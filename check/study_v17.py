"""V16-based upgrade-priority comparisons; reconstructed diagnostics, not official scores."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent
BASE = '6e6dd1310d32e79c45117b86dea00601eccf1e5e'
ARMS = ('control', 'damage', 'charge', 'laser')


def configuration(arm):
    cfg = json.loads(subprocess.check_output(['git', 'show', BASE+':automata/bot.json'], cwd=ROOT))
    source = subprocess.check_output(['git', 'show', BASE+':automata/src/brain/params.rs'], cwd=ROOT, text=True)
    old = re.findall(r'"([a-z_]+)"', source.split('upgrade_priority: [', 1)[1].split(']', 1)[0])
    assert len(old) == 22 and old[:3] == ['plating', 'armor', 'nanites']
    promote = {'control': [], 'damage': ['laser_damage'], 'charge': ['laser_charge'],
               'laser': ['laser_damage', 'laser_charge']}[arm]
    order = old[:3] + promote + [key for key in old[3:] if key not in promote]
    assert sorted(order) == sorted(old)
    assert [key for key in order if not key.startswith('laser_')] == [key for key in old if not key.startswith('laser_')]
    cfg['upgrade_priority'] = order
    assert cfg['range_laser'] == 200
    return cfg


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arms', default=','.join(ARMS))
    p.add_argument('--seeds', required=True)
    p.add_argument('--pursuit', type=float, default=.6)
    p.add_argument('--mode', choices=('squad', 'ffa'), default='squad')
    p.add_argument('--jobs', type=int, default=3)
    p.add_argument('--traces', action='store_true')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--executable', type=Path, default=WORK/'runtime-tools/v16-target/release/automata')
    a = p.parse_args()
    a.out = a.out.resolve()
    a.executable = a.executable.resolve()
    if a.out.exists():
        p.error('Use a new output path')
    a.out.parent.mkdir(parents=True, exist_ok=True)
    meta = {'kind': 'Reconstructed simulator; not an official score or forecast.',
        'baseline_commit': BASE, 'baseline_official_score': 6.25, 'baseline_receipt': 'BB-0E038934',
        'mode': a.mode, 'seeds': a.seeds, 'join_per_loss': a.pursuit, 'jobs': a.jobs,
        'executable': str(a.executable), 'executable_sha256': hashlib.sha256(a.executable.read_bytes()).hexdigest(),
        'sim_commit': subprocess.check_output(['git', '-C', str(WORK/'reference-juan'), 'rev-parse', 'HEAD'], text=True).strip(),
        'arms': {}}
    summary = {}
    for arm in a.arms.split(','):
        cfg = configuration(arm)
        cf = a.out.with_name(a.out.stem+'-'+arm+'-params.json')
        cf.write_text(json.dumps(cfg, sort_keys=True)+'\n')
        meta['arms'][arm] = cfg
        env = dict(os.environ, MECH_PARAMS=str(cf), PYTHONHASHSEED='0', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
        output = a.out.with_name(a.out.stem+'-'+arm+'.jsonl')
        command = [sys.executable, 'sim/run_matches.py', '--mode', a.mode, '--bot', str(a.executable),
            '--cwd', str(ROOT), '--arena', str(ROOT/'arena'), '--seeds', a.seeds, '--jobs', str(a.jobs),
            '--squad', f'join_per_loss={a.pursuit}', '--out', str(output)]
        if a.traces:
            command += ['--traces', str(a.out.parent/(a.out.stem+'-traces')/arm)]
        print('Starting '+arm, flush=True)
        with a.out.with_name(a.out.stem+'-'+arm+'.log').open('w') as log:
            subprocess.run(command, cwd=WORK/'reference-juan', env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        rows = [json.loads(line) for line in output.read_text().splitlines()]
        if not rows or any('error' in row for row in rows):
            raise RuntimeError('Incomplete arm: '+arm)
        with a.out.open('a') as out:
            for row in rows:
                out.write(json.dumps(dict(row, arm=arm), separators=(',', ':'))+'\n')
        summary[arm] = {'n': len(rows), **{'mean_'+key: statistics.mean(row[key] for row in rows)
            for key in ('score', 'kills', 'dmg_dealt', 'dmg_taken', 'cubes', 'zone_dmg')},
            'late': sum(row['late_replies'] for row in rows),
            'tracebacks': sum(row['bot_stderr_tracebacks'] for row in rows)}
        a.out.with_suffix('.meta.json').write_text(json.dumps(meta, indent=2)+'\n')
        a.out.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2)+'\n')
        print(json.dumps({arm: summary[arm]}), flush=True)


if __name__ == '__main__':
    main()

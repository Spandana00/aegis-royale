"""V14-based spacing/late-threat factorial diagnostics; never an official scorer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent
ARMS = {
    'control': {},
    'spacing': {'range_laser': 200},
    'late': {'gear_late_s': 120},
    'spacing_late': {'range_laser': 200, 'gear_late_s': 120},
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arms', default=','.join(ARMS))
    p.add_argument('--seeds', required=True)
    p.add_argument('--jobs', type=int, default=3)
    p.add_argument('--pursuit', type=float, default=.6)
    p.add_argument('--mode', choices=('squad', 'ffa'), default='squad')
    p.add_argument('--traces', action='store_true')
    p.add_argument('--executable', type=Path, default=WORK/'runtime-tools/v14-target/release/automata')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out = a.out.resolve()
    a.executable = a.executable.resolve()
    if a.out.exists():
        p.error('Use a fresh output path')
    a.out.parent.mkdir(parents=True, exist_ok=True)
    base = json.loads(subprocess.check_output(['git', 'show',
        '3f08bd1311f93bde3696a2f5a295fd603e9e9fa0:automata/bot.json'], cwd=ROOT))
    meta = {'kind': 'third-party reconstructed simulation; not official scoring',
        'baseline': '3f08bd1311f93bde3696a2f5a295fd603e9e9fa0',
        'seeds': a.seeds, 'mode': a.mode, 'join_per_loss': a.pursuit,
        'jobs': a.jobs, 'executable': str(a.executable),
        'executable_sha256': hashlib.sha256(a.executable.read_bytes()).hexdigest(),
        'sim_commit': subprocess.check_output(['git', '-C', str(WORK/'reference-juan'),
            'rev-parse', 'HEAD'], text=True).strip(), 'arms': {}}
    summary = {}
    for arm in a.arms.split(','):
        params = dict(base, **ARMS[arm])
        cf = a.out.with_name(a.out.stem+'-'+arm+'-params.json')
        cf.write_text(json.dumps(params, sort_keys=True)+'\n')
        meta['arms'][arm] = params
        env = dict(os.environ, MECH_PARAMS=str(cf), PYTHONHASHSEED='0',
                   OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
        output = a.out.with_name(a.out.stem+'-'+arm+'.jsonl')
        args = [sys.executable, 'sim/run_matches.py', '--mode', a.mode,
            '--bot', str(a.executable), '--cwd', str(ROOT), '--arena', str(ROOT/'arena'),
            '--seeds', a.seeds, '--jobs', str(a.jobs), '--squad', f'join_per_loss={a.pursuit}',
            '--out', str(output)]
        if a.traces:
            args += ['--traces', str(a.out.parent/(a.out.stem+'-traces')/arm)]
        print('Starting '+arm, flush=True)
        with a.out.with_name(a.out.stem+'-'+arm+'.log').open('w') as log:
            subprocess.run(args, cwd=WORK/'reference-juan', env=env,
                stdout=log, stderr=subprocess.STDOUT, check=True)
        rows = [json.loads(line) for line in output.read_text().splitlines()]
        if not rows or any('error' in row for row in rows):
            raise RuntimeError('Incomplete diagnostic: '+arm)
        with a.out.open('a') as f:
            for row in rows:
                f.write(json.dumps(dict(row, arm=arm), separators=(',', ':'))+'\n')
        summary[arm] = {'n': len(rows), **{
            'mean_'+key: statistics.mean(row[key] for row in rows)
            for key in ('score', 'kills', 'dmg_taken', 'dmg_dealt', 'cubes', 'zone_dmg')},
            'late': sum(row['late_replies'] for row in rows),
            'tracebacks': sum(row['bot_stderr_tracebacks'] for row in rows)}
        a.out.with_suffix('.meta.json').write_text(json.dumps(meta, indent=2)+'\n')
        a.out.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2)+'\n')
        print(json.dumps({arm: summary[arm]}), flush=True)


if __name__ == '__main__':
    main()

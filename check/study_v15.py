"""Matched V14 control and independently switched V15 hypotheses. Proxy, never official score."""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent
RUST = WORK / 'reference-automata'
GO = WORK / 'reference-arnav'
OVERRIDES = {
    'control': {},
    'candidate': {'aim_share': True, 'beam_damage_fix': True, 'beam_armor_budget': True},
    'share': {'aim_share': True},
    'share_budget': {'aim_share': True, 'beam_damage_fix': True, 'beam_armor_budget': True},
    'budget': {'beam_damage_fix': True, 'beam_armor_budget': True},
    'zone': {'zone_charge_guard': True},
    'beam_zone': {'beam_damage_fix': True, 'zone_charge_guard': True},
    'beam': {'beam_damage_fix': True},
    'motion': {'aim_motion_fix': True},
    'both': {'beam_damage_fix': True, 'aim_motion_fix': True},
    'mortar': {'sf_mortar': 2},
    'beam_mortar': {'beam_damage_fix': True, 'sf_mortar': 2},
    'motion_mortar': {'aim_motion_fix': True, 'sf_mortar': 2},
    'all': {'beam_damage_fix': True, 'aim_motion_fix': True, 'sf_mortar': 2},
    'pursuit': {'gear_pursuit_s': 6},
    'both_pursuit': {'beam_damage_fix': True, 'aim_motion_fix': True, 'gear_pursuit_s': 6},
}



def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arms', default='control,beam,motion,both,mortar,beam_mortar,motion_mortar,all,pursuit,both_pursuit')
    p.add_argument('--seeds', default='7000-7023')
    p.add_argument('--jobs', type=int, default=3)
    p.add_argument('--pursuit', type=float, default=.6)
    p.add_argument('--mode', choices=('squad', 'ffa'), default='squad')
    p.add_argument('--traces', action='store_true')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--source-root', type=Path, default=ROOT/'automata')
    p.add_argument('--executable', type=Path, default=WORK/'runtime-tools/v15-target/release/automata')
    a = p.parse_args()
    a.source_root = a.source_root.resolve()
    a.executable = a.executable.resolve()
    a.out = a.out.resolve()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    if a.out.exists():
        p.error('Use a new output path')
    cfg = json.loads((WORK / 'baseline-v14/automata/bot.json').read_text())
    meta = {'kind': 'third-party simulation diagnostics; not official scoring',
            'seeds': a.seeds, 'mode': a.mode, 'pursuit': a.pursuit, 'jobs': a.jobs,
            'config_matches_official_recording': True, 'arms': {},
            'sim_commit': subprocess.check_output(['git', '-C', str(WORK/'reference-juan'), 'rev-parse', 'HEAD'], text=True).strip()}
    for arm in a.arms.split(','):
        env = dict(os.environ, PYTHONHASHSEED='0', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
        cwd = ROOT
        command = str(a.executable)
        sources = sorted(a.source_root.glob('src/**/*.rs')) + [a.source_root/'Cargo.toml', a.source_root/'Cargo.lock']
        params = dict(cfg, **OVERRIDES[arm])
        cf = a.out.with_name(a.out.stem + '-' + arm + '-params.json')
        cf.write_text(json.dumps(params, sort_keys=True) + '\n')
        env['MECH_PARAMS'] = str(cf)
        meta['arms'][arm] = {'command': command, 'cwd': str(cwd), 'params': params,
            'executable_sha256': hashlib.sha256(Path(command).read_bytes()).hexdigest(),
            'source_commit': subprocess.check_output(['git', '-C', str(cwd), 'rev-parse', 'HEAD'], text=True).strip(),
            'source_sha256': {str(f.relative_to(a.source_root)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sources}}
        output = a.out.with_name(a.out.stem + '-' + arm + '.jsonl')
        args = [sys.executable, 'sim/run_matches.py', '--mode', a.mode, '--bot', command,
                '--cwd', str(cwd), '--arena', str(ROOT/'arena'), '--seeds', a.seeds,
                '--jobs', str(a.jobs), '--squad', f'join_per_loss={a.pursuit}', '--out', str(output)]
        if a.traces:
            args += ['--traces', str(a.out.parent / (a.out.stem + '-traces') / arm)]
        print('Starting', arm, flush=True)
        with a.out.with_name(a.out.stem + '-' + arm + '.log').open('w') as log:
            subprocess.run(args, cwd=WORK/'reference-juan', env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        rows = [json.loads(x) for x in output.read_text().splitlines()]
        if len(rows) == 0 or any('error' in x for x in rows):
            raise RuntimeError(f'Invalid simulator run for {arm}')
        with a.out.open('a') as out:
            for r in rows:
                r['arm'] = arm
                out.write(json.dumps(r, separators=(',', ':')) + '\n')
        grouped = defaultdict(list)
        for line in a.out.read_text().splitlines():
            r = json.loads(line)
            grouped[r['arm']].append(r)
        summary = {k: {'n': len(v), 'mean_proxy_points': statistics.mean(x['score'] for x in v),
                       'mean_damage_dealt': statistics.mean(x['dmg_dealt'] for x in v),
                       'mean_cubes': statistics.mean(x['cubes'] for x in v),
                       'mean_zone_damage': statistics.mean(x['zone_dmg'] for x in v),
                       'late': sum(x['late_replies'] for x in v),
                       'tracebacks': sum(x['bot_stderr_tracebacks'] for x in v)} for k,v in grouped.items()}
        a.out.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2)+'\n')
        a.out.with_suffix('.meta.json').write_text(json.dumps(meta, indent=2)+'\n')
        print(json.dumps({arm: summary[arm]}), flush=True)


if __name__ == '__main__':
    main()

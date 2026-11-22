"""Keep V18 screening, fresh comparisons and reserved confirmation separate."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path

from analyze_v17 import summary


def trace(path):
    damage, hits = Counter(), Counter()
    frames = charging = close = shorts = 0
    first_laser = None
    with gzip.open(path, 'rt') as stream:
        header = json.loads(next(stream))
        slot = header['seed'] % 16
        for line in stream:
            row = json.loads(line)
            me = next((m for m in row.get('m', []) if m[0] == slot), None)
            if me and me[6] > 0:
                frames += 1
                charging += bool(me[8] & 4)
                if 2 in me[11:13] and first_laser is None:
                    first_laser = row['t'] / header['tick_hz']
                close += any(m[0] != slot and m[6] > 0 and 2 not in m[11:13]
                             and math.dist(m[1:4], me[1:4]) < 70 for m in row.get('m', []))
            for event in row.get('ev', []):
                if event.get('e') == 'hit' and event.get('dst') == slot:
                    damage[event['w']] += event['amt']
                    hits[event['w']] += 1
                if event.get('e') == 'short' and event.get('id') == slot:
                    shorts += 1
    return {'seed': header['seed'], 'live_frames': frames, 'charging_frames': charging,
            'frames_nonlaser_opponent_within70': close, 'first_laser_s': first_laser,
            'short_events': shorts, 'damage_taken': dict(damage), 'hits_taken': dict(hits),
            'trace_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results', nargs='+', type=Path, required=True)
    p.add_argument('--selected', choices=('spacing70', 'spacing85'), required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--traces', action='store_true')
    a = p.parse_args()
    groups, stages, all_rows, sources, trace_data = defaultdict(list), {}, [], [], {}
    for path in a.results:
        rows = [dict(json.loads(line), stage=path.stem) for line in path.read_text().splitlines()]
        if not rows or any('error' in row for row in rows):
            raise RuntimeError('Incomplete cohort: '+str(path))
        # The two development files share seeds and must be combined before pairing.
        cohort = ('holdout' if 'holdout' in path.stem else 'ffa' if 'ffa' in path.stem
                  else 'fresh' if 'fresh' in path.stem else 'screen')
        groups[cohort] += rows
        all_rows += rows
        sources.append(json.loads(path.with_suffix('.meta.json').read_text()))
        if cohort != 'screen':
            stages[path.stem] = summary(rows)
        trace_dir = path.with_name(path.stem+'-traces')
        if a.traces and trace_dir.exists():
            trace_data[path.stem] = {}
            for directory in sorted(trace_dir.iterdir()):
                parsed = [trace(f) for f in sorted(directory.glob('*.gz'))]
                damage, hits = Counter(), Counter()
                for row in parsed:
                    damage.update(row['damage_taken'])
                    hits.update(row['hits_taken'])
                trace_data[path.stem][directory.name] = {
                    'n': len(parsed), 'damage_taken': dict(damage), 'hits_taken': dict(hits),
                    'live_frames': sum(r['live_frames'] for r in parsed),
                    'charging_frames': sum(r['charging_frames'] for r in parsed),
                    'frames_nonlaser_opponent_within70': sum(r['frames_nonlaser_opponent_within70'] for r in parsed),
                    'short_events': sum(r['short_events'] for r in parsed),
                    'laser_ever': sum(r['first_laser_s'] is not None for r in parsed),
                    'laser_by30': sum(r['first_laser_s'] is not None and r['first_laser_s'] <= 30 for r in parsed),
                    'trace_hashes': {str(r['seed']): r['trace_sha256'] for r in parsed}}
    pooled = {name: summary(rows) for name, rows in groups.items()}
    validation = [row for name in ('fresh', 'holdout') for row in groups[name]
                  if row['arm'] in ('control', a.selected)]
    if validation:
        pooled['selected_validation'] = summary(validation)
    report = {'kind': 'Reconstructed simulation diagnostics; not an official score or forecast.',
        'matches': len(all_rows), 'selected_arm': a.selected,
        'baseline': 'V17, official 6.27, commit e45e734215354fc4f938af15c984a666f446a426',
        'stages': stages, 'pooled': pooled, 'trace_data': trace_data,
        'limits': ['Opponent behavior and escalation are reconstructed.',
            'Sampling intervals exclude model error and feature selection.',
            'Replay distance is geometric, without a visibility guarantee.',
            'Damage and weapon counts also depend on survival and encounters.']}
    a.out.write_text(json.dumps(report, indent=2)+'\n')
    a.out.with_name('v18_match_sources.json').write_text(json.dumps(sources, indent=2)+'\n')
    with a.archive.open('wb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as stream:
            stream.write(''.join(json.dumps(row, separators=(',', ':'))+'\n' for row in all_rows).encode())
    print(json.dumps({'matches': len(all_rows), 'pooled': pooled}, indent=2))


if __name__ == '__main__':
    main()

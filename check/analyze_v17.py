"""Keep development, reserved holdout and FFA evidence distinct."""
import argparse
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path

from analyze_v14 import matched


def summary(rows):
    result = matched(rows, baseline='control')
    for row in result.values():
        row['matched_difference_from_control'] = row.pop('matched_difference_from_v13')
    return result


def trace_upgrades(path):
    counts, equipped = Counter(), Counter()
    frames = charged = beams = 0
    with gzip.open(path, 'rt') as stream:
        header = json.loads(next(stream))
        slot = header['seed'] % 16
        me = None
        for line in stream:
            row = json.loads(line)
            if 'm' not in row:
                continue
            me = next((m for m in row['m'] if m[0] == slot), me)
            if me and me[6] > 0:
                frames += 1
                charged += bool(me[8] & 4)
            for event in row.get('ev', []):
                if event.get('id') != slot:
                    continue
                if event.get('e') == 'upgrade':
                    counts[event['up']] += 1
                    if me and 2 in me[11:13]:
                        equipped[event['up']] += 1
                elif event.get('e') == 'laser':
                    beams += 1
    return {'seed': header['seed'], 'chosen_upgrades': dict(counts),
        'chosen_while_holding_laser': dict(equipped), 'live_frames': frames,
        'charging_frames': charged, 'laser_releases': beams}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results', nargs='+', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--traces', action='store_true')
    a = p.parse_args()
    groups, stages, all_rows, sources, trace_data = defaultdict(list), {}, [], [], {}
    for path in a.results:
        rows = [dict(json.loads(line), stage=path.stem) for line in path.read_text().splitlines()]
        if not rows or any('error' in row for row in rows):
            raise RuntimeError('Incomplete cohort: '+str(path))
        stages[path.stem] = summary(rows)
        cohort = ('holdout' if 'holdout' in path.stem else 'ffa' if 'ffa' in path.stem
                  else 'fresh' if 'fresh' in path.stem else 'screen')
        groups[cohort] += rows
        all_rows += rows
        sources.append(json.loads(path.with_suffix('.meta.json').read_text()))
        trace_dir = path.with_name(path.stem+'-traces')
        if a.traces and trace_dir.exists():
            trace_data[path.stem] = {}
            for directory in sorted(trace_dir.iterdir()):
                parsed = [trace_upgrades(f) for f in sorted(directory.glob('*.gz'))]
                total, armed = Counter(), Counter()
                for row in parsed:
                    total.update(row['chosen_upgrades'])
                    armed.update(row['chosen_while_holding_laser'])
                trace_data[path.stem][directory.name] = {'n': len(parsed),
                    'chosen_upgrades': dict(total), 'chosen_while_holding_laser': dict(armed),
                    'live_frames': sum(row['live_frames'] for row in parsed),
                    'charging_frames': sum(row['charging_frames'] for row in parsed),
                    'laser_releases': sum(row['laser_releases'] for row in parsed)}
    pooled = {name: summary(rows) for name, rows in groups.items()}
    validation = [row for name in ('fresh', 'holdout') for row in groups[name]
                  if row['arm'] in ('control', 'charge')]
    if validation:
        pooled['charge_validation'] = summary(validation)
    report = {'kind': 'Reconstructed simulation diagnostics; not an official score or forecast.',
        'matches': len(all_rows), 'baseline': 'V16, official 6.25, commit 6e6dd1310d32e79c45117b86dea00601eccf1e5e',
        'stages': stages, 'pooled': pooled, 'trace_data': trace_data,
        'limits': ['Opponent behavior and escalation are reconstructed.',
            'Sampling intervals do not account for model error or feature selection.',
            'Upgrade and firing counts also reflect changed lifespans and encounters.']}
    a.out.write_text(json.dumps(report, indent=2)+'\n')
    a.out.with_name('v17_match_sources.json').write_text(json.dumps(sources, indent=2)+'\n')
    with a.archive.open('wb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as stream:
            stream.write(''.join(json.dumps(row, separators=(',', ':'))+'\n' for row in all_rows).encode())
    print(json.dumps({'matches': len(all_rows), 'pooled': pooled}, indent=2))


if __name__ == '__main__':
    main()

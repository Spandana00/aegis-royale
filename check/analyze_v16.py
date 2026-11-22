"""Summarize paired policy diagnostics without treating them as official scores."""
import argparse
from collections import defaultdict
import gzip
import json
from pathlib import Path

from analyze_v14 import matched


def summarize(rows):
    result = matched(rows, baseline='control')
    for row in result.values():
        row['matched_difference_from_control'] = row.pop('matched_difference_from_v13')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results', nargs='+', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--archive', type=Path, required=True)
    a = p.parse_args()
    groups = defaultdict(list)
    all_rows, stages, sources = [], {}, []
    for path in a.results:
        rows = [dict(json.loads(line), stage=path.stem) for line in path.read_text().splitlines()]
        if not rows or any('error' in row for row in rows):
            raise RuntimeError('Incomplete cohort: '+str(path))
        stages[path.stem] = summarize(rows)
        cohort = 'v15_requested_rerun' if path.stem.startswith('v15-requested-rerun') else (
            'v16_fresh' if path.stem.startswith('v16-fresh') else (
                'v16_holdout' if path.stem == 'v16-holdout' else (
                    'v16_ffa' if path.stem.startswith('v16-ffa') else 'v16_screen')))
        groups[cohort] += rows
        all_rows += rows
        sources.append(json.loads(path.with_suffix('.meta.json').read_text()))
    pooled = {key: summarize(rows) for key, rows in groups.items()}
    selected = [row for group in ('v16_fresh', 'v16_holdout') for row in groups[group]
                if row['arm'] in ('control', 'spacing')]
    if selected:
        pooled['v16_selected_validation'] = summarize(selected)
    interactions = {}
    for name, rows in {**stages, **pooled}.items():
        if all(key in rows for key in ('control', 'spacing', 'late', 'spacing_late')):
            interactions[name] = sum(rows[key]['proxy_mean'] * weight for key, weight in
                [('spacing_late', 1), ('spacing', -1), ('late', -1), ('control', 1)])
    report = {'kind': 'Third-party reconstructed simulation; not official scores or forecasts.',
        'matches': len(all_rows), 'stages': stages, 'pooled': pooled,
        'spacing_x_late_interaction_proxy_points': interactions,
        'limits': ['Opponent policy and escalation are reconstructed.',
            'Wall-clock planning budgets can change paths on repeated runs.',
            'Bootstrap intervals omit model error and selection error.',
            'Aggregate official receipts cannot identify a causal feature.']}
    a.out.write_text(json.dumps(report, indent=2)+'\n')
    a.out.with_name('v16_match_sources.json').write_text(json.dumps(sources, indent=2)+'\n')
    with a.archive.open('wb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as gz:
            gz.write(''.join(json.dumps(row, separators=(',', ':'))+'\n' for row in all_rows).encode())
    print(json.dumps({'matches': len(all_rows), 'pooled': pooled,
                      'interactions': interactions}, indent=2))


if __name__ == '__main__':
    main()

"""Matched V15 diagnostics, including feature interactions and weapon outcomes."""
import argparse
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import statistics

from analyze_v14 import matched, trace


def weapon_trace(path):
    slot = int(path.name.split('seed')[1].split('.')[0]) % 16
    totals, kills = Counter(), []
    me = None
    with gzip.open(path, 'rt') as stream:
        header = json.loads(next(stream))
        for line in stream:
            frame = json.loads(line)
            if 'm' not in frame:
                continue
            me = next((m for m in frame['m'] if m[0] == slot), me)
            for event in frame.get('ev', []):
                kind = event.get('e')
                if kind == 'fire' and event.get('id') == slot:
                    totals['shots_'+event['w']] += 1
                elif kind == 'laser' and event.get('id') == slot:
                    totals['shots_laser'] += 1
                    totals['laser_releases_with_mech_hits'] += any(h < 16 for h in event.get('hits', []))
                elif kind == 'hit' and event.get('src') == slot:
                    category = 'mech' if event['dst'] < 16 else 'resource'
                    totals[f"damage_{event['w']}_{category}"] += event['amt']
                    totals[f"hits_{event['w']}_{category}"] += 1
                elif kind == 'cookoff' and event.get('id') == slot:
                    totals['own_mortar_cookoffs'] += 1
                elif kind == 'death' and event.get('by') == slot and event['id'] < 16:
                    kills.append({'t': event['t']/header['tick_hz'], 'victim': event['id'],
                                  'our_cubes': me[9] if me else None,
                                  'our_hp_fraction': me[6]/me[10] if me else None})
    return {'totals': dict(totals), 'kills': kills}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results', nargs='+', type=Path, required=True)
    p.add_argument('--traces', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    stages, rows_by_stage, trace_data = {}, {}, {}
    for file in a.results:
        rows = [json.loads(line) for line in file.read_text().splitlines()]
        rows_by_stage[file.stem] = rows
        stages[file.stem] = matched(rows, baseline='control')
    for cohort, prefix in [('initial','v15-fresh-'),('zone','v15-zone-fresh-'),
                           ('budget','v15-budget-fresh-'),('share','v15-share-fresh-'),
                           ('final','v15-final-fresh-')]:
        squad = [r for stage,rows in rows_by_stage.items() if stage.startswith(prefix) and 'ffa' not in stage for r in rows]
        ffa = [r for stage,rows in rows_by_stage.items() if stage.startswith(prefix) and 'ffa' in stage for r in rows]
        if squad: stages[cohort+'_squad_pooled'] = matched(squad, baseline='control')
        if ffa: stages[cohort+'_ffa_pooled'] = matched(ffa, baseline='control')
    if a.traces:
        for directory in sorted(a.traces.iterdir()):
            rows = [dict(trace(file), **weapon_trace(file)) for file in sorted(directory.glob('*.jsonl.gz'))]
            totals = Counter()
            for row in rows:
                totals.update(row['totals'])
            trace_data[directory.name] = {'n': len(rows), 'totals': dict(totals), 'rows': rows}
    screen = next((v for k,v in stages.items() if k.endswith('screen')), {})
    interactions = {}
    if all(x in screen for x in ['control','beam','motion','both']):
        interactions['beam_x_motion'] = sum(screen[k]['proxy_mean']*w for k,w in [('both',1),('beam',-1),('motion',-1),('control',1)])
    if all(x in screen for x in ['control','beam','mortar','beam_mortar']):
        interactions['beam_x_mortar_ban'] = sum(screen[k]['proxy_mean']*w for k,w in [('beam_mortar',1),('beam',-1),('mortar',-1),('control',1)])
    sharing = stages.get('share_squad_pooled', {})
    if all(x in sharing for x in ['control','share','budget','share_budget']):
        interactions['fresh_aim_share_x_cube_bounded_release'] = sum(sharing[k]['proxy_mean']*w for k,w in [('share_budget',1),('share',-1),('budget',-1),('control',1)])
    for cohort in stages.values():
        for result in cohort.values():
            result['matched_difference_from_control'] = result.pop('matched_difference_from_v13')
    report = {'kind': 'approximate simulation diagnostics; not official scores',
              'comparison_baseline': 'V14 behavior with all added switches off',
              'matches': sum(len(rows) for rows in rows_by_stage.values()),
              'stages': stages, 'screen_interactions_proxy_points': interactions,
              'trace_data': trace_data}
    a.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'matches': report['matches'], 'stages': stages, 'interactions': interactions},indent=2))


if __name__ == '__main__':
    main()

"""Summarize matched diagnostics and event traces; never estimate official score."""
import argparse
from collections import Counter, defaultdict
import gzip
import json
import math
from pathlib import Path
import random
import statistics


def matched(rows, baseline='v13'):
    groups = defaultdict(dict)
    for row in rows:
        key = (row['mode'], row['seed'])
        groups[row['arm']][key] = row
    report = {}
    for arm, data in groups.items():
        values = list(data.values())
        keys = sorted(data.keys() & groups[baseline].keys())
        differences = [data[k]['score'] - groups[baseline][k]['score'] for k in keys]
        rng = random.Random(14)
        samples = sorted(statistics.mean(rng.choices(differences, k=len(differences)))
                         for _ in range(4000)) if differences else []
        report[arm] = {
            'n': len(values), 'proxy_mean': statistics.mean(r['score'] for r in values),
            'matched_difference_from_v13': statistics.mean(differences) if differences else None,
            'paired_bootstrap_95_percent': [samples[99], samples[3899]] if samples else None,
            'sampling_interval_excludes_model_and_selection_error': True,
            'mean_cubes_at_death_or_finish': statistics.mean(r['cubes'] for r in values),
            'mean_damage_dealt': statistics.mean(r['dmg_dealt'] for r in values),
            'mean_zone_damage': statistics.mean(r['zone_dmg'] for r in values),
            'early_deaths_before_30s': sum(r['death_t'] is not None and 0 <= r['death_t'] < 30 for r in values),
            'late_replies': sum(r['late_replies'] for r in values),
            'tracebacks': sum(r['bot_stderr_tracebacks'] for r in values),
        }
    return report


def trace(path):
    seed = int(path.name.split('seed')[1].split('.')[0])
    slot = seed % 16
    first_laser, first_secondary, cube30, hp30 = None, None, None, None
    low_energy, charge, live_frames, rear_damage, damage = 0, 0, 0, 0., 0.
    previous, distance = None, 0.
    sources = Counter()
    with gzip.open(path, 'rt') as stream:
        header = json.loads(next(stream))
        for line in stream:
            frame = json.loads(line)
            if 'm' not in frame:
                continue
            t = frame['t'] / header['tick_hz']
            me = next((m for m in frame['m'] if m[0] == slot and m[6] > 0), None)
            if me:
                live_frames += 1
                low_energy += me[7] < 20
                charge += bool(me[8] & 4)
                if previous:
                    distance += math.hypot(me[1]-previous[0], me[2]-previous[1])
                previous = me[1:3]
                if me[12] >= 0 and first_secondary is None:
                    first_secondary = t
                if 2 in me[11:13] and first_laser is None:
                    first_laser = t
                if t >= 30 and cube30 is None:
                    cube30, hp30 = me[9], me[6] / me[10]
            for event in frame.get('ev', []):
                if event.get('e') == 'hit' and event.get('dst') == slot:
                    amount = event.get('amt', 0)
                    damage += amount
                    rear_damage += amount if event.get('rear') else 0
                    sources[str(event.get('src'))] += amount
    return {'seed': seed, 'first_laser_s': first_laser,
            'first_secondary_s': first_secondary,
            'cubes_at_30s_if_alive': cube30, 'hp_fraction_at_30s_if_alive': hp30,
            'fraction_live_frames_energy_below_20': low_energy/max(1, live_frames),
            'fraction_live_frames_charging': charge/max(1, live_frames),
            'distance_travelled_m': distance, 'incoming_hit_damage': damage,
            'incoming_rear_hit_damage': rear_damage,
            'incoming_damage_by_source': dict(sources)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results', nargs='+', type=Path, required=True)
    p.add_argument('--traces', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    output = {'kind': 'third-party simulation diagnostics; not official scoring',
              'stages': {}, 'trace_summary': {}, 'trace_rows': {}}
    for source in a.results:
        rows = [json.loads(line) for line in source.read_text().splitlines()]
        output['stages'][source.stem] = matched(rows)
    if a.traces:
        for directory in sorted(a.traces.iterdir()):
            rows = [trace(file) for file in sorted(directory.glob('*.jsonl.gz'))]
            if not rows:
                continue
            output['trace_rows'][directory.name] = rows
            output['trace_summary'][directory.name] = {
                'n': len(rows), 'laser_by_30s': sum(r['first_laser_s'] is not None and r['first_laser_s'] <= 30 for r in rows),
                'laser_ever': sum(r['first_laser_s'] is not None for r in rows),
                'survived_to_30s': sum(r['cubes_at_30s_if_alive'] is not None for r in rows),
                'mean_cubes_at_30s_among_survivors': statistics.mean(r['cubes_at_30s_if_alive'] for r in rows if r['cubes_at_30s_if_alive'] is not None),
                'mean_low_energy_fraction': statistics.mean(r['fraction_live_frames_energy_below_20'] for r in rows),
                'incoming_hit_damage': sum(r['incoming_hit_damage'] for r in rows),
                'incoming_rear_hit_damage': sum(r['incoming_rear_hit_damage'] for r in rows),
            }
    a.out.write_text(json.dumps(output, indent=2)+'\n')
    print(json.dumps({'stages': output['stages'], 'trace_summary': output['trace_summary']}, indent=2))


if __name__ == '__main__':
    main()

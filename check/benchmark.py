"""Replay + synthetic stress timings. These are NOT match scores."""
import copy
import gzip
import json
import math
from pathlib import Path
import random
import resource
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bot import Bot
from check import Schema


def main():
    with gzip.open(ROOT / 'check/stream.jsonl.gz', 'rt') as f:
        messages = [json.loads(line) for line in f]
    hello = messages[0]
    hello['map']['dir'] = str(ROOT / 'arena')
    start = time.perf_counter()
    bot = Bot(hello)
    startup_ms = (time.perf_counter() - start) * 1000
    schema = Schema(ROOT / 'mechfight.schema.json')
    observations = [m for m in messages if m['type'] == 'obs']
    rng = random.Random(3917)
    for index in range(220):
        o = copy.deepcopy(observations[index % len(observations)])
        me = o['self']
        o['t'] = 160 + index * .1
        o['tick'] = 3200 + 2 * index
        me['hp'] = 420 if index % 4 else 1400
        kind = ('laser','mortar','lightning')[index % 3]
        me['weapons'][1] = {'kind':kind,'cooldown':0,'charge':.4 if kind == 'laser' else 0,
                            'stats':copy.deepcopy(hello['config']['weapons'][kind])}
        o['mechs'] = []
        for i in range(15):
            a, d = rng.uniform(0,2*math.pi), rng.uniform(15,180)
            x, y = me['pos'][0]+d*math.cos(a), me['pos'][1]+d*math.sin(a)
            o['mechs'].append({'id':i+10,'kind':'mech','pos':[x,y,bot.world.ground(x,y)],
                'vel':[rng.uniform(-20,20),rng.uniform(-20,20),rng.uniform(-5,5)],
                'aim':[a+math.pi,0],'hp':rng.uniform(20,1600),'max_hp':1600,
                'cubes':i,'weapons':['gun',kind],'charging':i%3==0})
        o['projectiles'] = []
        for i in range(40):
            a, d = rng.uniform(0,2*math.pi), rng.uniform(10,100)
            x, y = me['pos'][0]+d*math.cos(a), me['pos'][1]+d*math.sin(a)
            o['projectiles'].append({'id':1000+i,'kind':'gun' if i%3 else 'mortar',
                'pos':[x,y,me['pos'][2]+rng.uniform(0,30)],
                'vel':[-200*math.cos(a),-200*math.sin(a),-5]})
        observations.append(o)
    # Exercise cover searches while healthy and reloading; low-HP recovery
    # would otherwise bypass this branch in most busy observations above.
    busy = observations[300:]
    for index in range(80):
        o = copy.deepcopy(busy[index % len(busy)])
        now = 220 + index * .6
        o.update(t=now, tick=4400 + 12 * index)
        me = o['self']
        me['hp'] = me['max_hp']
        me['weapons'][0].update(ammo=0, reload=2.3, cooldown=0.)
        me['weapons'][1] = None
        o['mechs'] = o['mechs'][:(1,3,15)[index % 3]]
        o['zone'].update(center=me['pos'][:2], next_center=me['pos'][:2],
                         radius=300, next_radius=250,
                         shrink_start=now+60, shrink_end=now+100)
        observations.append(o)
    timings = []
    failures = []
    for o in observations:
        start = time.perf_counter()
        action = bot.act(o)
        timings.append((time.perf_counter()-start)*1000)
        errors = schema.errors(action, 'Action')
        if errors or not all(math.isfinite(v) for k in ('move','aim') for v in action.get(k, [])):
            failures.append({'tick':o['tick'],'errors':errors})
        # mf.run normally drains debug drawings every decision.
        import mechfight
        mechfight.draw.take()
    timings.sort()
    report = {'kind':'local correctness and timing; not a scored match',
              'startup_ms':round(startup_ms,2), 'observations':len(timings),
              'p50_ms':round(statistics.median(timings),3),
              'p99_ms':round(timings[int(len(timings)*.99)],3),
              'max_ms':round(max(timings),3), 'over_50_ms':sum(v>50 for v in timings),
              'max_rss_mib':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2),
              'invalid_actions':failures}
    print(json.dumps(report,indent=2))
    if failures or report['over_50_ms']:
        sys.exit(1)


if __name__=='__main__':
    main()

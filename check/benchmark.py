"""Replay + synthetic stress timings. These are NOT match scores."""
import copy
import argparse
from collections import Counter
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy',choices=('v9','v11'),default='v11')
    args=parser.parse_args()
    with gzip.open(ROOT / 'check/stream.jsonl.gz', 'rt') as f:
        messages = [json.loads(line) for line in f]
    hello = messages[0]
    hello['map']['dir'] = str(ROOT / 'arena')
    start = time.perf_counter()
    if args.policy=='v9':
        bot=Bot(hello)
    else:
        from pilot.main import Pilot
        from types import SimpleNamespace
        class Candidate:
            def __init__(self):
                self.policy=Pilot(hello)
                if self.policy.state.arena is None or not self.policy.state.arena.ok_nav:
                    raise RuntimeError('Active navigation cache did not load')
                self.world=SimpleNamespace(ground=self.policy.state.arena.ground_z)
            def act(self,obs):
                return self.policy.decide(obs,time.perf_counter())
            @property
            def mode(self):
                return getattr(self.policy.state.prev_intent,'mode','unknown')
        bot=Candidate()
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
    # Continuous tracks exercise the learned circular model; independent random
    # snapshots alone reset its history and mostly time the linear fallback.
    for index in range(120):
        o = copy.deepcopy(observations[0])
        now = 300 + index*.1
        o.update(t=now,tick=6000+2*index,events=[],crates=[],cubes=[],pickups=[],
                 projectiles=[],sounds=[],drops=[],offer=None)
        me=o['self'];me['hp']=me['max_hp'];me['weapons'][1]=None
        me['weapons'][0].update(ammo=12,reload=0.,cooldown=0.)
        o['zone'].update(center=me['pos'][:2],next_center=me['pos'][:2],radius=300,
                         next_radius=250,shrink_start=now+60,shrink_end=now+100)
        o['mechs']=[]
        for i in range(6):
            a=now*1.2+i
            cx=me['pos'][0]+140*math.cos(i*math.tau/6)
            cy=me['pos'][1]+140*math.sin(i*math.tau/6)
            o['mechs'].append({'id':i+10,'kind':'mech','pos':[cx+16*math.cos(a),cy+16*math.sin(a),me['pos'][2]],
                'vel':[-19.2*math.sin(a),19.2*math.cos(a),0.], 'aim':[a+math.pi,0.],
                'hp':1400,'max_hp':1400,'cubes':0,'weapons':['gun','lightning'],'charging':False})
        observations.append(o)
    # Resource-rich contact frames exercise V9's additional reachability and
    # collision checks, including rejected detours and multiple attackers.
    for index in range(120):
        o = copy.deepcopy(observations[0])
        now = 330 + index*.1
        o.update(t=now,tick=6600+2*index,events=[],crates=[],cubes=[],pickups=[],
                 projectiles=[],sounds=[],drops=[],offer=None)
        me=o['self'];me['hp']=me['max_hp'];me['cubes']=index%11
        me['weapons'][0].update(ammo=12,reload=0.,cooldown=0.)
        me['weapons'][1]=None if index%2 else {
            'kind':'mortar','cooldown':0.,'stats':copy.deepcopy(hello['config']['weapons']['mortar'])}
        o['zone'].update(center=me['pos'][:2],next_center=me['pos'][:2],radius=300,
                         next_radius=250,shrink_start=now+60,shrink_end=now+100)
        o['mechs']=[]
        for i in range(1 if index%3 else 2):
            a=i*1.5
            o['mechs'].append({'id':i+30,'kind':'mech',
                'pos':[me['pos'][0]+50*math.cos(a),me['pos'][1]+50*math.sin(a),me['pos'][2]],
                'vel':[-8.,0.,0.], 'aim':[math.pi+a,0.], 'hp':1400,'max_hp':1400,
                'cubes':0,'weapons':['gun','lightning'],'charging':False})
        for i in range(12):
            a=i*math.tau/12
            d=8.+(i%4)*18.
            p=[me['pos'][0]+d*math.cos(a),me['pos'][1]+d*math.sin(a),me['pos'][2]]
            o['pickups'].append({'id':8000+i,'kind':'laser' if i%2 else 'lightning','pos':p})
            if i%3==0:
                o['cubes'].append({'id':5000+i,'pos':[me['pos'][0]+8*math.cos(a),
                                                        me['pos'][1]+8*math.sin(a),me['pos'][2]]})
        observations.append(o)
    timings = []
    learned_observations = 0
    tactical_resource_observations = 0
    failures = []
    modes=Counter()
    for o in observations:
        start = time.perf_counter()
        action = bot.act(o)
        timings.append((time.perf_counter()-start)*1000)
        modes[bot.mode]+=1
        learner=getattr(bot,'aim_learner',None)
        if learner and any(tr['selected'] for tr in learner.tracks.values()):
            learned_observations += 1
        if bot.mode in ('arm','salvage'):
            tactical_resource_observations += 1
        errors = schema.errors(action, 'Action')
        if errors or not all(math.isfinite(v) for k in ('move','aim') for v in action.get(k, [])):
            failures.append({'tick':o['tick'],'errors':errors})
        # mf.run normally drains debug drawings every decision.
        import mechfight
        mechfight.draw.take()
    timings.sort()
    report = {'kind':'local correctness and timing; not a scored match',
              'policy':args.policy,
              'startup_ms':round(startup_ms,2), 'observations':len(timings),
              'p50_ms':round(statistics.median(timings),3),
              'p99_ms':round(timings[int(len(timings)*.99)],3),
              'max_ms':round(max(timings),3), 'over_50_ms':sum(v>50 for v in timings),
              'max_rss_mib':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2),
              'observations_with_learned_aim':learned_observations,
              'observations_with_tactical_collection':tactical_resource_observations,
              'invalid_actions':failures}
    if args.policy=='v11':
        report.pop('observations_with_learned_aim')
        report.pop('observations_with_tactical_collection')
        report.update(mode_counts=dict(modes),module_errors=bot.policy.errors,
                      soft_budget_overruns=bot.policy.overruns,
                      arming_decisions=bot.policy.state.scratch.get('brain',{}).get('arm_decisions',0),
                      process_deadline_guard_tested=False)
        if bot.policy.errors:
            failures.append({'module_errors':bot.policy.errors})
    print(json.dumps(report,indent=2))
    if failures or report['over_50_ms']:
        sys.exit(1)


if __name__=='__main__':
    main()

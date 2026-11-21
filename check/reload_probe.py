"""Paired map exposure diagnostic during a gun reload; not a match scorer.

Uses real campus geometry and acceleration-limited ground movement. A fixed
observer checks line of fire to three body heights. It does not simulate enemy
AI, projectiles, damage, deaths, jumping, loot, or placement.
"""
import argparse
import copy
import gzip
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bot import Bot
import mechfight

BASELINE = '5209875b7f6f512de87b0411b6c44258cd113fbb'


def exposed(world, position, height, source):
    return any(world.clear_ray(source, [*position[:2], position[2] + height * fraction])
               for fraction in (.25, .55, .9))


def play(prototype, template, start, enemy, seconds):
    bot = copy.deepcopy(prototype)
    obs = copy.deepcopy(template)
    me = obs['self']
    me.update(pos=start[:],vel=[0.,0.,0.],hp=1400,max_hp=1400,energy=100.,grounded=True)
    me['weapons'][1] = None
    me['aim'] = [math.atan2(enemy['pos'][1]-start[1],enemy['pos'][0]-start[0]),0.]
    obs.update(mechs=[copy.deepcopy(enemy)],projectiles=[],crates=[],cubes=[],pickups=[],drops=[],events=[],sounds=[],offer=None)
    obs['zone'].update(center=start[:2],next_center=start[:2],radius=300.,next_radius=250.,shrink_start=100.,shrink_end=150.)
    bot.mode,bot.target_id = 'fight',enemy['id']
    bot.last_harm,bot.last_combat = 29.,29.
    source = [*enemy['pos'][:2],enemy['pos'][2]+7.]
    dt, seen, reloading_steps, last_spend = .05,0.,0,-100.
    first_loaded_trigger = None
    action = {'move':[0.,0.],'boost':False,'aim':me['aim'][:]}
    # Also check when a loaded gun first gets a firing opportunity after the
    # reload. Holding cover forever must not look like a cost-free improvement.
    for step in range(round((seconds+2.)/dt)):
        now=30.+step*dt
        obs.update(tick=600+step,t=now)
        remaining=max(0.,seconds-step*dt)
        me['weapons'][0].update(ammo=0 if remaining>1e-8 else 12,reload=remaining,cooldown=0.)
        if step%2 == 0:
            action=bot.act(obs)
            mechfight.draw.take()
            reloading_steps += int(bot.mode=='reload')
            if remaining<1e-8 and action['fire'][0] and first_loaded_trigger is None:
                first_loaded_trigger=round(max(0.,step*dt-seconds),3)
        aim=action.get('aim',me['aim'])
        delta=(aim[0]-me['aim'][0]+math.pi)%(2*math.pi)-math.pi
        me['aim'][0] += max(-4*dt,min(4*dt,delta))
        me['aim'][1] += max(-3*dt,min(3*dt,aim[1]-me['aim'][1]))
        boost=action.get('boost',False) and me['energy']>0
        speed=me['stats']['boost_speed'] if boost else me['stats']['walk_speed']
        desired=[v*speed for v in action['move']]
        delta=[desired[i]-me['vel'][i] for i in range(2)]
        length=math.hypot(*delta)
        fraction=min(1.,me['stats']['ground_accel']*dt/max(1e-9,length))
        velocity=[me['vel'][i]+delta[i]*fraction for i in range(2)]
        displacement=[(me['vel'][i]+velocity[i])*.5*dt for i in range(2)]
        # Approximate wall sliding in this ground-only diagnostic.
        previous=me['pos'][:]
        for axes in ((0,1),(0,),(1,)):
            point=previous[:]
            for axis in axes:
                point[axis] += displacement[axis]
            if bot.world.travel_clear(previous,point,me['stats']['radius'],me['stats']['height']):
                me['pos']=[point[0],point[1],bot.world.ground(*point[:2])]
                me['vel']=[velocity[i] if i in axes else 0. for i in range(2)]+[0.]
                break
        else:
            me['vel']=[0.,0.,0.]
        if boost:
            me['energy']=max(0.,me['energy']-me['stats']['boost_drain']*dt)
            last_spend=now
        elif now-last_spend>me['stats']['energy_regen_delay']:
            me['energy']=min(100.,me['energy']+me['stats']['energy_regen']*dt)
        if step*dt < seconds-1e-8:
            seen += dt*exposed(bot.world,me['pos'],me['stats']['height'],source)
    return {'exposed_s':round(seen,3),'cover_decisions':reloading_steps,
            'travel_m':round(math.dist(start[:2],me['pos'][:2]),2),
            'first_loaded_trigger_delay_s':first_loaded_trigger}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=2421)
    parser.add_argument('--trials',type=int,default=32)
    parser.add_argument('--baseline-ref',default=BASELINE)
    args=parser.parse_args()
    with gzip.open(ROOT/'check/stream.jsonl.gz','rt') as f:
        messages=[json.loads(line) for line in f]
    hello=messages[0]
    hello['map']['dir']=str(ROOT/'arena')
    initial=next(m for m in messages if m['type']=='obs')
    source=subprocess.check_output(['git','show',f'{args.baseline_ref}:bot.py'],cwd=ROOT,text=True)
    baseline_module=types.ModuleType('trusted_repository_baseline')
    baseline_module.__file__=str(ROOT/'bot.py')
    exec(compile(source,'baseline_bot.py','exec'),baseline_module.__dict__)
    baseline,candidate=baseline_module.Bot(hello),Bot(hello)
    rng=random.Random(args.seed)
    world,nav=candidate.world,candidate.nav
    cells=[i for i,v in enumerate(nav.open) if v]
    scenarios=[]
    # Sample ground positions near buildings, with a clear initial firing line.
    # Selection is independent of whether the candidate finds any reload cover.
    for attempt in range(20000):
        k=rng.choice(cells)
        x,y=nav.point(k)
        near=world.nearby(x,y,40.)
        if not any(p.top-world.ground(x,y)>10 and p.overlaps(x,y,40.) for p in (world.prisms[i] for i in near)):
            continue
        z=world.ground(x,y)
        angle,distance=rng.uniform(-math.pi,math.pi),rng.uniform(85.,140.)
        ex,ey=x+distance*math.cos(angle),y+distance*math.sin(angle)
        ez=world.ground(ex,ey)
        if not world.free(ex,ey,ez) or not world.clear_ray([ex,ey,ez+7],[x,y,z+4.95]):
            continue
        enemy={'id':5,'kind':'mech','pos':[ex,ey,ez],'vel':[0.,0.,0.],
               'aim':[angle+math.pi,0.],'hp':1400,'max_hp':1400,'cubes':0,
               'weapons':['gun'],'charging':False}
        scenarios.append(([x,y,z],enemy))
        if len(scenarios)==args.trials:
            break
    if len(scenarios)!=args.trials:
        raise RuntimeError('Could not sample requested number of independent scenarios')
    cases=[]
    for i,(start,enemy) in enumerate(scenarios):
        cases.append({'case':i,'start':start,'observer':enemy['pos'],
                      'baseline':play(baseline,initial,start,enemy,2.4),
                      'candidate':play(candidate,initial,start,enemy,2.4)})
    old=sum(c['baseline']['exposed_s'] for c in cases)
    new=sum(c['candidate']['exposed_s'] for c in cases)
    report={'kind':'paired reload-window line-of-fire diagnostic; not damage or placement',
            'seed':args.seed,'trials':args.trials,'baseline_ref':args.baseline_ref,
            'candidate':candidate.name,'seconds_per_trial':2.4,
            'baseline_exposed_s':round(old,3),'candidate_exposed_s':round(new,3),
            'exposure_reduction_pct':round(100*(old-new)/old,2) if old else 0.,
            'post_reload_observation_s':2.,
            'cases':cases}
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()

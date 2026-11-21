"""Scripted gun-ray collision diagnostic; not the game or a placement scorer.

Tests constant horizontal motion plus known vertical acceleration and landing.
It isolates aiming: no enemy AI, spread, torso slew, damage, deaths, or strategy.
"""
import copy
import gzip
import itertools
import json
import math
from pathlib import Path
import subprocess
import sys
import types

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bot import Bot
from world import World,Prism

BASELINE='5209875b7f6f512de87b0411b6c44258cd113fbb'


def scene(distance,roof):
    world=World.__new__(World)
    world.ground=lambda x,y:0.
    world.prisms=[]
    world.cells={}
    if roof:
        p=Prism({'base':10.,'top':roof,
                 'ring':[distance-12,-60,distance+100,-60,distance+100,60,distance-12,60],
                 'holes':[]})
        world.prisms=[p]
        x0,y0,x1,y1=p.box
        for x in range(math.floor(x0/world.CELL),math.floor(x1/world.CELL)+1):
            for y in range(math.floor(y0/world.CELL),math.floor(y1/world.CELL)+1):
                world.cells[x,y]=[0]
    return world


def flight_feet(case,t,config):
    # Independent target trajectory, evaluated at collision time rather than
    # reusing the bot's predictor. A landing ends the downward trajectory.
    z=case['feet']+case['vz']*t+.5*case['acceleration']*t*t
    return max(case['floor'],z)


def ray_hits(solution,case,world,config):
    if solution is None:
        return False
    yaw,pitch=solution[:2]
    direction=[math.cos(pitch)*math.cos(yaw),math.cos(pitch)*math.sin(yaw),math.sin(pitch)]
    gun=config['weapons']['gun']
    muzzle=[0.,0.,config['mech']['muzzle_height']]
    offset=config['mech']['radius']+.5
    origin=[muzzle[i]+offset*direction[i] for i in range(3)]
    velocity=[gun['speed']*v for v in direction]
    latency=.05
    rx=origin[0]-case['distance']
    ry=origin[1]-case['vy']*latency
    dx,dy=velocity[0],velocity[1]-case['vy']
    scale=1+config['cubes']['size_per_cube']*case['cubes']
    radius=config['mech']['radius']*scale+config['projectile']['gun_radius']
    a,b,c=dx*dx+dy*dy,2*(rx*dx+ry*dy),rx*rx+ry*ry-radius*radius
    discriminant=b*b-4*a*c
    if discriminant<0:
        return False
    lo=max(0.,(-b-math.sqrt(discriminant))/(2*a))
    hi=min(gun['range']/gun['speed'],(-b+math.sqrt(discriminant))/(2*a))
    if hi<lo:
        return False
    height=config['mech']['height']*scale
    # The horizontal cylinder crossing interval is short. Sample its vertical
    # overlap at sub-millisecond spacing, then verify the shot clears geometry.
    samples=max(20,math.ceil((hi-lo)/.0005))
    for i in range(samples+1):
        t=lo+(hi-lo)*i/samples
        point=[origin[j]+velocity[j]*t for j in range(3)]
        feet=flight_feet(case,t+latency,config)
        if feet-.3 <= point[2] <= feet+height+.3 and world.clear_ray(muzzle,point):
            return True
    return False


def cases(config):
    common=itertools.product
    gravity=config['mech']['gravity']
    jet=config['mech']['jet_accel']-gravity
    for distance,vy,cubes in common((60.,100.,150.,210.),(0.,11.7,19.5),(0,10)):
        yield dict(group='grounded',distance=distance,vy=vy,cubes=cubes,feet=0.,vz=0.,floor=0.,acceleration=0.)
    for group,floor,heights,velocities,acceleration in (
            ('rising',0.,(2.,12.,30.),(5.,10.),-gravity),
            ('falling',0.,(4.,12.,24.,40.),(-8.,-16.,-24.),-gravity),
            ('roof_landing',30.,(32.,40.,55.),(-8.,-16.,-24.),-gravity),
            ('jet_braking',0.,(12.,24.,40.),(-8.,-16.),jet)):
        for distance,vy,cubes,feet,vz in common((60.,100.,150.,210.),(0.,11.7,19.5),(0,10),heights,velocities):
            yield dict(group=group,distance=distance,vy=vy,cubes=cubes,feet=feet,vz=vz,floor=floor,acceleration=acceleration)


def main():
    with gzip.open(ROOT/'check/stream.jsonl.gz','rt') as f:
        messages=[json.loads(line) for line in f]
    hello=messages[0]
    hello['map']['dir']=str(ROOT/'arena')
    template=next(m for m in messages if m['type']=='obs')
    code=subprocess.check_output(['git','show',f'{BASELINE}:bot.py'],cwd=ROOT,text=True)
    baseline_module=types.ModuleType('trusted_repository_baseline')
    baseline_module.__file__=str(ROOT/'bot.py')
    exec(compile(code,'baseline_bot.py','exec'),baseline_module.__dict__)
    old,new=baseline_module.Bot(hello),Bot(hello)
    config=hello['config']
    summary={}
    fixed,missed=[],[]
    unchanged=True
    for case in cases(config):
        world=scene(case['distance'],case['floor'])
        enemy={'id':5,'kind':'mech','pos':[case['distance'],0.,case['feet']],
               'vel':[0.,case['vy'],case['vz']],'aim':[math.pi,0.],
               'hp':1400,'max_hp':1400,'cubes':case['cubes'],'weapons':['gun'],'charging':False}
        obs=copy.deepcopy(template)
        obs['self'].update(pos=[0.,0.,0.],vel=[0.,0.,0.])
        obs.update(events=[],crates=[],cubes=[],pickups=[],projectiles=[],sounds=[])
        solutions=[]
        for bot in (old,new):
            bot.world=world
            bot.enemies.clear()
            # Derive acceleration from two observations, as the live bot does.
            before=copy.deepcopy(enemy)
            before['vel'][2]=case['vz']-case['acceleration']*.1
            before['pos'][2]=case['feet']-case['vz']*.1+.5*case['acceleration']*.01
            obs.update(t=10.,mechs=[before])
            bot.remember(obs)
            obs.update(t=10.1,mechs=[enemy])
            bot.remember(obs)
            solutions.append(bot.firing_solution(obs['self'],enemy,obs['self']['weapons'][0]))
        a,b=[ray_hits(s,case,world,config) for s in solutions]
        row=summary.setdefault(case['group'],{'cases':0,'baseline_hits':0,'candidate_hits':0,'baseline_valid_aims':0,'candidate_valid_aims':0})
        row['cases']+=1
        row['baseline_hits']+=int(a);row['candidate_hits']+=int(b)
        row['baseline_valid_aims']+=int(solutions[0] is not None)
        row['candidate_valid_aims']+=int(solutions[1] is not None)
        if case['group'] in ('grounded','rising'):
            unchanged &= solutions[0]==solutions[1]
        detail=dict(case,baseline_hit=a,candidate_hit=b,
                    baseline_aim_height=round(solutions[0][2][2],3) if solutions[0] else None,
                    candidate_aim_height=round(solutions[1][2][2],3) if solutions[1] else None)
        if b and not a and len(fixed)<8: fixed.append(detail)
        if a and not b and len(missed)<8: missed.append(detail)
    print(json.dumps({'kind':'scripted gun-ray collision diagnostic; not damage or placement',
                      'baseline_ref':BASELINE,'candidate':new.name,'groups':summary,
                      'non_falling_solutions_unchanged':unchanged,
                      'example_corrected_shots':fixed,'example_regressions':missed},indent=2))
    if not unchanged:
        raise SystemExit('Unexpected change to a non-falling firing solution')


if __name__=='__main__':
    main()

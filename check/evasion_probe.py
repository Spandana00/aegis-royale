"""Paired horizontal-evasion experiment; NOT the game or a placement scorer.

Uses 20 Hz movement with bounded ground acceleration, 10 Hz decisions, and
scripted gun shooters. Omits buildings, vertical motion, outgoing damage,
upgrades, and house-bot decision logic. Both versions get identical scenarios.
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
from bot import Bot, intercept


class FlatWorld:
    def ground(self, x, y):
        return 0.

    def travel_clear(self, *args, **kwargs):
        return True

    def clear_ray(self, *args):
        return True


def segment_hits(a, b, previous, current, radius, height):
    rx, ry = a[0] - previous[0], a[1] - previous[1]
    dx = b[0] - a[0] - current[0] + previous[0]
    dy = b[1] - a[1] - current[1] + previous[1]
    aa, bb = dx * dx + dy * dy, 2 * (rx * dx + ry * dy)
    cc = rx * rx + ry * ry - radius * radius
    if aa < 1e-12:
        if cc > 0:
            return False
        lo, hi = 0., 1.
    else:
        discriminant = bb * bb - 4 * aa * cc
        if discriminant < 0:
            return False
        lo = max(0., (-bb - math.sqrt(discriminant)) / (2 * aa))
        hi = min(1., (-bb + math.sqrt(discriminant)) / (2 * aa))
        if lo > hi:
            return False
    dz = b[2] - a[2]
    if abs(dz) < 1e-12:
        return -.3 <= a[2] <= height + .3
    t0, t1 = (-.3 - a[2]) / dz, (height + .3 - a[2]) / dz
    return max(lo, min(t0, t1)) <= min(hi, max(t0, t1))


def play(bot, template, config, seed, shooters, duration):
    rng = random.Random(seed)
    obs = copy.deepcopy(template)
    me = obs['self']
    initial_angle = rng.uniform(-math.pi, math.pi)
    me.update(pos=[0., 0., 0.], vel=[11.7 * math.cos(initial_angle), 11.7 * math.sin(initial_angle), 0.],
              hp=1400, max_hp=1400, energy=100, grounded=True)
    me['weapons'][1] = None
    obs['zone'].update(center=[0., 0.], next_center=[0., 0.], radius=300, next_radius=200)
    bot.mode, bot.target_id = 'fight', 5
    bot.escaping_until, bot.last_move = -100., (0., 0.)
    bot.history.clear()
    bot.goal_id = None
    enemies = []
    gun = config['weapons']['gun']
    for i in range(shooters):
        a = (i - (shooters - 1) / 2) * .85
        distance = rng.uniform(90., 150.)
        enemies.append({'id':5+i, 'kind':'mech', 'pos':[distance*math.cos(a),distance*math.sin(a),0.],
                        'vel':[0.,0.,0.], 'aim':[a+math.pi,0.], 'hp':1400, 'max_hp':1400,
                        'cubes':0, 'weapons':['gun'], 'charging':False})
    bot.direct_ids = {e['id'] for e in enemies}
    magazines = [gun['mag']] * shooters
    cooldowns = [rng.uniform(0., gun['cooldown']) for _ in enemies]
    reloads = [0.] * shooters
    bullets, hits, shots, distance_sum = [], 0, 0, 0.
    moving, boosting, last_spend = [0.,0.], False, -100.
    dt = .05
    for tick in range(round(duration / dt)):
        now = tick * dt
        obs.update(tick=tick, t=now, mechs=enemies)
        obs['projectiles'] = [dict(id=i,kind='gun',pos=p[:],vel=v[:]) for i,(p,v,age) in enumerate(bullets)]
        if tick % 2 == 0:
            bot.history.append((now, me['pos'][:], math.hypot(*moving)))
            moving, boosting, jump = bot.steer(obs, enemies[0]['pos'], enemies, enemies[0])
        previous = me['pos'][:]
        previous_velocity = me['vel'][:]
        speed = me['stats']['boost_speed'] if boosting and me['energy'] > 0 else me['stats']['walk_speed']
        desired = [moving[0] * speed, moving[1] * speed]
        dx, dy = desired[0] - me['vel'][0], desired[1] - me['vel'][1]
        dv = math.hypot(dx, dy)
        fraction = min(1., me['stats']['ground_accel'] * dt / max(1e-9, dv))
        me['vel'][0] += dx * fraction
        me['vel'][1] += dy * fraction
        me['pos'][0] += me['vel'][0] * dt
        me['pos'][1] += me['vel'][1] * dt
        if boosting:
            me['energy'] = max(0., me['energy'] - me['stats']['boost_drain'] * dt)
            last_spend = now
        elif now - last_spend >= me['stats']['energy_regen_delay']:
            me['energy'] = min(100., me['energy'] + me['stats']['energy_regen'] * dt)
        distance_sum += math.dist(me['pos'][:2], enemies[0]['pos'][:2])
        for i, enemy in enumerate(enemies):
            if reloads[i] > 0:
                reloads[i] = max(0., reloads[i] - dt)
                if reloads[i] <= 1e-8:
                    magazines[i] = gun['mag']
                continue
            cooldowns[i] -= dt
            if cooldowns[i] > 0:
                continue
            origin = [*enemy['pos'][:2], 7.]
            aimpoint, flight = intercept(origin, [previous[0], previous[1], 4.5], previous_velocity, gun['speed'])
            dx, dy, dz = (aimpoint[j] - origin[j] for j in range(3))
            yaw = math.atan2(dy, dx) + math.radians(rng.gauss(0., gun['spread_deg']))
            pitch = math.atan2(dz, math.hypot(dx, dy)) + math.radians(rng.gauss(0., gun['spread_deg']))
            direction = [math.cos(pitch)*math.cos(yaw),math.cos(pitch)*math.sin(yaw),math.sin(pitch)]
            start = [origin[j] + 3. * direction[j] for j in range(3)]
            bullets.append((start, [gun['speed'] * v for v in direction], 0.))
            shots += 1
            magazines[i] -= 1
            cooldowns[i] += gun['cooldown']
            if magazines[i] == 0:
                reloads[i] = gun['reload']
        remaining = []
        for p,v,age in bullets:
            end = [p[j] + v[j] * dt for j in range(3)]
            if segment_hits(p, end, previous, me['pos'], me['stats']['radius'] + .3, me['stats']['height']):
                hits += 1
            elif age + dt < gun['range'] / gun['speed']:
                remaining.append((end, v, age + dt))
        bullets = remaining
    return {'shots':shots, 'hits':hits, 'mean_range':round(distance_sum / round(duration/dt),2)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', default='5209875b7f6f512de87b0411b6c44258cd113fbb')
    parser.add_argument('--seed', type=int, default=101)
    parser.add_argument('--dodge-scale', type=float, default=None)
    parser.add_argument('--legacy-motion', action='store_true')
    parser.add_argument('--trials', type=int, default=24)
    parser.add_argument('--seconds', type=float, default=12.)
    args = parser.parse_args()
    # Load the user's own earlier submitted source from this repository history.
    source = subprocess.check_output(['git','show',args.baseline_ref+':bot.py'],cwd=ROOT,text=True)
    baseline_module = types.ModuleType('evasion_baseline')
    baseline_module.__file__ = str(ROOT / 'bot.py')
    exec(compile(source, baseline_module.__file__, 'exec'), baseline_module.__dict__)
    with gzip.open(ROOT / 'check/stream.jsonl.gz','rt') as f:
        messages = [json.loads(line) for line in f]
    hello = messages[0]
    hello['map']['dir'] = str(ROOT / 'arena')
    template = next(m for m in messages if m['type']=='obs')
    baseline, candidate = baseline_module.Bot(hello), Bot(hello)
    legacy_motion = args.legacy_motion or not hasattr(candidate, 'dodge_scale')
    if not hasattr(candidate, 'dodge_scale'):
        candidate.dodge_scale = 1.
    if args.dodge_scale is not None:
        candidate.dodge_scale = args.dodge_scale
    if legacy_motion:
        old_cost = baseline_module.Bot.dodge_cost
        candidate.dodge_cost = lambda obs,vx,vy,x,y: old_cost(candidate,obs,vx,vy,x,y) * candidate.dodge_scale
    baseline.world = FlatWorld()
    candidate.world = FlatWorld()
    results = []
    for trial in range(args.trials):
        seed = args.seed + trial * 104729
        shooters = 1 + trial % 3
        first = play(baseline, template, hello['config'], seed, shooters, args.seconds)
        second = play(candidate, template, hello['config'], seed, shooters, args.seconds)
        results.append({'seed':seed,'shooters':shooters,'baseline':first,'candidate':second})
    a = sum(x['baseline']['hits'] for x in results)
    b = sum(x['candidate']['hits'] for x in results)
    report = {'kind':'paired horizontal-evasion diagnostic; not a game or placement score',
              'baseline_ref':args.baseline_ref,'candidate':candidate.name,'seed':args.seed,
              'trials':args.trials,'seconds_per_trial':args.seconds,'dodge_scale':candidate.dodge_scale,
              'motion_model':'legacy' if legacy_motion else 'acceleration limited',
              'baseline_hits':a,'candidate_hits':b,
              'hit_reduction_pct':round(100 * (a-b) / max(1,a),2),
              'cases':results}
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()

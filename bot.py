"""AEGIS: survival, opportunity, and accurate fire for mechfight/1."""
import math
import random
from collections import deque
from pathlib import Path

import mechfight as mf
from aiming import AimLearner
from navigation import Navigator
from world import World


TAU = 2 * math.pi


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def angle(x):
    return (x + math.pi) % TAU - math.pi


def unit(x, y):
    d = math.hypot(x, y)
    return (x / d, y / d) if d > 1e-6 else (0., 0.)


def intercept(origin, target, velocity, speed):
    """Earliest positive constant-velocity intercept, no shooter-velocity inheritance."""
    r = [target[i] - origin[i] for i in range(3)]
    a = sum(v * v for v in velocity) - speed * speed
    b = 2 * sum(r[i] * velocity[i] for i in range(3))
    c = sum(v * v for v in r)
    if abs(a) < 1e-9:
        t = -c / b if b < -1e-9 else math.sqrt(c) / speed
    else:
        det = b * b - 4 * a * c
        roots = [(-b - math.sqrt(det)) / (2 * a), (-b + math.sqrt(det)) / (2 * a)] if det >= 0 else []
        positive = [v for v in roots if v >= 0]
        t = min(positive) if positive else math.sqrt(c) / speed
    t = clamp(t, 0., 2.)
    return [target[i] + velocity[i] * t for i in range(3)], t


def future_zone(zone, now, ahead):
    """obs.center/radius already interpolate; only interpolate the remaining shrink."""
    start = max(now, zone['shrink_start'])
    f = clamp((now + ahead - start) / max(.01, zone['shrink_end'] - start), 0., 1.)
    c = [zone['center'][i] + f * (zone['next_center'][i] - zone['center'][i]) for i in range(2)]
    r = zone['radius'] + f * (zone['next_radius'] - zone['radius'])
    return c, r


class Bot:
    name = 'AEGIS v8'

    def __init__(self, hello):
        self.config = hello['config']
        self.rng = random.Random(hello['seed'])
        directory = hello['map']['dir']
        if not (Path(directory) / 'v2/world.json').exists():
            directory = str(Path(__file__).parent / 'arena')
        self.world = World(directory)
        self.nav = Navigator(self.world)
        self.items = {key: {} for key in ('crates', 'cubes', 'pickups')}
        self.enemies = {}
        self.history = deque(maxlen=18)
        self.goal = None
        self.goal_id = None
        self.mode = 'explore'
        self.target_id = None
        self.last_harm = -100.
        self.last_combat = -100.
        self.strafe = self.rng.choice((-1, 1))
        self.phase = self.rng.random() * TAU
        self.cover_goal = None
        self.cover_time = -100.
        self.last_move = (0., 0.)
        self.escaping_until = -100.
        self.loot_blacklist = {}
        self.scan_yaw = None
        self.direct_ids = set()
        self.aim_learner = AimLearner()

    def reachable_cell(self, pos, goal):
        start = self.nav.nearest(*pos[:2])
        component = self.nav.components[start] if start is not None else None
        return self.nav.nearest(*goal[:2], component=component)

    def remember(self, obs):
        now, me = obs['t'], obs['self']
        for group, saved in self.items.items():
            seen = {item['id'] for item in obs.get(group, [])}
            for item in obs.get(group, []):
                saved[item['id']] = (item, now)
            for iid, (item, last) in list(saved.items()):
                d = math.dist(item['pos'][:2], me['pos'][:2])
                # Only invalidate missing objects where omnidirectional sensors
                # and an unobstructed eye ray guarantee we would see them.
                if iid not in seen and (now - last > 90 or (d < 33 and self.world.clear_ray(
                        [me['pos'][0], me['pos'][1], me['pos'][2] + me['stats'].get('eye_height', 8)],
                        [item['pos'][0], item['pos'][1], item['pos'][2] + 1.2]))):
                    del saved[iid]
        for event in obs.get('events', []):
            if event['type'] == 'damaged' and event.get('weapon') != 'zone':
                self.last_harm = now
            if event['type'] in ('hit', 'damaged'):
                self.last_combat = now
            if event['type'] == 'took':
                self.items['pickups'].pop(event['id'], None)
            if event['type'] == 'hit':
                saved = self.items['crates'].get(event['target'])
                if saved and event['target'] not in {c['id'] for c in obs['crates']}:
                    item, last = saved
                    item['hp'] = item.get('hp', 300) - event['amount']
                    if item['hp'] <= 0:
                        self.items['crates'].pop(event['target'], None)
        for enemy in obs.get('mechs', []):
            self.enemies[enemy['id']] = (enemy, now)
        self.enemies = {i: v for i, v in self.enemies.items() if now - v[1] < 5.1}
        self.history.append((now, me['pos'][:], math.hypot(*self.last_move)))
        gun = next((w for w in me['weapons'] if w and w['kind'] == 'gun'), None)
        if gun:
            self.aim_learner.observe(obs, gun['stats']['speed'],
                                     self.config['cubes'].get('size_per_cube', .05),
                                     self.config['mech']['radius'])

    def enemy_center(self, enemy):
        scale = 1 + self.config['cubes'].get('size_per_cube', .05) * enemy.get('cubes', 0)
        h = self.config['npc']['height'] if enemy['kind'] == 'npc' else self.config['mech']['height'] * scale
        return [enemy['pos'][0], enemy['pos'][1], enemy['pos'][2] + h * .52]

    def firing_solution(self, me, target, weapon, adaptive=True):
        stats = weapon['stats']
        kind = weapon['kind']
        origin = [me['pos'][0], me['pos'][1], me['pos'][2] + me['stats'].get('muzzle_height', 7)]
        aimpoint = self.enemy_center(target) if 'kind' in target else [*target['pos'][:2], target['pos'][2] + 1.2]
        vel = list(target.get('vel', [0., 0., 0.]))
        # Account for the middle of the two simulation ticks in each action.
        aimpoint = [aimpoint[i] + vel[i] * .045 for i in range(3)]
        flight = 0.
        model_used = False
        if kind == 'gun':
            aimpoint, flight = intercept(origin, aimpoint, vel, stats['speed'])
            if adaptive and target.get('kind') == 'mech':
                forecast = self.aim_learner.predict(target, flight+.045)
                if forecast is not None:
                    model_used = True
                    center = self.enemy_center(target)
                    for _ in range(3):
                        forecast = self.aim_learner.predict(target, flight+.045)
                        aimpoint = [*forecast, center[2]+vel[2]*(flight+.045)]
                        flight = math.dist(origin, aimpoint)/stats['speed']
            if abs(vel[2]) > .8:
                aimpoint[2] = max(target['pos'][2] - 1., aimpoint[2] - .5 * self.config['mech']['gravity'] * flight ** 2)
        elif kind == 'mortar':
            origin[2] = me['pos'][2] + me['stats'].get('height', 9) + .5
            speed, gravity = stats['speed'], stats['gravity']
            base = aimpoint[:]
            for _ in range(4):
                dx, dy = aimpoint[0] - origin[0], aimpoint[1] - origin[1]
                d, dz = max(1., math.hypot(dx, dy) - 3.), aimpoint[2] - origin[2]
                disc = speed ** 4 - gravity * (gravity * d * d + 2 * dz * speed * speed)
                if disc < 0:
                    return None
                pitch = math.atan((speed * speed - math.sqrt(disc)) / (gravity * d))
                flight = d / max(1., speed * math.cos(pitch))
                aimpoint = [base[i] + vel[i] * min(3., flight) for i in range(3)]
            yaw = math.atan2(dy, dx)
            if not me['stats'].get('min_pitch', -.7) <= pitch <= me['stats'].get('max_pitch', 1.3):
                return None
            # Check the ballistic arc; a valid low arc must clear every wall.
            last = origin
            for i in range(1, 9):
                t = flight * i / 8
                point = [origin[0] + speed * math.cos(pitch) * math.cos(yaw) * t,
                         origin[1] + speed * math.cos(pitch) * math.sin(yaw) * t,
                         origin[2] + speed * math.sin(pitch) * t - .5 * gravity * t * t]
                if not self.world.clear_ray(last, point):
                    return None
                last = point
            if math.dist(me['pos'][:2], aimpoint[:2]) < stats.get('splash_radius', 7) + 9:
                return None
            return yaw, pitch, aimpoint, flight
        dx, dy, dz = (aimpoint[i] - origin[i] for i in range(3))
        distance = math.hypot(dx, dy)
        if math.sqrt(dx * dx + dy * dy + dz * dz) > stats.get('range', 230) + 2:
            if model_used:
                return self.firing_solution(me, target, weapon, False)
            return None
        yaw, pitch = math.atan2(dy, dx), math.atan2(dz, distance)
        if kind == 'lightning':
            pitch = clamp(pitch, me['stats'].get('min_pitch', -.7), me['stats'].get('max_pitch', 1.3))
        elif not me['stats'].get('min_pitch', -.7) <= pitch <= me['stats'].get('max_pitch', 1.3):
            if model_used:
                return self.firing_solution(me, target, weapon, False)
            return None
        if not self.world.clear_ray(origin, aimpoint):
            if model_used:
                baseline = self.firing_solution(me, target, weapon, False)
                if baseline is not None:
                    return baseline
            if kind not in ('gun', 'laser') or 'kind' not in target:
                return None
            target_height = (self.config['npc']['height'] if target['kind'] == 'npc' else
                             self.config['mech']['height'] * (1 + self.config['cubes'].get('size_per_cube', .05) * target.get('cubes', 0)))
            aimpoint[2] += target_height * .3
            pitch = math.atan2(aimpoint[2] - origin[2], distance)
            if not me['stats'].get('min_pitch', -.7) <= pitch <= me['stats'].get('max_pitch', 1.3) or not self.world.clear_ray(origin, aimpoint):
                return None
        return yaw, pitch, aimpoint, flight

    def choose_upgrade(self, obs):
        me = obs['self']
        ratio = me['hp'] / me['max_hp']
        weights = {'servos': 83, 'nanites': 82, 'plating': 88, 'armor': 86,
                   'reactor': 74, 'jets': 70, 'capacitor': 55, 'gyros': 39, 'sensors': 24,
                   'gun_damage': 94, 'gun_mag': 100, 'gun_rate': 75, 'gun_velocity': 78,
                   'laser_damage': 93, 'laser_charge': 88, 'laser_pierce': 35,
                   'lightning_range': 96, 'lightning_efficiency': 82, 'lightning_chain': 50,
                   'mortar_reload': 64, 'mortar_splash': 61, 'mortar_velocity': 44}
        if ratio < .5:
            weights['plating'] += 28
            weights['nanites'] += 10
        if obs['zone']['radius'] < 90:
            weights['armor'] += 12
            weights['nanites'] -= 20
        return max(range(len(obs['offer']['choices'])), key=lambda i: weights.get(obs['offer']['choices'][i]['id'], 30))

    def safe_goal(self, obs):
        pos, zone, now = obs['self']['pos'], obs['zone'], obs['t']
        center, radius = future_zone(zone, now, 12.)
        distance = math.dist(pos[:2], center)
        safe = max(0., radius - max(12., obs['self']['stats'].get('radius', 2.5) + 6.))
        urgent = distance > safe
        if urgent:
            # Move well inside, avoiding repeated stops exactly on the edge.
            inset = max(0., safe - 28.)
            ux, uy = unit(pos[0] - center[0], pos[1] - center[1])
            return [center[0] + ux * inset, center[1] + uy * inset], True
        return center, False

    def loot_score(self, obs, p, value, enemies):
        me, zone = obs['self'], obs['zone']
        d = math.dist(me['pos'][:2], p[:2])
        if abs(p[2] - me['pos'][2]) > 4.:
            return -1.
        c, r = future_zone(zone, obs['t'], d / max(8., me['stats']['walk_speed']) + 7.)
        if math.dist(p[:2], c) > r - 6:
            return -1.
        danger = sum(max(0., 1 - math.dist(p[:2], e['pos'][:2]) / 65.) for e in enemies)
        return value / (d + 16.) - danger * 2.5

    def choose_goal(self, obs, enemies, target, solutions):
        me, now = obs['self'], obs['t']
        pos, zone = me['pos'], obs['zone']
        safe, urgent = self.safe_goal(obs)
        ratio = me['hp'] / me['max_hp']
        exposed = [e for e in enemies if e['id'] in self.direct_ids]
        close = [e for e in exposed if math.dist(pos[:2], e['pos'][:2]) < 115]
        # Stay in recovery until substantially healed. The old policy resumed
        # firing at half health and repeatedly reset its own regeneration.
        recovering = (ratio < .5 or (self.mode == 'recover' and ratio < .88)
                      or (ratio < .72 and len(close) > 1))
        if target and len(close) <= 1 and target.get('hp', 1400) < min(220., me['hp'] * .3):
            recovering = False
        if urgent:
            self.mode, self.goal_id = 'zone', None
            return safe
        if recovering and (enemies or self.mode == 'recover'):
            self.mode, self.goal_id = 'recover', None
            if enemies:
                return self.find_cover(obs, exposed or enemies)
            return me['pos'][:2]
        best, goal, gid, mode = .22, None, None, 'explore'
        secondary = next((w for w in me['weapons'] if w and w['kind'] != 'gun'), None)
        for iid, (item, last) in self.items['cubes'].items():
            if self.loot_blacklist.get(iid, 0) > now:
                continue
            value = 105. if me.get('cubes', 0) < 10 else 50.
            score = self.loot_score(obs, item['pos'], value, close)
            if self.goal_id == iid:
                score *= 1.16
            if score > best:
                best, goal, gid, mode = score, item['pos'], iid, 'cube'
        preference = {'lightning': 1., 'laser': .85, 'mortar': .35, 'gun': 0.}
        held = preference.get(secondary['kind'], 0) if secondary else 0
        for iid, (item, last) in self.items['pickups'].items():
            improvement = preference[item['kind']] - held
            if improvement <= .1 or self.loot_blacklist.get(iid, 0) > now:
                continue
            score = self.loot_score(obs, item['pos'], 130. * improvement, close)
            if score > best:
                best, goal, gid, mode = score, item['pos'], iid, 'weapon'
        for drop in obs.get('drops', []):
            d = math.dist(pos[:2], drop['pos'][:2])
            if drop['lands_in'] > d / me['stats']['walk_speed'] + 7:
                continue
            if drop['holder'] not in (None, me['id']) and drop['progress'] > 1.:
                continue
            value = 150. + 140. * (1 - ratio)
            score = self.loot_score(obs, drop['pos'], value, close)
            if score > best:
                best, goal, gid, mode = score, drop['pos'], drop['id'], 'drop'
        if ratio < .48 and enemies and min(math.dist(e['pos'][:2], me['pos'][:2]) for e in enemies) < 155:
            if mode != 'drop' or goal is None or math.dist(me['pos'][:2], goal[:2]) > 18:
                self.mode, self.goal_id = 'recover', None
                return self.find_cover(obs, enemies)
        if not close and ratio > .72:
            for iid, (item, last) in self.items['crates'].items():
                if self.loot_blacklist.get(iid, 0) > now:
                    continue
                score = self.loot_score(obs, item['pos'], 47., enemies)
                if score > best:
                    best, goal, gid, mode = score, item['pos'], iid, 'crate'
        # A lone pursuer is an opportunity; preserve distance from groups.
        if target and target['kind'] == 'mech' and solutions:
            d = math.dist(pos[:2], target['pos'][:2])
            if len(close) <= 1 and ratio > .5 and (goal is None or d < 65 or best < 1.1):
                self.mode, self.goal_id = 'fight', target['id']
                return target['pos'][:2]
        if target and target['kind'] == 'npc' and not close and ratio > .72:
            self.mode, self.goal_id = 'farm', target['id']
            return target['pos'][:2]
        if goal is not None:
            self.mode, self.goal_id = mode, gid
            if mode == 'crate':
                ux, uy = unit(me['pos'][0] - goal[0], me['pos'][1] - goal[1])
                return [goal[0] + ux * 18., goal[1] + uy * 18.]
            return list(goal[:2])
        if len(close) >= 2:
            self.mode, self.goal_id = 'cover', None
            return self.find_cover(obs, enemies)
        # Explore the safe circle without collapsing immediately to its center.
        self.mode, self.goal_id = 'explore', None
        if self.goal and math.dist(pos[:2], self.goal) > 13 and math.dist(self.goal, zone['next_center']) < max(20., zone['next_radius'] - 20):
            return self.goal
        direction = self.phase + math.floor(now / 18.) * 1.7
        radius = min(100., zone['next_radius'] * .4)
        goal = [zone['next_center'][0] + radius * math.cos(direction), zone['next_center'][1] + radius * math.sin(direction)]
        k = self.reachable_cell(me['pos'], goal)
        return list(self.nav.point(k)) if k is not None else safe

    def find_cover(self, obs, enemies):
        now, me = obs['t'], obs['self']
        if self.cover_goal and now - self.cover_time < 1.2 and math.dist(me['pos'][:2], self.cover_goal) > 6:
            return self.cover_goal
        pos = me['pos']
        center, radius = future_zone(obs['zone'], now, 12)
        best, goal = float('inf'), list(center)
        closest = sorted(enemies, key=lambda e: math.dist(e['pos'][:2], pos[:2]))[:3]
        for i in range(16):
            a = i * TAU / 16
            p = [pos[0] + 37. * math.cos(a), pos[1] + 37. * math.sin(a)]
            k = self.reachable_cell(pos, p)
            if k is None:
                continue
            p = list(self.nav.point(k))
            if math.dist(p, center) > max(0., radius - 10):
                continue
            h = self.world.ground(*p)
            cost = math.dist(p, pos[:2]) * .1
            for e in closest:
                dist = math.dist(p, e['pos'][:2])
                cost += 100. / (dist + 5.)
                if self.world.clear_ray(self.enemy_center(e), [p[0], p[1], h + me['stats'].get('height', 9) * .7]):
                    cost += 9. * max(.15, 1 - dist / 250.)
            if cost < best:
                best, goal = cost, p
        self.cover_goal, self.cover_time = goal, now
        return goal

    def choose_target(self, obs):
        me, now = obs['self'], obs['t']
        enemies = [e for e in obs['mechs'] if e['kind'] == 'mech']
        candidates = enemies[:]
        if not enemies and me['hp'] > me['max_hp'] * .65:
            candidates += [e for e in obs['mechs'] if e['kind'] == 'npc' and math.dist(e['pos'][:2], me['pos'][:2]) < 75]
        candidates.sort(key=lambda e: math.dist(e['pos'][:2], me['pos'][:2]))
        best, target, solutions = -1., None, {}
        self.direct_ids = set()
        for e in candidates[:6]:
            d = math.dist(me['pos'][:2], e['pos'][:2])
            available = {}
            for i, w in enumerate(me['weapons']):
                if w is None:
                    continue
                solution = self.firing_solution(me, e, w)
                if solution is not None:
                    available[i] = solution
            if not available:
                continue
            if any(me['weapons'][i]['kind'] != 'mortar' for i in available):
                self.direct_ids.add(e['id'])
            hp = max(1., e.get('hp', 1400))
            score = 1500 / (hp + 300) + 75. / (d + 30)
            if e['id'] == self.target_id:
                score += .6
            if e.get('charging'):
                score += .5
            if e['kind'] == 'npc':
                score *= .5
            if score > best:
                best, target, solutions = score, e, available
        self.target_id = target['id'] if target else None
        return enemies, target, solutions

    def enemy_lightning_range(self, target):
        """Conservative upper bound: every unlocked offer could be Tesla coil."""
        upgrade = next((u for u in self.config['upgrades'] if u['id'] == 'lightning_range'), None)
        count = sum(target.get('cubes', 0) >= n for n in self.config['cubes']['upgrade_thresholds'])
        reach = self.config['weapons']['lightning']['range']
        if upgrade:
            stack = min(count, upgrade.get('max', 0))
            for _ in range(stack):
                for effect in upgrade.get('effects', []):
                    if effect['path'] == 'weapons.lightning.range':
                        reach = reach * effect.get('mul', 1.) + effect.get('add', 0.)
        return reach

    def engagement_distance(self, obs, target):
        me = obs['self']
        secondary = next((w for w in me['weapons'] if w and w['kind'] != 'gun'), None)
        preferred = 100.
        if target and target.get('kind') == 'npc':
            preferred = 57.
        elif secondary and secondary['kind'] == 'laser':
            preferred = 145.
        elif secondary and secondary['kind'] == 'lightning':
            # Commit to the short-range weapon against an isolated opponent;
            # keep gun distance while outnumbered or short of energy.
            if len(self.direct_ids) <= 1 and me['energy'] > 20 and me['hp'] > .58 * me['max_hp']:
                preferred = secondary['stats']['range'] * .82
                if target and 'lightning' in target.get('weapons', []):
                    opposing = self.enemy_lightning_range(target)
                    dz = self.enemy_center(target)[2] - me['pos'][2] - me['stats'].get('muzzle_height', 7.)
                    horizontal = math.sqrt(max(0., secondary['stats']['range'] ** 2 - dz * dz))
                    if horizontal > opposing + 8.:
                        preferred = min(secondary['stats']['range'] - 4., horizontal - 2.)
            else:
                preferred = 92.
        if target and 'lightning' in target.get('weapons', []) and (not secondary or secondary['kind'] != 'lightning'):
            preferred = max(95., preferred)
        return min(preferred, max(18., obs['zone']['radius'] * .72))

    def dodge_cost(self, obs, vx, vy, x, y):
        me = obs['self']
        radius, height = me['stats'].get('radius', 2.5), me['stats'].get('height', 9.)
        risk = 0.
        for bullet in obs.get('projectiles', [])[:36]:
            p, v = bullet['pos'], bullet['vel']
            if bullet['kind'] == 'mortar':
                g = self.config['weapons']['mortar']['gravity']
                z = p[2] - me['pos'][2]
                det = v[2] ** 2 + 2 * g * max(-1., z)
                if det < 0:
                    continue
                t = (v[2] + math.sqrt(det)) / g
                if not 0 < t < 1.7:
                    continue
                d = math.hypot(p[0] + v[0] * t - x - vx * t, p[1] + v[1] * t - y - vy * t)
                risk += max(0., (11 + radius - d) / 6.) ** 2 * 5.
            else:
                rx, ry = p[0] - x, p[1] - y
                dx, dy = v[0] - vx, v[1] - vy
                t = clamp(-(rx * dx + ry * dy) / (dx * dx + dy * dy + 1e-6), 0., .8)
                z = p[2] + v[2] * t
                if me['pos'][2] - 1 < z < me['pos'][2] + height + 1:
                    d = math.hypot(rx + dx * t, ry + dy * t)
                    risk += max(0., radius + 1.2 - d) * (1.3 if bullet['kind'] == 'gun' else .4)
        return risk

    def steer(self, obs, waypoint, enemies, target):
        me, now = obs['self'], obs['t']
        pos, stats = me['pos'], me['stats']
        radius, height = stats.get('radius', 2.5), stats.get('height', 9)
        elevated = pos[2] > self.world.ground(*pos[:2]) + 3.
        ux, uy = unit(waypoint[0] - pos[0], waypoint[1] - pos[1])
        secondary = next((w for w in me['weapons'] if w and w['kind'] != 'gun'), None)
        preferred = self.engagement_distance(obs, target)
        fighting = self.mode in ('fight', 'farm') and target is not None
        standoff = None
        if fighting:
            ex, ey = target['pos'][0] - pos[0], target['pos'][1] - pos[1]
            d = math.hypot(ex, ey)
            rx, ry = unit(ex, ey)
            radial = clamp((d - preferred) / 24., -.9, .9)
            # Smooth changes of strafe direction frustrate linear leading without
            # spending energy on constant jumping or canceling horizontal speed.
            side = self.strafe * (1 if math.sin(now * 1.65 + self.phase) > -.2 else -1)
            # Keep following A* around a wall until the short approach is clear.
            approach = [pos[0] + rx * min(15., d), pos[1] + ry * min(15., d)]
            if d < preferred + 18 or self.world.travel_clear(pos, approach, radius + .35, height, elevated):
                ux, uy = unit(rx * radial - ry * side, ry * radial + rx * side)
                # V2's direction-only orbit caps retreat at about two thirds
                # of walking speed. Account for a pursuer's radial velocity
                # when maintaining distance denies its short-range weapon.
                if ('lightning' in target.get('weapons', []) and len(self.direct_ids) <= 1
                        and preferred > self.enemy_lightning_range(target) + 4.
                        and d < preferred + 20.):
                    velocity = target.get('vel', [0., 0., 0.])
                    incoming = velocity[0] * rx + velocity[1] * ry
                    standoff = rx, ry, side, incoming + .8 * (d - preferred)
        ratio = me['hp'] / me['max_hp']
        boost = (self.mode == 'zone' or (self.mode in ('recover', 'cover') and enemies)) and me['energy'] > 25
        if fighting and target:
            d = math.dist(pos[:2], target['pos'][:2])
            boost = me['energy'] > 58 and (d > preferred + 35 or d < preferred - 18)
        # Hysteresis avoids spending/recharging energy on alternate decisions.
        if now < self.escaping_until and me['energy'] > 20:
            boost = True
        elif boost:
            self.escaping_until = now + .65
        speed = stats['boost_speed'] if boost and me['grounded'] else stats['walk_speed']
        if any(w and w['kind'] == 'laser' and w.get('charge', 0) > 0 for w in me['weapons']):
            speed *= stats.get('charge_move_mult', .5)
        if standoff is not None:
            rx, ry, side, desired_radial = standoff
            radial_speed = clamp(desired_radial, -.97 * speed, .97 * speed)
            tangent_speed = math.sqrt(max(0., speed * speed - radial_speed * radial_speed)) * side
            ux, uy = unit(rx * radial_speed - ry * tangent_speed,
                          ry * radial_speed + rx * tangent_speed)
        center, zr = future_zone(obs['zone'], now, 1.2)
        best, move = float('inf'), (0., 0.)
        candidates = [(ux, uy)] + [(math.cos(i * TAU / 20), math.sin(i * TAU / 20)) for i in range(20)]
        goal_dist = math.dist(waypoint[:2], pos[:2])
        if goal_dist < 3 and self.mode in ('drop', 'recover', 'zone', 'crate') and not enemies:
            candidates.insert(0, (0., 0.))
        danger = sorted((e for e in enemies if e['id'] in self.direct_ids), key=lambda e: math.dist(e['pos'][:2], pos[:2]))[:4]
        for mx, my in candidates:
            vx, vy = mx * speed, my * speed
            px, py = pos[0] + vx * .62, pos[1] + vy * .62
            if not self.world.travel_clear(pos, (px, py), radius + .35, height, elevated):
                continue
            cost = (1 - mx * ux - my * uy) * 2.5
            if mx == 0 and my == 0:
                cost -= 4.
            edge = math.dist((px, py), center) - max(0., zr - radius - 2)
            current_edge = math.dist(pos[:2], center) - max(0., zr - radius - 2)
            if edge > 0:
                cost += min(100., max(0., edge - current_edge) * 3 + edge * .25) * (1 + obs['zone']['dps'] / 80.)
            cost += self.dodge_cost(obs, vx, vy, pos[0], pos[1])
            for e in danger:
                distance = math.dist((px, py), e['pos'][:2])
                if e['id'] != self.target_id or ratio < .5:
                    cost += max(0., 65 - distance) / 9.
                if 'lightning' in e.get('weapons', []) and (not secondary or secondary['kind'] != 'lightning'):
                    cost += max(0., 58 - distance) / 5.
                if e.get('charging'):
                    ex, ey = px - e['pos'][0], py - e['pos'][1]
                    line_dist = abs(ex * math.sin(e['aim'][0]) - ey * math.cos(e['aim'][0]))
                    if ex * math.cos(e['aim'][0]) + ey * math.sin(e['aim'][0]) > 0:
                        cost += max(0., radius + 3 - line_dist) * 1.8
            if cost < best:
                best, move = cost, (mx, my)
        # A long look-ahead can reject every direction at a tight corner even
        # though the next actual step is safe. Creep to the turn before jumping.
        if best == float('inf'):
            for mx, my in candidates:
                px, py = pos[0] + mx * speed * .13, pos[1] + my * speed * .13
                if self.world.travel_clear(pos, (px, py), radius + .08, height, elevated):
                    cost = 1 - mx * ux - my * uy
                    if cost < best:
                        best, move = cost, (mx, my)
        trying = goal_dist > 8 or fighting
        stuck = (trying and len(self.history) >= 14 and now - self.history[0][0] > 1.1
                 and math.dist(pos[:2], self.history[0][1][:2]) < 2.5)
        jump = False
        if stuck:
            if move == (0., 0.):
                move = (ux, uy)
            if self.goal_id is not None and now - self.nav.planned < .3:
                self.loot_blacklist[self.goal_id] = now + 9.
            jump = me['grounded'] and me['energy'] > 25
            if not me['grounded'] and me['vel'][2] < 4 and me['energy'] > 35:
                boost = True
            self.nav.planned = -100.
        # Hop only under immediate fire, at most every 2.4 seconds. Reserve jets
        # for clearing obstacles; flying continuously drains the escape budget.
        if me['grounded'] and enemies and me['energy'] > 45 and obs['projectiles'] and int(now * 10) % 24 == 0:
            jump = True
        return list(move), bool(boost and (not me['grounded'] or move != (0., 0.))), bool(jump)

    def engage(self, obs, target, solutions, action):
        """Schedule independent triggers around one real, shared torso direction."""
        me = obs['self']
        slots = me['weapons']
        d = max(1., math.dist(me['pos'][:2], target['pos'][:2]))
        scale = 1 + self.config['cubes'].get('size_per_cube', .05) * target.get('cubes', 0)
        if target.get('kind') == 'npc':
            radius, height = self.config['npc']['radius'], self.config['npc']['height']
        elif 'kind' in target:
            radius, height = self.config['mech']['radius'] * scale, self.config['mech']['height'] * scale
        else:
            radius, height = self.config['crates']['radius'], self.config['crates']['height']
        gun = next((i for i in solutions if slots[i]['kind'] == 'gun'), None)
        laser = next((i for i in solutions if slots[i]['kind'] == 'laser'), None)
        mortar = next((i for i in solutions if slots[i]['kind'] == 'mortar'), None)
        gun_ready = gun is not None and slots[gun].get('ammo', 0) > 0 and slots[gun].get('reload', 0) <= .05
        chosen = gun if gun is not None else next(iter(solutions))
        laser_release = False
        if laser is not None:
            w = slots[laser]
            fraction = min(1., w.get('charge', 0) / max(.01, w['stats']['charge']))
            cube_mult = 1 + self.config['cubes'].get('damage_per_cube', .04) * min(me.get('cubes', 0), self.config['cubes'].get('stat_cap', 10))
            damage = w['stats']['damage'] * (.35 + .65 * fraction) * cube_mult
            if 'mortar' in target.get('weapons', []):
                damage *= 1 + w['stats'].get('cookoff', .6)
            laser_release = w.get('charge', 0) > 0 and (fraction >= .97 or target.get('hp', 1400) < damage * .9)
            # Charge while the gun tracks its projectile intercept. Only the
            # release needs the hitscan direction, and a full charge can wait.
            if laser_release or not gun_ready:
                chosen = laser
        mortar_due = mortar is not None and slots[mortar]['cooldown'] <= .05
        if mortar_due and not laser_release:
            velocity = target.get('vel', [0, 0, 0])
            slow = math.hypot(*velocity[:2]) < 6.
            if not gun_ready or (slow and d > 60 and laser is None):
                chosen = mortar
        yaw, pitch, _, _ = solutions[chosen]
        action['aim'] = [yaw, pitch]
        for i, w in enumerate(slots):
            if w is None or i not in solutions:
                continue
            wy, wp, _, _ = solutions[i]
            yaw_error = abs(angle(wy - me['aim'][0]))
            pitch_error = abs(wp - me['aim'][1])
            kind = w['kind']
            if kind == 'lightning':
                # Lightning checks a yaw cone, independent of gun pitch and
                # projectile lead. A shared-pitch gate incorrectly disabled it.
                cone = math.radians(w['stats']['cone_deg']) * .48
                reserve = 8. if self.mode in ('recover', 'zone') else 1.
                action['fire'][i] = bool(yaw_error < cone and d < w['stats']['range'] - .5
                                         and me['energy'] >= w['stats']['energy'] + reserve)
                continue
            # Test alignment against the actual torso, not a broad turn-rate
            # allowance which permitted long-range shots many metres off target.
            aligned = (yaw_error <= math.atan2(radius * .9, d) + .012
                       and pitch_error <= math.atan2(height * .43, d) + .012)
            if kind == 'laser':
                charge = w.get('charge', 0)
                if charge > 0:
                    action['fire'][i] = not (laser_release and aligned and chosen == i)
                else:
                    safe_charge = (self.mode not in ('recover', 'zone', 'cover') and
                                   ('lightning' not in target.get('weapons', []) or d > 65))
                    useful = d > 48 or not gun_ready or target.get('hp', 1400) < 180
                    action['fire'][i] = bool(w['cooldown'] <= .05 and safe_charge and useful and yaw_error < .4)
            elif kind == 'mortar':
                action['fire'][i] = bool(aligned and chosen == i and w['cooldown'] <= .06)
            else:
                # Preserve gun fire while charging another weapon. Do not point
                # it at an incompatible hitscan/ballistic aim for an entire clip.
                compatible = abs(angle(wy - yaw)) < math.atan2(radius, d) + .035 and abs(wp - pitch) < math.atan2(height * .5, d) + .025
                action['fire'][i] = bool(aligned and compatible and w.get('reload', 0) <= 0 and w.get('ammo', 0) > 0)
        healing = self.mode == 'recover' or (self.mode == 'cover' and me['hp'] < me['max_hp'] * .7)
        if healing and obs['t'] - self.last_harm > 1.5:
            action['fire'] = [False, False]

    def act(self, obs):
        self.remember(obs)
        me, now = obs['self'], obs['t']
        action = {'tick': obs['tick'], 'fire': [False, False]}
        if obs.get('offer'):
            action['pick'] = self.choose_upgrade(obs)
        enemies, target, solutions = self.choose_target(obs)
        self.goal = self.choose_goal(obs, enemies, target, solutions)
        # Actively take nearby useful loot, even while fighting or rotating.
        preference = {'gun': 0, 'mortar': 1, 'laser': 3, 'lightning': 4}
        slots = me['weapons']
        held = {w['kind'] for w in slots if w}
        for pickup in sorted(obs.get('pickups', []), key=lambda p: -preference[p['kind']]):
            if pickup['kind'] in held or math.dist(pickup['pos'][:2], me['pos'][:2]) > self.config['loot']['pickup_radius'] - .15 or abs(pickup['pos'][2] - me['pos'][2]) > 4:
                continue
            empty = next((i for i, w in enumerate(slots) if w is None), None)
            if empty is not None:
                action['take'] = pickup['id']
                break
            old = next((i for i, w in enumerate(slots) if w['kind'] != 'gun'), 1)
            if preference[pickup['kind']] > preference[slots[old]['kind']] and not slots[old].get('charge', 0):
                action.update(take=pickup['id'], drop=old)
                break
        threats = [(e['pos'][0], e['pos'][1], 1.5 if self.mode in ('cover', 'recover') else .35) for e in enemies[:4]]
        waypoint = self.nav.waypoint(me['pos'], self.goal, now, obs['zone'], threats,
                                     me['stats'].get('radius', 2.5) + .3, me['stats'].get('height', 9))
        action['move'], action['boost'], action['jump'] = self.steer(obs, waypoint, enemies, target)
        self.last_move = action['move']
        # Safe farming: do not expose a healing mech just to damage a crate.
        if target is None and self.mode == 'crate' and now - self.last_harm > 6:
            saved = self.items['crates'].get(self.goal_id)
            if saved:
                target = saved[0]
                solutions = {i: s for i, w in enumerate(slots) if w and (s := self.firing_solution(me, target, w))}
        if target is not None and solutions:
            self.engage(obs, target, solutions, action)
        else:
            # Face a nearby attacker to protect rear armor; scan when safe.
            if enemies:
                nearest = min(enemies, key=lambda e: math.dist(me['pos'][:2], e['pos'][:2]))
                action['aim'] = [math.atan2(nearest['pos'][1] - me['pos'][1], nearest['pos'][0] - me['pos'][0]), 0.]
            else:
                sounds = [s for s in obs.get('sounds', []) if s['kind'] in ('gun', 'laser_charge', 'lightning', 'mortar') and s['dist'] != 'far']
                if sounds:
                    self.scan_yaw = sounds[-1]['bearing']
                else:
                    self.scan_yaw = angle((self.scan_yaw if self.scan_yaw is not None else me['aim'][0]) + .14)
                action['aim'] = [self.scan_yaw, 0.]
        for w in slots:
            if w and w['kind'] == 'gun' and w.get('reload', 0) == 0:
                magazine = w['stats']['mag']
                if w.get('ammo', magazine) <= 0 or (target is None and w.get('ammo', magazine) < magazine * .7):
                    action['reload'] = True
        mf.draw.label(f"{self.mode} hp={int(me['hp'])} target={self.target_id}")
        return action


if __name__ == '__main__':
    mf.run(Bot)

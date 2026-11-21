"""Bounded online comparison of horizontal target-motion forecasts.

Independent implementation inspired by virtual-gun model comparison; see
docs/GITHUB_RESEARCH.md. Scores are forecast errors, not game hit statistics.
"""
from collections import deque
import math

MODEL_NAMES = ('linear', 'circular')


def forecasts(pos, vel, turn, seconds):
    t = max(0., min(1.5, seconds))
    x, y = pos[:2]
    vx, vy = vel[:2]
    linear = (x + vx*t, y + vy*t)
    if abs(turn) < 1e-4:
        circular = linear
    else:
        a = turn*t
        s, c = math.sin(a), math.cos(a)
        circular = (x + (vx*s + vy*(c-1.))/turn,
                    y + (vx*(1.-c) + vy*s)/turn)
    return linear, circular


class AimLearner:
    MAX_TRACKS = 16
    MAX_PENDING = 12

    def __init__(self):
        self.tracks = {}
        self.now = -100.

    def observe(self, obs, gun_speed, size_per_cube, base_radius):
        now, me = obs['t'], obs['self']
        self.now = now
        self.tracks = {i: tr for i, tr in self.tracks.items() if 0 <= now-tr['time'] < 2.}
        enemies = sorted((e for e in obs.get('mechs', []) if e['kind'] == 'mech'),
                         key=lambda e: math.dist(e['pos'][:2], me['pos'][:2]))[:6]
        for enemy in enemies:
            iid, pos = enemy['id'], enemy['pos']
            vel = enemy.get('vel', [0., 0., 0.])
            tr = self.tracks.get(iid)
            dt = now-tr['time'] if tr else 0.
            if tr is None or not .04 <= dt <= .26 or math.dist(pos[:2], tr['pos'][:2]) > 60.*dt+2.:
                tr = {'time':now, 'pos':pos[:], 'vel':vel[:], 'turn':0., 'turn_samples':0,
                      'errors':[0.]*2, 'samples':0, 'selected':0,
                      'issued':-100., 'pending':deque(maxlen=self.MAX_PENDING)}
                self.tracks[iid] = tr
            else:
                while tr['pending'] and tr['pending'][0][0] <= now:
                    due, predictions, axis, radius = tr['pending'].popleft()
                    if due < tr['time']:
                        continue
                    f = (due-tr['time'])/dt
                    actual = [tr['pos'][i] + f*(pos[i]-tr['pos'][i]) for i in range(2)]
                    for i, prediction in enumerate(predictions):
                        dx, dy = actual[0]-prediction[0], actual[1]-prediction[1]
                        lateral = dx*axis[1]-dy*axis[0]
                        radial = dx*axis[0]+dy*axis[1]
                        error = min(16., (lateral*lateral + .15*radial*radial)/(radius*radius))
                        tr['errors'][i] = error if tr['samples'] == 0 else .7*tr['errors'][i] + .3*error
                    tr['samples'] += 1
                if math.hypot(*vel[:2]) > 3. and math.hypot(*tr['vel'][:2]) > 3.:
                    change = (math.atan2(vel[1],vel[0])-math.atan2(tr['vel'][1],tr['vel'][0])+math.pi)%(2*math.pi)-math.pi
                    rate = max(-3., min(3., change/dt))
                    tr['turn_samples'] = tr['turn_samples']+1 if abs(rate)>.12 and rate*tr['turn']>0 else int(abs(rate)>.12)
                    tr['turn'] = .65*tr['turn'] + .35*rate
                else:
                    tr['turn'] = 0.
                    tr['turn_samples'] = 0
                tr.update(time=now, pos=pos[:], vel=vel[:])
                best = min(range(2), key=lambda i: tr['errors'][i])
                linear = tr['errors'][0]
                # Keep the scored linear baseline until an alternative has
                # enough observations and a material measured advantage.
                tr['selected'] = best if (tr['samples'] >= 6 and best != 0
                    and tr['turn_samples'] >= 3 and abs(tr['turn'])>.2
                    and tr['errors'][best]+.2 < linear and tr['errors'][best] < .75*linear) else 0
            if now-tr['issued'] >= .18:
                dx, dy = pos[0]-me['pos'][0], pos[1]-me['pos'][1]
                distance = math.hypot(dx, dy)
                horizon = max(.12, min(1.05, distance/max(1.,gun_speed)+.045))
                axis = (dx/max(1.,distance), dy/max(1.,distance))
                radius = max(1.,base_radius*(1+size_per_cube*enemy.get('cubes',0)))
                tr['pending'].append((now+horizon, forecasts(pos,vel,tr['turn'],horizon), axis, radius))
                tr['issued'] = now
        if len(self.tracks) > self.MAX_TRACKS:
            keep = sorted(self.tracks, key=lambda i:self.tracks[i]['time'], reverse=True)[:self.MAX_TRACKS]
            self.tracks = {i:self.tracks[i] for i in keep}

    def predict(self, enemy, seconds):
        tr = self.tracks.get(enemy['id'])
        if tr is None or self.now-tr['time'] > .21 or tr['selected'] == 0:
            return None
        return forecasts(enemy['pos'], enemy.get('vel',[0.,0.,0.]), tr['turn'], seconds)[tr['selected']]

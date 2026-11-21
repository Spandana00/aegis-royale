"""Observable regressions for the independently switchable V12 experiments."""
import copy
import gzip
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pilot import brain, navigate3
from pilot.state import EnemyThreat, Intent, Threats, WorldState


class FeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(ROOT / 'check/stream.jsonl.gz', 'rt') as f:
            rows = [json.loads(line) for line in f]
        cls.hello = rows[0]
        cls.obs = next(x for x in rows if x['type'] == 'obs')

    def setUp(self):
        saved = dict(brain.P)
        self.addCleanup(lambda: (brain.P.clear(), brain.P.update(saved)))
        brain.P.update(pickup_race=False, wide_band=False, focus_lock=False,
                       fight_boost=0., pursuit_range=False, predictive_move=False)

    def scenario(self):
        o = copy.deepcopy(self.obs)
        o.update(t=20., tick=400, mechs=[], pickups=[], crates=[], cubes=[], events=[],
                 projectiles=[], sounds=[], beams=[], drops=[], offer=None)
        o['self'].update(pos=[0., 0., 0.], vel=[0., 0., 0.], aim=[0., 0.], hp=1400.,
                         max_hp=1400., energy=100., grounded=True, cubes=0)
        o['self']['weapons'] = [{'kind': 'gun', 'ammo': 12, 'reload': 0., 'cooldown': 0.,
                                'stats': copy.deepcopy(self.hello['config']['weapons']['gun'])}, None]
        o['zone'].update(center=[0., 0.], next_center=[0., 0.], radius=500., next_radius=450.,
                         shrink_start=1000., shrink_end=1100.)
        s = WorldState(self.hello, None)
        s.update(o)
        e = EnemyThreat(id=5, kind='mech', pos=(80., 0., 0.), vel=(0., 0., 0.),
                        hp=1400., max_hp=1400., weapons=['gun'], dist=80., visible=True,
                        last_seen_t=20., los=True, can_hit_me=True, facing_me=True)
        return s, e

    def item(self, s, x=100.):
        p = {'id': 8001, 'kind': 'laser', 'pos': [x, 0., 0.]}
        s.obs['pickups'] = [p]
        brain._remember_items(s, brain._mem(s))
        return brain._mem(s)['items'][8001]

    def test_missing_pickup_needs_two_clear_views_and_reappearance_resets_it(self):
        s, e = self.scenario()
        s.arena = SimpleNamespace(los=lambda a, b: True)
        brain.P['pickup_race'] = True
        self.item(s)
        s.obs['pickups'] = []
        s.t = 21.
        brain._remember_items(s, brain._mem(s))
        self.assertIn(8001, brain._mem(s)['items'])
        s.obs['pickups'] = [{'id': 8001, 'kind': 'laser', 'pos': [100., 0., 0.]}]
        s.t = 22.
        brain._remember_items(s, brain._mem(s))
        s.obs['pickups'] = []
        s.t = 22.1
        brain._remember_items(s, brain._mem(s))
        self.assertIn(8001, brain._mem(s)['items'])
        s.t = 22.7
        brain._remember_items(s, brain._mem(s))
        self.assertNotIn(8001, brain._mem(s)['items'])

    def test_occlusion_and_rear_vision_do_not_erase_a_pickup(self):
        for yaw, line in [(math.pi, True), (0., False)]:
            s, e = self.scenario()
            s.arena = SimpleNamespace(los=lambda a, b: line)
            brain.P['pickup_race'] = True
            self.item(s)
            s.me['aim'] = [yaw, 0.]
            s.obs['pickups'] = []
            for t in (21., 22.):
                s.t = t
                brain._remember_items(s, brain._mem(s))
            self.assertIn(8001, brain._mem(s)['items'])

    def test_pickup_race_uses_fresh_same_level_rivals_without_that_weapon(self):
        s, e = self.scenario()
        brain.P['pickup_race'] = True
        item = self.item(s)
        tr = SimpleNamespace(kind='mech', dead=False, last_seen_t=s.t,
                             pos=(90., 0., 0.), weapons=['gun'])
        s.tracks[5] = tr
        self.assertTrue(brain._lost_pickup_race(s, item))
        tr.weapons.append('laser')
        self.assertFalse(brain._lost_pickup_race(s, item))
        tr.weapons = ['gun']
        tr.last_seen_t = s.t - 2.
        self.assertFalse(brain._lost_pickup_race(s, item))
        tr.last_seen_t = s.t
        tr.pos = (90., 0., 15.)
        self.assertFalse(brain._lost_pickup_race(s, item))

    def test_band_widens_a_gun_fight_and_preserves_lightning_reach(self):
        s, e = self.scenario()
        e.weapons = ['gun', 'laser']
        before = brain._desired_range(s, e)
        brain.P['wide_band'] = True
        self.assertGreater(brain._desired_range(s, e), before)
        s.me['weapons'][1] = {'kind': 'lightning'}
        self.assertEqual(brain._desired_range(s, e), 28.)

    def test_band_contracts_with_the_late_circle(self):
        s, e = self.scenario()
        e.weapons = ['laser']
        brain.P['wide_band'] = True
        s.zone.update(radius=40., next_radius=30.)
        self.assertLessEqual(brain._desired_range(s, e), 26.)

    def test_focus_keeps_a_comparable_target_but_yields_to_a_kill(self):
        s, e = self.scenario()
        other = copy.deepcopy(e)
        other.id = 6
        other.hp = 1350.
        th = Threats(enemies=[e, other], attackers=[5, 6])
        brain.P['focus_lock'] = True
        brain._mem(s)['focus_id'] = 5
        got = brain._assess_fight(s, th, th.enemies, {5, 6})
        self.assertEqual(got['target'].id, 5)
        brain.P['focus_lock'] = False
        unchanged = brain._assess_fight(s, th, [e], {5, 6})
        # Focus changes ranking, never the selected target's actual fight ratio.
        brain.P['focus_lock'] = True
        ratio = brain._assess_fight(s, th, [e], {5, 6})['ratio']
        self.assertAlmostEqual(ratio, unchanged['ratio'])
        other.hp = 40.
        self.assertEqual(brain._assess_fight(s, th, th.enemies, {5, 6})['target'].id, 6)

    def test_pursuit_compensates_closing_speed_with_a_unit_movement(self):
        s, e = self.scenario()
        s.tracks[5] = SimpleNamespace(pos=(80., 0., 0.), vel=(-8., 0., 0.))
        it = Intent(mode='engage', target_id=5, desired_range=80.)
        m = navigate3._mem(s)
        brain.P['pursuit_range'] = True
        move = navigate3._engage_dir(s, it, m)
        self.assertAlmostEqual(math.hypot(*move), 1.)
        self.assertAlmostEqual(move[0] * navigate3._walk_speed(s), -8.)
        self.assertGreater(abs(move[1]), .1)
        brain.P['pursuit_range'] = False
        self.assertAlmostEqual(navigate3._engage_dir(s, it, m)[0], 0.)

    def test_combat_boost_is_grounded_and_preserves_charge_and_lightning_energy(self):
        s, e = self.scenario()
        s.tracks[5] = SimpleNamespace(pos=e.pos, vel=e.vel)
        it = Intent(mode='engage', target_id=5, desired_range=80.)
        brain.P['fight_boost'] = 40.
        self.assertTrue(navigate3.step(s, it, Threats()).boost)
        s.me['weapons'][1] = {'kind': 'laser', 'charge': .4}
        self.assertFalse(navigate3.step(s, it, Threats()).boost)
        s.me['weapons'][1] = {'kind': 'lightning'}
        s.energy = 55.
        self.assertFalse(navigate3.step(s, it, Threats()).boost)
        s.energy = 100.
        s.me['grounded'] = False
        self.assertFalse(navigate3.step(s, it, Threats()).boost)

    def test_predictive_move_steps_out_of_a_projected_bullet_path(self):
        from pilot.local_motion import choose
        s, e = self.scenario()
        e.last_seen_t = s.t
        s.tracks[5] = e
        s.obs['projectiles'] = [{'id': 1, 'kind': 'gun', 'pos': [110., 0., 4.5],
                                 'vel': [-252., 0., 0.]}]
        it = Intent(mode='engage', target_id=5, desired_range=80.)
        direction = choose(s, it, Threats(), (1., 0.), 0)
        self.assertGreater(abs(direction[1]), .5)
        self.assertLessEqual(math.hypot(*direction), 1.00001)
        self.assertLessEqual(s.scratch['motion']['candidates'], 9)

    def test_predictive_move_respects_the_circle_and_airborne_routes(self):
        from pilot.local_motion import choose
        s, e = self.scenario()
        e.last_seen_t = s.t
        s.pos = (24., 0., 0.)
        s.tracks[5] = e
        s.zone.update(radius=30., next_radius=30.)
        it = Intent(mode='engage', target_id=5, desired_range=40.)
        direction = choose(s, it, Threats(), (1., 0.), 0)
        self.assertLessEqual(direction[0], 0.)
        s.me['grounded'] = False
        self.assertIsNone(choose(s, it, Threats(), (1., 0.), 0))


if __name__ == '__main__':
    unittest.main()

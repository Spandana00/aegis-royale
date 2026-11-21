"""Scenario regressions for interacting firing, cover and collection decisions."""
import copy
from types import SimpleNamespace
import unittest

import test_v12 as fixtures
from pilot import brain, combat, tactics
from pilot.state import Intent, Threats


class DiagnosisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.FeatureTests.setUpClass()

    def setUp(self):
        saved = dict(brain.P)
        self.addCleanup(lambda: (brain.P.clear(), brain.P.update(saved)))
        brain.P.update(arm_commit=False, fight_boost=0., cover_all=False,
                       final_fire=False, combat_cube=False, critical_recover=False)
        self.s, self.e = fixtures.FeatureTests().scenario()
        self.th = Threats(enemies=[self.e], attackers=[self.e.id])

    def test_laser_release_rechecks_gun_against_the_final_hitscan_aim(self):
        s, e = self.s, self.e
        e.pos, e.dist, e.vel, e.hp = (120., 0., 0.), 120., (0., 15., 0.), 100.
        s.me['weapons'][0]['stats']['damage'] = 150.
        s.me['weapons'][1] = {'kind': 'laser', 'charge': .3, 'cooldown': 0.,
                             'stats': copy.deepcopy(fixtures.FeatureTests.hello['config']['weapons']['laser'])}
        me = combat._Me(s)
        tg = combat._targets(s, Intent(), self.th, me, {})[0]
        s.me['aim'] = list(combat.laser_solution(me, tg)[:2])
        intent = Intent(mode='engage', target_id=e.id)
        before = combat.step(s, intent, self.th)
        self.assertTrue(before.fire[0])
        self.assertEqual(before.reason, 'laser-early')
        brain.P['final_fire'] = True
        s.scratch.pop('combat', None)
        after = combat.step(s, intent, self.th)
        self.assertFalse(after.fire[0])
        self.assertEqual(after.aim, before.aim)
        self.assertEqual(after.fire[1], before.fire[1])
        self.assertEqual(s.scratch['combat']['final_gun_veto'], 1)

    def test_an_aligned_gun_shot_is_retained(self):
        brain.P['final_fire'] = True
        out = combat.step(self.s, Intent(mode='engage', target_id=self.e.id), self.th)
        self.assertTrue(out.fire[0])

    def test_cover_checks_three_threats_and_invalidates_the_cache_when_the_pack_changes(self):
        s = self.s
        calls = []
        def nearest(pos, threats, distance):
            calls.append(threats)
            return (-5., 0., 0.)
        s.arena = SimpleNamespace(nearest_cover=nearest)
        brain.P['cover_all'] = True
        pack = [(80., 0., 0.), (0., 90., 0.), (-100., 0., 0.), (0., -140., 0.)]
        brain._cover_from(s, pack, {})
        self.assertEqual(set(calls[-1]), set(pack[:3]))
        brain._cover_from(s, pack, {})
        self.assertEqual(len(calls), 1)
        pack[1] = (0., 70., 0.)
        brain._cover_from(s, pack, {})
        self.assertEqual(len(calls), 2)

    def test_short_cube_detour_retains_firing_and_the_selected_target(self):
        s, e = self.s, self.e
        m = brain._mem(s)
        m['items'][5001] = {'id': 5001, 'type': 'cube', 'pos': (8., 0., 0.), 't': s.t}
        fight = {'verdict': 'engage', 'target': e}
        out = tactics.cube_detour(s, m, self.th, [e], fight, {})
        self.assertEqual(out.loot_id, 5001)
        self.assertEqual(out.target_id, e.id)
        self.assertTrue(out.allow_fire)
        self.assertTrue(combat.step(s, out, self.th).fire[0])

    def test_cube_detour_rejects_obstacles_danger_stale_loot_and_capped_scaling(self):
        s, e = self.s, self.e
        m = brain._mem(s)
        cube = {'id': 5001, 'type': 'cube', 'pos': (17., 0., 0.), 't': s.t}
        m['items'][5001] = cube
        fight = {'verdict': 'engage', 'target': e}
        s.arena = SimpleNamespace(size_class=lambda n: 0, walk_line=lambda *a: False)
        self.assertIsNone(tactics.cube_detour(s, m, self.th, [e], fight, {}))
        s.arena = None
        e.weapons = ['lightning', 'laser']; e.dist = 25.
        self.assertIsNone(tactics.cube_detour(s, m, self.th, [e], fight, {}))
        cube.update(pos=(8., 0., 0.), t=s.t-3.)
        self.assertIsNone(tactics.cube_detour(s, m, self.th, [e], fight, {}))
        cube['t'] = s.t
        s.me['cubes'] = 10
        self.assertIsNone(tactics.cube_detour(s, m, self.th, [e], fight, {}))

    def test_recovery_is_latched_and_requires_shelter(self):
        s, e = self.s, self.e
        m = brain._mem(s)
        s.hp = .24 * s.max_hp
        s.arena = SimpleNamespace(nearest_cover=lambda *a, **kw: None)
        fight = {'verdict': 'engage', 'target': e}
        self.assertIsNone(tactics.recovery(s, m, self.th, [e], fight, {}))
        s.t += 3.
        s.arena.nearest_cover = lambda *a, **kw: (-10., 0., 0.)
        out = tactics.recovery(s, m, self.th, [e], fight, {})
        self.assertFalse(out.allow_fire)
        s.hp = .5 * s.max_hp
        self.assertIsNotNone(tactics.recovery(s, m, self.th, [e], fight, {}))
        s.hp = .6 * s.max_hp
        self.assertIsNone(tactics.recovery(s, m, self.th, [e], fight, {}))
        self.assertNotIn('critical', m)

    def test_recovery_does_not_run_from_a_close_or_killable_attacker(self):
        s, e = self.s, self.e
        m = brain._mem(s)
        s.hp = .2 * s.max_hp
        s.arena = SimpleNamespace(nearest_cover=lambda *a, **kw: (-10., 0., 0.))
        fight = {'verdict': 'engage', 'target': e}
        e.dist = 30.
        self.assertIsNone(tactics.recovery(s, m, self.th, [e], fight, {}))
        e.dist = 80.
        self.th.killable = [e.id]
        self.assertIsNone(tactics.recovery(s, m, self.th, [e], fight, {}))


if __name__ == '__main__':
    unittest.main()

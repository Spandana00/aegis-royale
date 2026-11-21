"""Tactical regression tests with the real map and recorded rule set."""
import copy
import gzip
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bot import Bot, angle, future_zone, intercept
from world import Prism


class GeometryTests(unittest.TestCase):
    def test_wall_roof_courtyard_bridge(self):
        p = Prism({'base': 10, 'top': 20, 'ring': [0,0,20,0,20,20,0,20], 'holes': [[5,5,15,5,15,15,5,15]]})
        self.assertFalse(p.ray_hits([-10,2,5],[30,2,5]))  # below bridge
        self.assertTrue(p.ray_hits([-10,2,15],[30,2,15]))
        self.assertFalse(p.ray_hits([7,7,15],[13,13,15])) # courtyard
        self.assertTrue(p.ray_hits([2,2,30],[2,2,0]))    # through roof
        self.assertFalse(p.overlaps(10,10,2))
        self.assertTrue(p.overlaps(5.5,10,2))

    def test_lead_hits_crossing_target(self):
        origin, target, vel = [0,0,7], [100,0,5], [0,19.5,0]
        predicted, t = intercept(origin, target, vel, 252)
        self.assertGreater(predicted[1], 7)
        self.assertAlmostEqual(math.dist(origin, predicted), 252*t, places=7)
        self.assertAlmostEqual(predicted[1], vel[1]*t)

    def test_shrink_is_not_interpolated_twice(self):
        z = {'center':[50,0], 'radius':100, 'next_center':[0,0], 'next_radius':0,
             'shrink_start':0,'shrink_end':100}
        c, r = future_zone(z, 50, 25)
        self.assertEqual(c, [25,0])
        self.assertEqual(r, 50)
        c, r = future_zone(z, 50, 70)
        self.assertEqual((c,r), ([0,0],0))


class TacticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(ROOT/'check/stream.jsonl.gz','rt') as f:
            messages = [json.loads(line) for line in f]
        cls.hello = messages[0]
        cls.hello['map']['dir'] = str(ROOT/'arena')
        cls.initial = next(m for m in messages if m['type']=='obs')
        cls.bot = Bot(cls.hello)
        # Select an open stretch of the actual campus, away from map edges.
        w = cls.bot.world
        cls.start = None
        for x in range(-100,400,10):
            for y in range(-150,250,10):
                z = w.ground(x,y)
                if w.free(x,y,z) and w.travel_clear([x,y,z],[x+100,y]) and w.free(x+100,y):
                    if w.clear_ray([x,y,z+7],[x+100,y,w.ground(x+100,y)+4.5]):
                        cls.start = [x,y,z]
                        break
            if cls.start:
                break
        assert cls.start is not None

    def scenario(self):
        o = copy.deepcopy(self.initial)
        o['self']['pos'] = self.start[:]
        o['self']['aim'] = [0.,0.]
        o['zone'].update(center=self.start[:2], next_center=self.start[:2],radius=300,next_radius=200)
        return o

    def enemy(self, o, distance=80, **kwargs):
        x,y,z = o['self']['pos']
        e = {'id':5,'kind':'mech','pos':[x+distance,y,self.bot.world.ground(x+distance,y)],
             'vel':[0,0,0],'aim':[math.pi,0],'hp':1400,'max_hp':1400,'cubes':0,'weapons':['gun'],'charging':False}
        e.update(kwargs)
        return e

    def weapon(self, kind):
        return {'kind':kind,'cooldown':0.,'stats':copy.deepcopy(self.hello['config']['weapons'][kind])}

    def test_gun_aims_at_torso_and_leads(self):
        o=self.scenario();e=self.enemy(o,vel=[0,15,0])
        sol=self.bot.firing_solution(o['self'],e,o['self']['weapons'][0])
        self.assertIsNotNone(sol)
        self.assertGreater(sol[0],.04)
        self.assertLess(abs(sol[1]),.15)

    def test_empty_gun_uses_available_cover(self):
        o=self.scenario();e=self.enemy(o);o['mechs']=[e]
        o['self']['weapons'][0].update(ammo=0,reload=2.)
        self.bot.mode='fight'
        x,y,z=o['self']['pos']
        with patch.object(self.bot,'reload_cover',return_value=[x,y+20]):
            self.bot.act(o)
        self.assertEqual(self.bot.mode,'reload')
        self.assertEqual(self.bot.goal,[x,y+20])

    def test_ready_lightning_keeps_attacking_during_gun_reload(self):
        o=self.scenario();e=self.enemy(o,distance=30);o['mechs']=[e]
        o['self']['weapons'][0].update(ammo=0,reload=2.)
        o['self']['weapons'][1]=self.weapon('lightning')
        self.bot.mode='fight'
        with patch.object(self.bot,'reload_cover') as cover:
            self.bot.act(o)
        cover.assert_not_called()
        self.assertEqual(self.bot.mode,'fight')

    def test_ready_laser_keeps_attacking_during_gun_reload(self):
        o=self.scenario();o['mechs']=[self.enemy(o)]
        o['self']['weapons'][0].update(ammo=0,reload=2.)
        o['self']['weapons'][1]=self.weapon('laser')
        self.bot.mode='fight'
        with patch.object(self.bot,'reload_cover') as cover:
            self.bot.act(o)
        cover.assert_not_called()

    def test_no_cover_retains_normal_combat_movement(self):
        o=self.scenario();o['mechs']=[self.enemy(o)]
        o['self']['weapons'][0].update(ammo=0,reload=2.)
        self.bot.mode='fight';self.bot.reload_checked=-100.
        with patch.object(self.bot.world,'clear_ray',return_value=True):
            a=self.bot.act(o)
        self.assertEqual(self.bot.mode,'fight')
        self.assertGreater(math.hypot(*a['move']),.5)

    def test_reload_cover_requires_upper_body_protection(self):
        o=self.scenario();e=self.enemy(o)
        self.bot.mode='fight';self.bot.reload_checked=-100.
        ground=self.bot.world.ground
        # A low wall hides the feet and center, but leaves the head exposed.
        def ray(a,b):
            return b[2] > ground(*b[:2]) + o['self']['stats']['height']*.8
        with patch.object(self.bot.world,'clear_ray',side_effect=ray):
            goal=self.bot.reload_cover(o,[e],2.4)
        self.assertIsNone(goal)

    def test_reload_does_not_override_zone_escape(self):
        o=self.scenario();x,y,z=o['self']['pos']
        o['zone'].update(center=[x-80,y],radius=100,next_center=[x-80,y],next_radius=25,shrink_start=0,shrink_end=20)
        o['self']['weapons'][0].update(ammo=0,reload=2.)
        self.bot.mode='fight'
        with patch.object(self.bot,'reload_cover') as cover:
            self.bot.act(o)
        cover.assert_not_called()
        self.assertEqual(self.bot.mode,'zone')

    def test_covered_reload_holds_position(self):
        o=self.scenario()
        self.bot.mode='reload'
        self.assertEqual(self.bot.reload_cover(o,[],2.),o['self']['pos'][:2])

    def test_covered_reload_stops_with_a_tracked_enemy(self):
        o=self.scenario();e=self.enemy(o)
        self.bot.mode='reload'
        with patch.object(self.bot.world,'clear_ray',return_value=False):
            self.assertEqual(self.bot.reload_cover(o,[e],2.),o['self']['pos'][:2])

    def test_reload_starts_return_before_gun_is_loaded(self):
        o=self.scenario();e=self.enemy(o);o['mechs']=[e]
        x,y,z=o['self']['pos']
        o['self']['weapons'][0].update(ammo=0,reload=.8)
        self.bot.mode='reload';self.bot.reload_origin=[x,y+15]
        self.bot.direct_ids={e['id']}
        goal=self.bot.choose_goal(o,[e],None,{})
        self.assertEqual(self.bot.mode,'rejoin')
        self.assertEqual(goal,[x,y+15])

    def test_loaded_gun_does_not_finish_rejoin_when_target_is_available(self):
        o=self.scenario();e=self.enemy(o);o['mechs']=[e]
        x,y,z=o['self']['pos']
        self.bot.mode='rejoin';self.bot.reload_origin=[x,y+15]
        self.bot.rejoin_until=o['t']+2
        self.bot.direct_ids={e['id']}
        solution=self.bot.firing_solution(o['self'],e,o['self']['weapons'][0])
        self.bot.choose_goal(o,[e],e,{0:solution})
        self.assertEqual(self.bot.mode,'fight')

    def test_cooling_secondary_does_not_leave_empty_gun_exposed(self):
        o=self.scenario();o['mechs']=[self.enemy(o)]
        o['self']['weapons'][0].update(ammo=0,reload=2.)
        o['self']['weapons'][1]=self.weapon('laser')
        o['self']['weapons'][1]['cooldown']=1.4
        self.bot.mode='fight'
        with patch.object(self.bot,'reload_cover',return_value=o['self']['pos'][:2]):
            self.bot.act(o)
        self.assertEqual(self.bot.mode,'reload')

    def test_low_health_healing_takes_priority_over_reload_cover(self):
        o=self.scenario();o['mechs']=[self.enemy(o)];o['self']['hp']=400
        o['self']['weapons'][0].update(ammo=0,reload=2.)
        self.bot.mode='fight'
        with patch.object(self.bot,'reload_cover') as cover:
            self.bot.act(o)
        cover.assert_not_called()
        self.assertEqual(self.bot.mode,'recover')

    def test_gun_becomes_active_after_reload(self):
        o=self.scenario();e=self.enemy(o);o['mechs']=[e]
        self.bot.mode='reload'
        sol=self.bot.firing_solution(o['self'],e,o['self']['weapons'][0])
        o['self']['aim']=list(sol[:2])
        a=self.bot.act(o)
        self.assertEqual(self.bot.mode,'fight')
        self.assertTrue(a['fire'][0])

    def test_gun_waits_for_turn(self):
        o=self.scenario();o['mechs']=[self.enemy(o)];o['self']['aim']=[math.pi,0]
        a=self.bot.act(o)
        self.assertFalse(a['fire'][0])
        self.assertLess(abs(a['aim'][0]),.1)

    def test_fires_when_aligned(self):
        o=self.scenario();e=self.enemy(o);o['mechs']=[e]
        sol=self.bot.firing_solution(o['self'],e,o['self']['weapons'][0]);o['self']['aim']=list(sol[:2])
        a=self.bot.act(o)
        self.assertTrue(a['fire'][0])

    def test_laser_releases_full_charge(self):
        o=self.scenario();e=self.enemy(o);o['mechs']=[e]
        laser=self.weapon('laser');laser['charge']=laser['stats']['charge']
        o['self']['weapons'][1]=laser
        sol=self.bot.firing_solution(o['self'],e,laser);o['self']['aim']=list(sol[:2])
        a=self.bot.act(o)
        self.assertFalse(a['fire'][1])

    def test_lightning_does_not_waste_energy_out_of_range(self):
        o=self.scenario();o['mechs']=[self.enemy(o,distance=80)]
        o['self']['weapons'][1]=self.weapon('lightning')
        a=self.bot.act(o)
        self.assertFalse(a['fire'][1])

    def test_takes_pickup(self):
        o=self.scenario();o['pickups']=[{'id':8001,'kind':'lightning','pos':o['self']['pos'][:]}]
        a=self.bot.act(o)
        self.assertEqual(a.get('take'),8001)

    def test_early_reload(self):
        o=self.scenario();o['self']['weapons'][0]['ammo']=3
        a=self.bot.act(o)
        self.assertTrue(a.get('reload'))

    def test_capture_stands_in_ring(self):
        o=self.scenario();o['drops']=[{'id':20000,'pos':o['self']['pos'][:],'radius':8,'lands_in':0,'capture_s':4,'progress':1,'holder':3}]
        a=self.bot.act(o)
        self.assertEqual(a['move'],[0.,0.])

    def test_leaves_shrinking_edge(self):
        o=self.scenario();x,y,z=o['self']['pos']
        o['zone'].update(center=[x-80,y],radius=100,next_center=[x-80,y],next_radius=25,shrink_start=0,shrink_end=20)
        goal,urgent=self.bot.safe_goal(o)
        self.assertTrue(urgent)
        self.assertLess(goal[0],x-40)

    def test_low_health_breaks_contact(self):
        o=self.scenario();o['self']['hp']=400;o['mechs']=[self.enemy(o)]
        self.bot.last_harm=o['t']-3
        a=self.bot.act(o)
        self.assertEqual(self.bot.mode,'recover')
        self.assertEqual(a['fire'],[False,False])

    def test_rooftop_is_not_a_ground_destination(self):
        nav=self.bot.nav
        start=nav.nearest(-177.92,215.74)
        roof=nav.nearest(-202.38,206.91)
        self.assertNotEqual(nav.components[start],nav.components[roof])
        projected=nav.nearest(-202.38,206.91,component=nav.components[start])
        self.assertIsNotNone(projected)
        self.assertEqual(nav.components[projected],nav.components[start])

    def test_fast_close_target_does_not_silence_gun_with_ready_laser(self):
        o=self.scenario();e=self.enemy(o,distance=38,vel=[0,25,0]);o['mechs']=[e]
        o['self']['weapons'][1]=self.weapon('laser')
        sol=self.bot.firing_solution(o['self'],e,o['self']['weapons'][0])
        o['self']['aim']=list(sol[:2])
        a=self.bot.act(o)
        self.assertTrue(a['fire'][0], 'A ready close-range laser must not suppress an aligned gun.')

    def test_lightning_uses_yaw_cone_with_different_gun_pitch(self):
        o=self.scenario();e=self.enemy(o,distance=30,vel=[0,0,18]);o['mechs']=[e]
        o['self']['weapons'][1]=self.weapon('lightning')
        sol=self.bot.firing_solution(o['self'],e,o['self']['weapons'][0])
        o['self']['aim']=list(sol[:2])
        a=self.bot.act(o)
        self.assertTrue(a['fire'][1], 'Lightning has a yaw cone; it must not require matching gun pitch.')

    def test_recovery_does_not_end_at_half_health(self):
        o=self.scenario();o['self']['hp']=730;o['mechs']=[self.enemy(o)]
        self.bot.mode='recover';self.bot.last_harm=o['t']-3
        a=self.bot.act(o)
        self.assertEqual(self.bot.mode,'recover')
        self.assertEqual(a['fire'],[False,False])

    def test_aims_at_exposed_upper_body(self):
        o=self.scenario();e=self.enemy(o)
        threshold=e['pos'][2]+6.5
        with patch.object(self.bot.world,'clear_ray',side_effect=lambda a,b:b[2]>threshold):
            sol=self.bot.firing_solution(o['self'],e,o['self']['weapons'][0])
        self.assertIsNotNone(sol)
        self.assertGreater(sol[2][2],threshold)

    def test_lightning_reaches_high_target_without_pitch_gate(self):
        o=self.scenario();e=self.enemy(o,distance=6)
        e['pos'][2]=o['self']['pos'][2]+32
        o['self']['weapons'][1]=self.weapon('lightning')
        with patch.object(self.bot.world,'clear_ray',return_value=True):
            sol=self.bot.firing_solution(o['self'],e,o['self']['weapons'][1])
        self.assertIsNotNone(sol)

    def test_gun_keeps_tracking_during_laser_charge(self):
        o=self.scenario();e=self.enemy(o,distance=100,vel=[0,24,0]);o['mechs']=[e]
        laser=self.weapon('laser');laser['charge']=.4;o['self']['weapons'][1]=laser
        sol=self.bot.firing_solution(o['self'],e,o['self']['weapons'][0]);o['self']['aim']=list(sol[:2])
        a=self.bot.act(o)
        self.assertTrue(a['fire'][0])
        self.assertTrue(a['fire'][1])
        self.assertAlmostEqual(a['aim'][0],sol[0])

    def test_combat_follows_route_when_direct_approach_is_blocked(self):
        o=self.scenario();e=self.enemy(o,distance=180)
        self.bot.mode='fight';self.bot.target_id=e['id'];self.bot.direct_ids={e['id']}
        self.bot.phase=0.;self.bot.strafe=-1
        x,y,z=o['self']['pos']
        def clear(a,b,*args):
            return not (b[0] > x+1 and abs(b[1]-y)<1)
        with patch.object(self.bot.world,'travel_clear',side_effect=clear):
            move,boost,jump=self.bot.steer(o,[x,y+50],[e],e)
        self.assertGreater(move[1],.5)

    def test_can_creep_to_a_tight_corner(self):
        o=self.scenario();x,y,z=o['self']['pos']
        self.bot.mode='explore';self.bot.direct_ids=set();self.bot.history.clear()
        def clear(a,b,*args):
            return math.dist(a[:2],b[:2]) <= 2.
        with patch.object(self.bot.world,'travel_clear',side_effect=clear):
            move,boost,jump=self.bot.steer(o,[x,y+50],[],None)
        self.assertGreater(move[1],.5)

    def test_blocked_commands_still_trigger_escape(self):
        o=self.scenario();o['t']=3.;x,y,z=o['self']['pos']
        self.bot.mode='explore';self.bot.direct_ids=set();self.bot.history.clear()
        for i in range(18):
            self.bot.history.append((i*.1,[x,y,z],0.))
        with patch.object(self.bot.world,'travel_clear',return_value=False):
            move,boost,jump=self.bot.steer(o,[x,y+50],[],None)
        self.assertTrue(jump)
        self.assertGreater(move[1],.5)

    def test_does_not_charge_laser_inside_enemy_lightning_range(self):
        o=self.scenario();e=self.enemy(o,distance=55,weapons=['gun','lightning']);o['mechs']=[e]
        o['self']['weapons'][1]=self.weapon('laser')
        sol=self.bot.firing_solution(o['self'],e,o['self']['weapons'][0]);o['self']['aim']=list(sol[:2])
        a=self.bot.act(o)
        self.assertTrue(a['fire'][0])
        self.assertFalse(a['fire'][1])


if __name__=='__main__':
    unittest.main()

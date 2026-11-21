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
from world import Prism, World


class GeometryTests(unittest.TestCase):
    def test_landing_surface_distinguishes_roof_bridge_and_courtyard(self):
        w=World.__new__(World)
        w.ground=lambda x,y:0.
        w.nearby=lambda x,y,r:{0}
        w.prisms=[Prism({'base':10,'top':30,'ring':[0,0,20,0,20,20,0,20],
                         'holes':[[5,5,15,5,15,15,5,15]]})]
        self.assertEqual(w.support_height(2,2,5),0.)
        self.assertEqual(w.support_height(2,2,40),30.)
        self.assertEqual(w.support_height(10,10,40),0.)
        self.assertEqual(w.support_height(25,2,40),0.)
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
        self.bot.vertical_accel.clear()
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

    def test_falling_target_is_hit_below_its_current_feet(self):
        o=self.scenario();e=self.enemy(o,distance=150,vel=[0,0,-24])
        e['pos'][2]=40.
        with patch.object(self.bot.world,'clear_ray',return_value=True), patch.object(self.bot.world,'support_height',return_value=0.):
            sol=self.bot.firing_solution(o['self'],e,o['self']['weapons'][0])
        self.assertIsNotNone(sol)
        point,flight=sol[2:]
        t=flight+.045
        future_feet=max(0.,40.-24*t-11*t*t)
        self.assertLess(point[2],e['pos'][2]-5.)
        self.assertGreater(point[2],future_feet)
        self.assertLess(point[2],future_feet+9.)

    def test_falling_target_aim_stays_above_landing_surface(self):
        o=self.scenario();e=self.enemy(o,distance=180,vel=[0,0,-24])
        e['pos'][2]=10.
        with patch.object(self.bot.world,'clear_ray',return_value=True), patch.object(self.bot.world,'support_height',return_value=0.):
            sol=self.bot.firing_solution(o['self'],e,o['self']['weapons'][0])
        self.assertIsNotNone(sol)
        self.assertAlmostEqual(sol[2][2],4.68)

    def test_falling_target_lands_on_roof_instead_of_terrain(self):
        o=self.scenario();e=self.enemy(o,distance=180,vel=[0,0,-35])
        e['pos'][2]=50.
        with patch.object(self.bot.world,'clear_ray',return_value=True), patch.object(self.bot.world,'support_height',return_value=30.):
            sol=self.bot.firing_solution(o['self'],e,o['self']['weapons'][0])
        self.assertIsNotNone(sol)
        self.assertAlmostEqual(sol[2][2],34.68)

    def test_falling_target_preserves_cube_scaled_body_height(self):
        o=self.scenario();e=self.enemy(o,distance=180,vel=[0,0,-24],cubes=10)
        e['pos'][2]=10.
        with patch.object(self.bot.world,'clear_ray',return_value=True), patch.object(self.bot.world,'support_height',return_value=0.):
            sol=self.bot.firing_solution(o['self'],e,o['self']['weapons'][0])
        self.assertIsNotNone(sol)
        self.assertAlmostEqual(sol[2][2],9.*1.5*.52)

    def test_observed_jets_brake_a_fall(self):
        o=self.scenario();o['t']=10.
        e=self.enemy(o,vel=[0,0,-12]);e['pos'][2]=30.;o['mechs']=[e]
        self.bot.enemies.clear()
        self.bot.remember(o)
        o2=copy.deepcopy(o);o2['t']=10.1
        o2['mechs'][0]['vel'][2]=-10.8;o2['mechs'][0]['pos'][2]=28.86
        self.bot.remember(o2)
        self.assertAlmostEqual(self.bot.vertical_accel[e['id']][0],12.)
        with patch.object(self.bot.world,'support_height',return_value=0.):
            p=self.bot.predict_falling_target(o2['mechs'][0],.5)
        self.assertAlmostEqual(p[2],28.86-10.8*.5+6.*.5**2+4.68)

    def test_old_vertical_motion_samples_expire(self):
        o=self.scenario();o['t']=20.;o['mechs']=[]
        self.bot.vertical_accel={5:(12.,19.)}
        self.bot.remember(o)
        self.assertNotIn(5,self.bot.vertical_accel)

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

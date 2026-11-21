"""Tactical regression tests with the real map and recorded rule set."""
import copy
import gzip
import json
import math
from pathlib import Path
import sys
import unittest

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


if __name__=='__main__':
    unittest.main()

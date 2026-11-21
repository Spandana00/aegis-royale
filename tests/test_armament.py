"""Observable arming decisions under contact, with the organizer's rule set."""
import copy
import gzip
import json
import math
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pilot import brain,combat
from pilot.state import WorldState,EnemyThreat,Threats


class ArmamentTests(unittest.TestCase):
    def setUp(self):
        saved = dict(brain.P)
        self.addCleanup(lambda: (brain.P.clear(), brain.P.update(saved)))
        brain.P.update(arm_commit=True, cover_all=False, final_fire=False,
                       combat_cube=False, critical_recover=False)

    @classmethod
    def setUpClass(cls):
        with gzip.open(ROOT/'check/stream.jsonl.gz','rt') as f:
            rows=[json.loads(line) for line in f]
        cls.hello=rows[0]
        cls.observation=next(r for r in rows if r['type']=='obs')

    def scenario(self):
        o=copy.deepcopy(self.observation)
        o.update(t=20.,tick=400,events=[],mechs=[],cubes=[],crates=[],drops=[],
                 projectiles=[],sounds=[],beams=[],offer=None,
                 pickups=[{'id':8001,'kind':'laser','pos':[-20.,0.,0.]}])
        o['self'].update(pos=[0.,0.,0.],vel=[0.,0.,0.],aim=[0.,0.],hp=1400.,max_hp=1400.,
            weapons=[{'kind':'gun','cooldown':0.,'ammo':12,'reload':0.,
                      'stats':copy.deepcopy(self.hello['config']['weapons']['gun'])},None])
        o['zone'].update(center=[0.,0.],next_center=[0.,0.],radius=500.,next_radius=450.,
                         shrink_start=1000.,shrink_end=1100.)
        enemy={'id':5,'kind':'mech','pos':[80.,0.,0.],'vel':[0.,0.,0.],
               'hp':1400.,'max_hp':1400.,'weapons':['gun'],'aim':[3.14159,0.],
               'charging':False,'cubes':0}
        o['mechs']=[enemy]
        s=WorldState(self.hello,None);s.update(o)
        e=EnemyThreat(id=5,kind='mech',pos=(80.,0.,0.),vel=(0.,0.,0.),hp=1400.,max_hp=1400.,
            weapons=['gun'],dist=80.,visible=True,last_seen_t=20.,los=True,can_hit_me=True,facing_me=True,danger=90.)
        return s,Threats(enemies=[e],attackers=[5])

    def test_collects_a_secondary_during_a_gun_duel_and_keeps_firing(self):
        s,th=self.scenario()
        intent=brain.choose_intent(s,th)
        self.assertEqual((intent.mode,intent.loot_id),('loot',8001))
        self.assertEqual(intent.goal,(-20.,0.,0.))
        self.assertEqual(intent.target_id,5)
        self.assertTrue(intent.allow_fire)
        action=combat.step(s,intent,th)
        self.assertTrue(action.fire[0])

    def test_commits_to_one_weapon_instead_of_swapping_routes(self):
        s,th=self.scenario();first=brain.choose_intent(s,th)
        o=copy.deepcopy(s.obs);o.update(t=20.1,tick=402)
        o['pickups'].append({'id':8002,'kind':'lightning','pos':[-1.,0.,0.]})
        s.update(o);th.enemies[0].last_seen_t=s.t
        second=brain.choose_intent(s,th)
        self.assertEqual(first.loot_id,second.loot_id)

    def test_unreached_weapon_times_out_and_is_blacklisted(self):
        s,th=self.scenario();brain.choose_intent(s,th)
        o=copy.deepcopy(s.obs);o.update(t=40.1,tick=802)
        s.update(o);th.enemies[0].last_seen_t=s.t
        intent=brain.choose_intent(s,th)
        self.assertNotEqual(intent.loot_id,8001)
        self.assertGreater(brain._mem(s)['blacklist'][8001],s.t+50.)

    def test_known_gone_weapon_is_abandoned(self):
        s,th=self.scenario();brain.choose_intent(s,th)
        o=copy.deepcopy(s.obs);o.update(t=20.1,tick=402,pickups=[],
              events=[{'type':'take_failed','id':8001,'reason':'gone'}])
        s.update(o);th.enemies[0].last_seen_t=s.t
        self.assertNotEqual(brain.choose_intent(s,th).loot_id,8001)

    def test_zone_emergency_remains_first(self):
        s,th=self.scenario();o=copy.deepcopy(s.obs)
        o['zone'].update(center=[-200.,0.],radius=100.,next_center=[-200.,0.],next_radius=60.,
                         shrink_start=10.,shrink_end=30.)
        s.update(o)
        self.assertEqual(brain.choose_intent(s,th).mode,'rotate')

    def test_arming_override_does_not_replace_multi_attacker_response(self):
        s,th=self.scenario();th.enemies[0].dist=40.
        e=copy.deepcopy(th.enemies[0]);e.id=6;e.pos=(0.,45.,0.);e.dist=45.
        th.enemies.append(e);th.attackers.append(6)
        m=brain._mem(s);m['threats_ref']=th;brain._remember_items(s,m)
        fight={'verdict':'engage','target':th.enemies[0]}
        self.assertIsNone(brain._arming_intent(s,m,th.enemies,fight,set(th.attackers),0.,1.))

    def test_arming_override_leaves_low_health_policy_unchanged(self):
        s,th=self.scenario();m=brain._mem(s);m['threats_ref']=th;brain._remember_items(s,m)
        fight={'verdict':'engage','target':th.enemies[0]}
        self.assertIsNone(brain._arming_intent(s,m,th.enemies,fight,{5},0.,.30))

    def test_killable_attacker_can_be_finished_first(self):
        s,th=self.scenario();th.killable=[5]
        m=brain._mem(s);m['threats_ref']=th;brain._remember_items(s,m)
        fight={'verdict':'engage','target':th.enemies[0]}
        self.assertIsNone(brain._arming_intent(s,m,th.enemies,fight,{5},0.,1.))

    def test_inventory_takes_the_best_equipment_when_drops_overlap(self):
        s,th=self.scenario();s.obs['pickups']=[
            {'id':8002,'kind':'mortar','pos':[0.,0.,0.]},
            {'id':8001,'kind':'laser','pos':[0.,0.,0.]}]
        self.assertEqual(brain.inventory(s,None).take,8001)

    def test_live_mech_reporting_zero_health_still_gets_a_finite_fight_decision(self):
        s,th=self.scenario();s.hp=0.;s.me['hp']=0.
        result=brain._assess_fight(s,th,th.enemies,{5})
        self.assertTrue(math.isfinite(result['ratio']))
        self.assertGreater(result['ratio'],0.)

    def test_normal_health_fight_estimate_matches_the_scored_baseline(self):
        s,th=self.scenario()
        result=brain._assess_fight(s,th,th.enemies,{5})
        self.assertEqual(result['verdict'],'engage')
        self.assertAlmostEqual(result['ratio'],.6882352941176473)

    def test_acquiring_a_weapon_ends_the_new_override(self):
        s,th=self.scenario();brain.choose_intent(s,th)
        s.me['weapons'][1]={'kind':'laser','cooldown':0.,'charge':0.,
                          'stats':copy.deepcopy(self.hello['config']['weapons']['laser'])}
        m=brain._mem(s)
        self.assertIsNone(brain._arming_intent(s,m,th.enemies,m['fight'],{5},0.,1.))
        self.assertNotIn('arming_goal',m)


if __name__=='__main__':
    unittest.main()

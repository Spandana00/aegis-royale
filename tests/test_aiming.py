"""Temporal forecasting checks: the learner sees only the current observation."""
import math
import unittest

from aiming import AimLearner, forecasts


def observe(learner,t,pos,vel,speed=252.,iid=5):
    learner.observe({'t':t,'self':{'pos':[0.,0.,0.]},'mechs':[
        {'id':iid,'kind':'mech','pos':[*pos,0.],'vel':[*vel,0.],'cubes':0}]},speed,.05,2.5)


class AimingTests(unittest.TestCase):
    def test_cold_start_preserves_linear_baseline(self):
        learner=AimLearner()
        observe(learner,0.,[100.,0.],[0.,12.])
        self.assertIsNone(learner.predict({'id':5,'pos':[100.,0.,0.],'vel':[0.,12.,0.]},.5))

    def test_constant_velocity_does_not_switch_away_from_linear(self):
        learner=AimLearner()
        for i in range(60):
            t=i*.1
            observe(learner,t,[100.,12.*t],[0.,12.])
        self.assertGreaterEqual(learner.tracks[5]['samples'],6)
        self.assertEqual(learner.tracks[5]['selected'],0)

    def test_circular_motion_learns_a_better_forecast(self):
        learner=AimLearner()
        radius,rate=12.,1.2
        for i in range(100):
            t=i*.1
            pos=[130.+radius*math.cos(rate*t),radius*math.sin(rate*t)]
            vel=[-radius*rate*math.sin(rate*t),radius*rate*math.cos(rate*t)]
            observe(learner,t,pos,vel)
        self.assertEqual(learner.tracks[5]['selected'],1)
        predicted=learner.predict({'id':5,'pos':[*pos,0.],'vel':[*vel,0.]},.55)
        actual=[130.+radius*math.cos(rate*(t+.55)),radius*math.sin(rate*(t+.55))]
        baseline=forecasts(pos,vel,0.,.55)[0]
        self.assertLess(math.dist(predicted,actual),math.dist(baseline,actual)*.25)

    def test_forecasts_are_not_scored_before_their_due_time(self):
        learner=AimLearner()
        observe(learner,0.,[200.,0.],[0.,12.])
        observe(learner,.1,[200.,1.2],[0.,12.])
        self.assertEqual(learner.tracks[5]['samples'],0)

    def test_visibility_gap_resets_old_learning(self):
        learner=AimLearner()
        observe(learner,0.,[100.,0.],[0.,12.])
        learner.tracks[5].update(selected=1,samples=12)
        observe(learner,1.,[100.,12.],[0.,12.])
        self.assertEqual(learner.tracks[5]['samples'],0)
        self.assertEqual(learner.tracks[5]['selected'],0)

    def test_teleport_does_not_teach_a_false_motion_model(self):
        learner=AimLearner()
        observe(learner,0.,[100.,0.],[0.,12.])
        observe(learner,.1,[300.,0.],[0.,12.])
        self.assertEqual(learner.tracks[5]['samples'],0)

    def test_memory_is_bounded_under_many_ids(self):
        learner=AimLearner()
        for i in range(100):
            observe(learner,i*.1,[100.,0.],[0.,12.],iid=i)
        self.assertLessEqual(len(learner.tracks),learner.MAX_TRACKS)
        self.assertTrue(all(len(tr['pending'])<=learner.MAX_PENDING for tr in learner.tracks.values()))

    def test_circular_forecast_has_correct_zero_turn_limit(self):
        p=forecasts([5.,6.],[10.,-3.],0.,.4)
        self.assertEqual(p[0],p[1])
        self.assertEqual(p[0],(9.,4.8))

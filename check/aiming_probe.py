"""Online forecast diagnostic, not a game, hit-rate test, or placement scorer.

Each observation is supplied at its timestamp. Future positions are used only
by this evaluator after the forecast is made, never as learner input.
"""
import itertools
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from aiming import AimLearner,MODEL_NAMES


def trajectory(kind,distance,speed,rate,phase,t):
    if kind=='linear':
        return [distance,speed*(t-4.)],[0.,speed]
    a=rate*t+phase
    amplitude=speed/rate
    if kind=='circle':
        return [distance+amplitude*math.cos(a),amplitude*math.sin(a)],[-speed*math.sin(a),speed*math.cos(a)]
    return [distance,amplitude*math.sin(a)],[0.,speed*math.cos(a)]


def main():
    summary={}
    linear_preserved=True
    for kind in ('linear','circle','oscillation'):
        rates=(0.,) if kind=='linear' else ((.75,1.25,1.8) if kind=='circle' else (1.4,2.,2.6))
        phases=(0.,) if kind=='linear' else (0.,1.1)
        for distance,speed,rate,phase in itertools.product((60.,110.,160.),(8.,12.,19.5),rates,phases):
            learner=AimLearner()
            row=summary.setdefault(kind,{'scenarios':0,'forecasts':0,'linear_error_sq':0.,'adaptive_error_sq':0.,
                                         'after_2s_forecasts':0,'linear_after_2s_sq':0.,'adaptive_after_2s_sq':0.,
                                         'selected_models':{m:0 for m in MODEL_NAMES}})
            row['scenarios']+=1
            for tick in range(80):
                now=tick*.1
                pos,vel=trajectory(kind,distance,speed,rate,phase,now)
                enemy={'id':5,'kind':'mech','pos':[*pos,0.],'vel':[*vel,0.],'cubes':0}
                learner.observe({'t':now,'self':{'pos':[0.,0.,0.]},'mechs':[enemy]},252.,.05,2.5)
                horizon=math.hypot(*pos)/252.+.045
                baseline=[pos[i]+vel[i]*horizon for i in range(2)]
                predicted=learner.predict(enemy,horizon)
                selected=learner.tracks[5]['selected']
                if predicted is None:
                    predicted=baseline
                # Future truth is computed only after choosing the forecast.
                actual,_=trajectory(kind,distance,speed,rate,phase,now+horizon)
                norm=max(1.,math.hypot(*pos));ax,ay=pos[0]/norm,pos[1]/norm
                old=(actual[0]-baseline[0])*ay-(actual[1]-baseline[1])*ax
                new=(actual[0]-predicted[0])*ay-(actual[1]-predicted[1])*ax
                row['forecasts']+=1
                row['linear_error_sq']+=old*old;row['adaptive_error_sq']+=new*new
                row['selected_models'][MODEL_NAMES[selected]]+=1
                if now>=2.:
                    row['after_2s_forecasts']+=1
                    row['linear_after_2s_sq']+=old*old;row['adaptive_after_2s_sq']+=new*new
                if kind=='linear':
                    linear_preserved &= math.dist(baseline,predicted)<1e-9
    for row in summary.values():
        n=row['forecasts'];warm=row['after_2s_forecasts']
        row['linear_lateral_rmse_m']=round(math.sqrt(row.pop('linear_error_sq')/n),4)
        row['adaptive_lateral_rmse_m']=round(math.sqrt(row.pop('adaptive_error_sq')/n),4)
        row['linear_after_2s_rmse_m']=round(math.sqrt(row.pop('linear_after_2s_sq')/warm),4)
        row['adaptive_after_2s_rmse_m']=round(math.sqrt(row.pop('adaptive_after_2s_sq')/warm),4)
    print(json.dumps({'kind':'online horizontal-forecast diagnostic; not game hit rate or placement',
                      'duration_per_scenario_s':8.,'decision_hz':10,'gun_speed_m_s':252.,
                      'linear_forecasts_preserved':linear_preserved,'groups':summary},indent=2))
    if not linear_preserved:
        raise SystemExit('Constant-velocity baseline changed unexpectedly')


if __name__=='__main__':
    main()

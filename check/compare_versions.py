"""Audit submitted source against the best scored bot; not a match scorer."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BASE='acec27de854684d8e9853c2adcc610411701f11d'
VERSIONS=[
    ('v1','cf2994318977d241b5c65b16eea33a4163cb0be8',[3.75]),
    ('v2','5209875b7f6f512de87b0411b6c44258cd113fbb',[4.50]),
    ('v3','790c32ab40d011a827ec370ace67c2972e6375b5',[3.96]),
    ('v4','463d65d15c11fb26057e1fec22000f9708455fbe',[4.40]),
    ('v5','1fa9554ef876770d36badc949bdf130fd9270156',[4.17,4.15]),
    ('v6','be9c963d0bb180c781984d85d50fb5896e07a6c2',[4.46]),
    ('v7',BASE,[4.60,4.52]),
]


def read(ref,path):
    return subprocess.check_output(['git','show',f'{ref}:{path}'],cwd=ROOT)


def methods(source):
    cls=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='Bot')
    return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,ast.FunctionDef)}


def main():
    baseline=methods(read(BASE,'bot.py'))
    rows=[]
    for name,ref,scores in VERSIONS:
        current=methods(read(ref,'bot.py'))
        changes=[n for n in current if current[n]!=baseline.get(n)]
        hashes={p:hashlib.sha256(read(ref,p)).hexdigest()
                for p in ['bot.py','world.py','navigation.py','mechfight.py','Dockerfile']}
        rows.append({'version':name,'commit':ref,'user_reported_scores':scores,
                     'deltas_from_best':[round(s-4.6,2) for s in scores],
                     'changed_bot_methods_vs_reference':changes,
                     'removed_bot_methods_vs_reference':[n for n in baseline if n not in current],
                     'runtime_sha256':hashes})
    current=methods((ROOT/'bot.py').read_bytes())
    changed=[n for n in current if current[n]!=baseline.get(n)]
    allowed={'__init__','remember','firing_solution'}
    if set(changed)!=allowed or not set(baseline)<=set(current):
        raise SystemExit(f'V8 scope changed outside learned gun aim: {changed}')
    for p in ['world.py','navigation.py','mechfight.py']:
        if (ROOT/p).read_bytes()!=read(BASE,p):
            raise SystemExit(f'Unexpected V8 runtime change: {p}')
    expected_docker=read(BASE,'Dockerfile').replace(b'COPY bot.py mechfight.py',b'COPY bot.py aiming.py mechfight.py')
    if (ROOT/'Dockerfile').read_bytes()!=expected_docker:
        raise SystemExit('Docker changed beyond copying aiming.py')
    expected_ignore=read(BASE,'.dockerignore').replace(b'!bot.py',b'!bot.py\n!aiming.py')
    if (ROOT/'.dockerignore').read_bytes()!=expected_ignore:
        raise SystemExit('Docker build allowlist changed beyond including aiming.py')
    print(json.dumps({
        'kind':'submitted-source audit and user-reported official scores; not a local scorer',
        'score_source':'user-supplied submission screenshots',
        'reference_commit':BASE,'reference_score':4.6,'matches_per_run':48,
        'minimum_extra_integer_placement_points_to_reach_5_30':34,
        'runs':rows,
        'candidate':{'name':'AEGIS v8','changed_bot_methods_vs_reference':changed,
                     'all_other_bot_methods_identical_to_reference':True,
                     'map_navigation_and_wrapper_identical_to_reference':True,
                     'docker_change':'Copies and allows aiming.py; other packaging content identical',
                     'aiming_module_sha256':hashlib.sha256((ROOT/'aiming.py').read_bytes()).hexdigest()}
    },indent=2))


if __name__=='__main__':
    main()

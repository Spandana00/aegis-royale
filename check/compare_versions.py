"""Audit submitted source against the best scored bot; not a match scorer."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from source_fingerprint import stable_ast_dump
BASE='d75253a91ccb4d199d4374c076ee0d58c383e590'
VERSIONS=[
    ('v1','cf2994318977d241b5c65b16eea33a4163cb0be8',[3.75]),
    ('v2','5209875b7f6f512de87b0411b6c44258cd113fbb',[4.50]),
    ('v3','790c32ab40d011a827ec370ace67c2972e6375b5',[3.96]),
    ('v4','463d65d15c11fb26057e1fec22000f9708455fbe',[4.40]),
    ('v5','1fa9554ef876770d36badc949bdf130fd9270156',[4.17,4.15]),
    ('v6','be9c963d0bb180c781984d85d50fb5896e07a6c2',[4.46]),
    ('v7','acec27de854684d8e9853c2adcc610411701f11d',[4.60,4.52]),
    ('v8','46d8cb1965a7a3c513ac705c588d34164292276d',[4.60]),
    ('v9','585ac9b06b7d9f6f5317ad52d1a3ab15c2656fa6',[4.77]),
    ('v10',BASE,[5.33]),
]


def read(ref,path):
    return subprocess.check_output(['git','show',f'{ref}:{path}'],cwd=ROOT)


def methods(source):
    cls=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='Bot')
    return {n.name:stable_ast_dump(n) for n in cls.body if isinstance(n,ast.FunctionDef)}


def main():
    baseline=methods(read(BASE,'bot.py'))
    rows=[]
    for name,ref,scores in VERSIONS:
        current=methods(read(ref,'bot.py'))
        changes=[n for n in current if current[n]!=baseline.get(n)]
        hashes={p:hashlib.sha256(read(ref,p)).hexdigest()
                for p in ['bot.py','world.py','navigation.py','mechfight.py','Dockerfile']}
        rows.append({'version':name,'commit':ref,'user_reported_scores':scores,
                     'deltas_from_best':[round(s-5.33,2) for s in scores],
                     'changed_bot_methods_vs_reference':changes,
                     'removed_bot_methods_vs_reference':[n for n in baseline if n not in current],
                     'runtime_sha256':hashes})
    current=methods((ROOT/'bot.py').read_bytes())
    changed=[n for n in current if current[n]!=baseline.get(n)]
    allowed=set()
    if set(changed)!=allowed or not set(baseline)<=set(current):
        raise SystemExit(f'Legacy V9 source unexpectedly changed: {changed}')
    for p in ['aiming.py','world.py','navigation.py','mechfight.py']:
        if (ROOT/p).read_bytes()!=read(BASE,p):
            raise SystemExit(f'Legacy V9 source unexpectedly changed: {p}')
    manifest=json.loads((ROOT/'docs/reference_manifest.json').read_text())
    for f in manifest['files']:
        actual=hashlib.sha256((ROOT/f['path']).read_bytes()).hexdigest()
        if actual!=f['sha256'] or (f['path'] not in ('pilot/main.py','pilot/brain.py') and actual!=f['source_sha256']):
            raise SystemExit(f'Imported policy changed: {f["path"]}')
    brain_text=(ROOT/'pilot/brain.py').read_text()
    brain_text=brain_text.replace('their_ttk = max(ehp, 1.0) / inc','their_ttk = ehp / inc')
    module=ast.parse(brain_text)
    scope=manifest['tactical_scope']
    module.body=[n for n in module.body if not(isinstance(n,ast.FunctionDef) and n.name in scope['modified_functions'])]
    if hashlib.sha256(stable_ast_dump(module).encode()).hexdigest()!=scope['protected_brain_ast_sha256']:
        raise SystemExit('Brain changed outside the documented armament functions')
    for p in ['pilot/arena.py','pilot/navigate.py','pilot/navigate3.py','pilot/combat.py','pilot/ballistics.py',
              'pilot/state.py','pilot/threats.py','pilot/navbake.npz','Dockerfile','.dockerignore']:
        if (ROOT/p).read_bytes()!=read(BASE,p):
            raise SystemExit(f'Unexpected change outside armament policy: {p}')
    print(json.dumps({
        'kind':'source provenance and reported scores; not a local scorer',
        'score_source':'user-supplied submission screenshots and follow-up score reports',
        'reference_commit':BASE,'reference_score':5.33,'matches_per_run':48,
        'minimum_extra_integer_placement_points_to_reach_5_50':8,
        'minimum_extra_integer_placement_points_to_reach_6_00':32,
        'runs':rows,
        'candidate':{'name':'AEGIS v11','official_score':None,
                     'active_entrypoint':'pilot/main.py','legacy_v9_source_preserved':True,
                     'policy_source':manifest['upstream_repository'],
                     'policy_commit':manifest['upstream_commit'],
                     'reported_upstream_best':5.56,'reported_upstream_family_mean':5.34,
                     'upstream_score_independently_verified':False,
                     'unchanged_module_scope':'V10 map, navigation, combat, ballistics, threats, state, guard and packaging',
                     'changed_tactics':scope['modified_functions'],
                     'numeric_guard':'Floor effective HP at 1 only for the fight-time denominator',
                     'only_source_edits':manifest['changes']}
    },indent=2))


if __name__=='__main__':
    main()

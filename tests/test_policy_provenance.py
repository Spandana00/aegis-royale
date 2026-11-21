"""Verify the active policy's provenance, unchanged modules and tactical scope."""
import ast
import gzip
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from source_fingerprint import stable_ast_dump


class ProvenanceTests(unittest.TestCase):
    def test_all_imported_runtime_files_match_the_pinned_manifest(self):
        manifest=json.loads((ROOT/'docs/reference_manifest.json').read_text())
        for entry in manifest['files']:
            data=(ROOT/entry['path']).read_bytes()
            self.assertEqual(len(data),entry['size_bytes'],entry['path'])
            self.assertEqual(hashlib.sha256(data).hexdigest(),entry['sha256'],entry['path'])
            if entry['path'] not in ('pilot/main.py','pilot/brain.py','pilot/navigate3.py','pilot/local_motion.py',
                                     'pilot/combat.py','pilot/tactics.py'):
                self.assertEqual(entry['sha256'],entry['source_sha256'],entry['path'])

    def test_entrypoint_diff_is_only_namespace_and_display_name(self):
        manifest=json.loads((ROOT/'docs/reference_manifest.json').read_text())
        text=(ROOT/'pilot/main.py').read_text()
        text=text.replace('from pilot import state as st','from bot import state as st')
        text=text.replace('from pilot.arena import Arena','from bot.arena import Arena')
        text=text.replace('f"pilot.{name}"','f"bot.{name}"')
        text=text.replace('"pilot.navigate3"','"bot.navigate3"')
        text=text.replace('import pilot.{name} failed','import bot.{name} failed')
        text=text.replace(f'BOT_NAME = "{manifest["display_name"]}"','BOT_NAME = "OSU-Walker"')
        expected=next(e['source_sha256'] for e in manifest['files'] if e['path']=='pilot/main.py')
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),expected)

    def test_tactical_changes_are_limited_to_the_documented_scope(self):
        manifest=json.loads((ROOT/'docs/reference_manifest.json').read_text())
        for filename,scope in manifest['tactical_scopes'].items():
            module=ast.parse((ROOT/filename).read_text())
            def changed(n):
                if isinstance(n,ast.FunctionDef):
                    return n.name in scope['modified_functions']
                return (isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name)
                        and n.target.id in scope.get('modified_globals',[]))
            module.body=[n for n in module.body if not changed(n)]
            digest=hashlib.sha256(stable_ast_dump(module).encode()).hexdigest()
            self.assertEqual(digest,scope['protected_ast_sha256'],filename)

    def test_enabled_features_match_the_declared_candidate(self):
        from pilot import brain
        manifest=json.loads((ROOT/'docs/reference_manifest.json').read_text())
        for key,value in manifest['enabled_features'].items():
            self.assertEqual(brain.P[key],value,key)


class RetainedPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pilot.main import Pilot
        with gzip.open(ROOT/'check/stream.jsonl.gz','rt') as f:
            hello=json.loads(next(f))
        hello['map']['dir']=str(ROOT/'arena')
        cls.policy=Pilot(hello)

    def test_reported_profile_and_navigation_are_active(self):
        from pilot import brain
        self.assertEqual(brain.DEFAULT_PROFILE,'laser+nav3x+fixx+steadyx')
        self.assertTrue(brain.P['laser_first'])
        self.assertEqual(brain.P['strafe_mode'],'steady')
        self.assertEqual(self.policy.mods['navigate'].__name__,'pilot.navigate3')

    def test_navigation_cache_loads_instead_of_silent_fallback(self):
        self.assertIsNotNone(self.policy.state.arena)
        self.assertTrue(self.policy.state.arena.ok_nav)
        self.assertEqual(self.policy.errors,{})

    def test_deadline_fallback_keeps_motion_and_drops_one_shots(self):
        from pilot.main import fallback
        previous={'tick':10,'move':[.6,.8],'aim':[1.,.2],'boost':True,
                  'fire':[True,True],'jump':True,'take':8001,'reload':True,'pick':1,'drop':0}
        action=fallback(previous,12)
        self.assertEqual(action,{'tick':12,'move':[.6,.8],'aim':[1.,.2],'boost':True})


if __name__=='__main__':
    unittest.main()

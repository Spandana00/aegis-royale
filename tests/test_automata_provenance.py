"""Preserve the complete pinned implementation and its coupled configuration."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AutomataProvenanceTests(unittest.TestCase):
    def test_all_runtime_sources_match_the_manifest_and_original_git_blobs(self):
        m = json.loads((ROOT/'docs/automata_manifest.json').read_text())
        for e in m['files']:
            data = (ROOT/e['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), e['sha256'], e['path'])
            self.assertEqual(len(data), e['size_bytes'], e['path'])
            original = data.replace(b'pub const BOT_NAME: &str = "AEGIS v14";',
                                    b'pub const BOT_NAME: &str = "automata";') if e['source_path']=='src/runtime.rs' else data
            self.assertEqual(hashlib.sha256(original).hexdigest(), e['source_sha256'], e['path'])
            self.assertEqual(hashlib.sha1(b'blob '+str(len(original)).encode()+b'\0'+original).hexdigest(),
                             e['source_git_blob'], e['path'])

    def test_original_equipment_parameters_remain_together(self):
        p = json.loads((ROOT/'automata/bot.json').read_text())
        self.assertNotIn('sf_nofirst', p)
        self.assertNotIn('sf_harm', p)
        self.assertNotIn('gear_late_s', p)
        self.assertEqual(p['lz_seek'], 300)
        self.assertEqual(p['gear_on'], 1)
        self.assertIs(p['harvest_on'], True)

    def test_packaging_runs_the_rust_policy_with_its_configuration(self):
        docker = (ROOT/'Dockerfile').read_text()
        ignore = (ROOT/'.dockerignore').read_text()
        self.assertIn('COPY automata/ .', docker)
        self.assertIn('ENV MECH_PARAMS=/bot.json', docker)
        self.assertIn('USER 65534:65534', docker)
        self.assertIn('ENTRYPOINT ["/usr/local/bin/automata"]', docker)
        self.assertIn('!automata/**', ignore)
        self.assertNotIn('!sentinel/', ignore)
        manifest = json.loads((ROOT/'docs/automata_manifest.json').read_text())
        for path, expected in manifest['packaging_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(), expected, path)


if __name__=='__main__':
    unittest.main()

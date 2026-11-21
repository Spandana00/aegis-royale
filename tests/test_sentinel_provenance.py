"""The active policy must preserve the pinned upstream's complete tactical code."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SentinelProvenanceTests(unittest.TestCase):
    def test_every_upstream_file_is_exact_after_reversing_only_namespacing_and_display_name(self):
        manifest = json.loads((ROOT / 'docs/sentinel_manifest.json').read_text())
        for entry in manifest['files']:
            data = (ROOT / entry['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'], entry['path'])
            self.assertEqual(len(data), entry['size_bytes'])
            if entry['path'].endswith('.py'):
                text = data.decode().replace('from .bot import ', 'from bot import ')
                text = text.replace('from .survivor import ', 'from survivor import ')
                text = text.replace('from .navigation import ', 'from navigation import ')
                text = text.replace('from . import mechfight as mf', 'import mechfight as mf')
                text = text.replace("name = 'AEGIS v13'", "name = 'Oval-Sentinel-recovery-v26'")
                data = text.encode()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry['source_sha256'], entry['path'])
            blob = b'blob ' + str(len(data)).encode() + b'\0' + data
            self.assertEqual(hashlib.sha1(blob).hexdigest(), entry['source_git_blob'], entry['path'])

    def test_competition_image_runs_the_audited_policy(self):
        docker = (ROOT / 'Dockerfile').read_text()
        self.assertIn('COPY sentinel/ /app/sentinel/', docker)
        self.assertIn('"-m", "sentinel.main"', docker)
        ignore = (ROOT / '.dockerignore').read_text()
        self.assertIn('!sentinel/**', ignore)
        manifest = json.loads((ROOT / 'docs/sentinel_manifest.json').read_text())
        for filename, expected in manifest['packaging_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT / filename).read_bytes()).hexdigest(), expected, filename)
        from sentinel.combat import Combat
        self.assertEqual(Combat.name, 'AEGIS v13')


if __name__ == '__main__':
    unittest.main()

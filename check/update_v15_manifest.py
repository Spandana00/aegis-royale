"""Pin the scoped V15 adaptation against the immutable, officially scored V14."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = '3f08bd1311f93bde3696a2f5a295fd603e9e9fa0'
ALLOWED = {'automata/src/runtime.rs', 'automata/src/brain/aim.rs',
           'automata/src/brain/params.rs', 'automata/src/brain/mod.rs', 'automata/bot.json'}


def main():
    old = json.loads(subprocess.check_output(['git', 'show', BASE+':docs/automata_manifest.json'], cwd=ROOT))
    files = []
    for entry in old['files']:
        original = subprocess.check_output(['git', 'show', BASE+':'+entry['path']], cwd=ROOT)
        if entry['source_path'] == 'src/runtime.rs':
            original = original.replace(b'pub const BOT_NAME: &str = "AEGIS v14";', b'pub const BOT_NAME: &str = "automata";')
        assert hashlib.sha256(original).hexdigest() == entry['source_sha256']
        actual = (ROOT/entry['path']).read_bytes()
        assert actual == original or entry['path'] in ALLOWED, entry['path']
        source_lines = original.decode().splitlines(keepends=True)
        adapted_lines = actual.decode().splitlines(keepends=True)
        transformations = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=source_lines, b=adapted_lines, autojunk=False).get_opcodes():
            if tag != 'equal':
                transformations.append({'adapted_start_line': j1, 'adapted_end_line': j2,
                    'adapted_sha256': hashlib.sha256(''.join(adapted_lines[j1:j2]).encode()).hexdigest(),
                    'original_lines': source_lines[i1:i2]})
        files.append(dict(entry, sha256=hashlib.sha256(actual).hexdigest(), size_bytes=len(actual),
                          reverse_transformations=transformations))
    extra = 'automata/src/brain/optimization_tests.rs'
    data = (ROOT/extra).read_bytes()
    files.append({'path': extra, 'source_path': None, 'sha256': hashlib.sha256(data).hexdigest(),
                  'size_bytes': len(data), 'purpose': 'New firing and relative-motion regression scenarios.'})
    config = json.loads((ROOT/'automata/bot.json').read_text())
    manifest = {'policy': 'AEGIS v15 / scoped adaptation of the scored V14 policy',
        'upstream_repository': old['upstream_repository'], 'upstream_commit': old['upstream_commit'],
        'baseline': {'commit': BASE, 'official_score': 6.19, 'receipt': 'BB-A804A35A'},
        'our_official_score': None,
        'allowed_modified_upstream_paths': sorted(ALLOWED),
        'allowed_changes': ['Display name.',
            'Independently switched laser damage, cube-bounded armor, own-motion aim and central aim sharing hypotheses, all disabled in Params defaults.',
            'Explicit selected configuration and new regression tests.'],
        'selected_config': config,
        'source_equivalence': 'Reverse the recorded line transformations to recover every original upstream Git blob.',
        'files': files,
        'packaging_sha256': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in old['packaging_sha256']}}
    (ROOT/'docs/v15_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    main()

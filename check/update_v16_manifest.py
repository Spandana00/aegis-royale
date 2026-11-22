"""Pin V16 against V14: original runtime, display name and selected configuration."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = '3f08bd1311f93bde3696a2f5a295fd603e9e9fa0'
ALLOWED = {'automata/src/runtime.rs', 'automata/bot.json'}


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
        changes = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=source_lines, b=adapted_lines, autojunk=False).get_opcodes():
            if tag != 'equal':
                changes.append({'adapted_start_line': j1, 'adapted_end_line': j2,
                    'adapted_sha256': hashlib.sha256(''.join(adapted_lines[j1:j2]).encode()).hexdigest(),
                    'original_lines': source_lines[i1:i2]})
        files.append(dict(entry, sha256=hashlib.sha256(actual).hexdigest(),
            size_bytes=len(actual), reverse_transformations=changes))
    baseline_config = json.loads(subprocess.check_output(['git', 'show', BASE+':automata/bot.json'], cwd=ROOT))
    config = json.loads((ROOT/'automata/bot.json').read_text())
    diff = {key: {'before': baseline_config.get(key, 'upstream default'), 'after': value}
        for key, value in config.items() if value != baseline_config.get(key)}
    assert set(diff) <= {'range_laser', 'gear_late_s'}, diff
    assert all(key in config for key in baseline_config), 'Original equipment bundle must be retained'
    manifest = {'policy': 'AEGIS v16 / V14 runtime with a controlled strategy configuration',
        'upstream_repository': old['upstream_repository'], 'upstream_commit': old['upstream_commit'],
        'baseline': {'commit': BASE, 'official_score': 6.19, 'receipt': 'BB-A804A35A'},
        'rejected_v15': {'commit': 'be6c83e043e7f604aa95d7f9c4f2e2f52c556f85',
            'official_score': 6.15, 'receipt': 'BB-05A9CC68'},
        'our_official_score': None, 'allowed_modified_upstream_paths': sorted(ALLOWED),
        'allowed_changes': ['Display name.', 'Selected strategy configuration, independently and jointly compared.',
            'V15 firing experiments removed; all original runtime algorithms restored.'],
        'selected_config': config, 'configuration_difference_from_v14': diff,
        'source_equivalence': 'Reverse recorded line transformations to recover every original upstream Git blob.',
        'files': files, 'packaging_sha256': {
            path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in old['packaging_sha256']}}
    (ROOT/'docs/v16_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    main()

"""Keep the 6.25 champion intact; pin the candidate's one priority change."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

from study_v17 import BASE, configuration

ROOT = Path(__file__).resolve().parents[1]
VENDOR_BASE = '3f08bd1311f93bde3696a2f5a295fd603e9e9fa0'
ALLOWED = {'automata/src/runtime.rs', 'automata/bot.json'}


def main():
    champion = json.loads((ROOT/'champion.json').read_text())
    assert champion['commit'] == BASE and champion['official_score'] == 6.25
    original_manifest = json.loads(subprocess.check_output(
        ['git', 'show', VENDOR_BASE+':docs/automata_manifest.json'], cwd=ROOT))
    entries = []
    for entry in original_manifest['files']:
        original = subprocess.check_output(['git', 'show', VENDOR_BASE+':'+entry['path']], cwd=ROOT)
        if entry['source_path'] == 'src/runtime.rs':
            original = original.replace(b'pub const BOT_NAME: &str = "AEGIS v14";',
                                        b'pub const BOT_NAME: &str = "automata";')
        assert hashlib.sha256(original).hexdigest() == entry['source_sha256']
        actual = (ROOT/entry['path']).read_bytes()
        assert actual == original or entry['path'] in ALLOWED, entry['path']
        if entry['path'] == 'automata/src/runtime.rs':
            assert actual == original.replace(b'pub const BOT_NAME: &str = "automata";',
                                              b'pub const BOT_NAME: &str = "AEGIS v17";')
        a, b = original.decode().splitlines(keepends=True), actual.decode().splitlines(keepends=True)
        changes = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
            if tag != 'equal':
                changes.append({'adapted_start_line': j1, 'adapted_end_line': j2,
                    'adapted_sha256': hashlib.sha256(''.join(b[j1:j2]).encode()).hexdigest(),
                    'original_lines': a[i1:i2]})
        entries.append(dict(entry, sha256=hashlib.sha256(actual).hexdigest(),
                            size_bytes=len(actual), reverse_transformations=changes))
    before = configuration('control')
    selected = json.loads((ROOT/'automata/bot.json').read_text())
    assert selected == configuration('charge')
    difference = {key: {'before': before[key], 'after': value}
                  for key, value in selected.items() if before[key] != value}
    assert set(difference) == {'upgrade_priority'}
    priority = selected['upgrade_priority']
    assert priority[:3] == before['upgrade_priority'][:3] == ['plating', 'armor', 'nanites']
    assert [x for x in priority if x != 'laser_charge'] == [
        x for x in before['upgrade_priority'] if x != 'laser_charge']
    assert selected['range_laser'] == 200
    manifest = {'policy': 'AEGIS v17 / faster-charge priority on the scored V16 runtime',
        'upstream_repository': original_manifest['upstream_repository'],
        'upstream_commit': original_manifest['upstream_commit'],
        'baseline': {'commit': BASE, 'official_score': 6.25, 'receipt': champion['receipt']},
        'our_official_score': None,
        'allowed_modified_upstream_paths': sorted(ALLOWED),
        'allowed_changes': ['Display name.', 'Move laser_charge immediately after plating, armor and nanites.',
            'All other priority relationships and the champion configuration remain intact.'],
        'configuration_difference_from_baseline': difference, 'selected_config': selected,
        'files': entries, 'packaging_sha256': {
            path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
            for path in original_manifest['packaging_sha256']}}
    (ROOT/'docs/v17_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    main()

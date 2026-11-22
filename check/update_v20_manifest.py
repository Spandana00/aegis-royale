"""Pin the bounded V20 resource deferral against scored V17 and original blobs."""
import difflib, hashlib, json, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
BASE = 'e45e734215354fc4f938af15c984a666f446a426'
VENDOR = '3f08bd1311f93bde3696a2f5a295fd603e9e9fa0'
ALLOWED = {'automata/bot.json','automata/src/runtime.rs','automata/src/brain/aim.rs',
           'automata/src/brain/mod.rs','automata/src/brain/params.rs','automata/src/brain/strategy.rs'}
def read(ref,path):return subprocess.check_output(['git','show',ref+':'+path],cwd=ROOT)
def main():
    old = json.loads(read(VENDOR,'docs/automata_manifest.json'))
    entries = []
    for entry in old['files']:
        original = read(VENDOR,entry['path'])
        if entry['source_path'] == 'src/runtime.rs':
            original = original.replace(b'AEGIS v14',b'automata')
        assert hashlib.sha256(original).hexdigest() == entry['source_sha256']
        actual = (ROOT/entry['path']).read_bytes()
        assert actual == original or entry['path'] in ALLOWED, entry['path']
        a,b = original.decode().splitlines(keepends=True),actual.decode().splitlines(keepends=True)
        changes=[]
        for tag,i1,i2,j1,j2 in difflib.SequenceMatcher(a=a,b=b,autojunk=False).get_opcodes():
            if tag != 'equal':
                changes.append({'adapted_start_line':j1,'adapted_end_line':j2,
                    'adapted_sha256':hashlib.sha256(''.join(b[j1:j2]).encode()).hexdigest(),
                    'original_lines':a[i1:i2]})
        entries.append(dict(entry,sha256=hashlib.sha256(actual).hexdigest(),size_bytes=len(actual),reverse_transformations=changes))
    path='automata/src/brain/finisher.rs';data=(ROOT/path).read_bytes()
    entries.append({'path':path,'source_path':None,'sha256':hashlib.sha256(data).hexdigest(),
                    'size_bytes':len(data),'reverse_transformations':[]})
    before=json.loads(read(BASE,'automata/bot.json')); selected=json.loads((ROOT/'automata/bot.json').read_text())
    assert {k:v for k,v in selected.items() if k!='finish_grace_s'} == before
    assert selected['finish_grace_s']==0.6
    manifest={'policy':'AEGIS v20 / bounded ready-laser kill completion',
        'upstream_repository':old['upstream_repository'],'upstream_commit':old['upstream_commit'],
        'baseline':{'commit':BASE,'official_score':6.27,'receipt':'BB-961EADA2'},'our_official_score':None,
        'allowed_modified_upstream_paths':sorted(ALLOWED),
        'allowed_changes':['Display name.','Add default-off resource deferral, selected at0.6seconds.',
            'Track a nonrenewing per-target window; attach target identity without changing firing scores.',
            'Suppress resource goals only for a ready aligned laser shot; retain safety priorities.'],
        'configuration_difference_from_baseline':{'finish_grace_s':{'before':None,'after':0.6}},
        'selected_config':selected,'files':entries,'packaging_sha256':json.loads(read(BASE,'docs/v17_manifest.json'))['packaging_sha256']}
    manifest['packaging_sha256'] = {path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in manifest['packaging_sha256']}
    (ROOT/'docs/v20_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()

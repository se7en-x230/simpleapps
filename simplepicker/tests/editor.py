import os,json,subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as temp:
    work=Path(temp);bin_dir=work/'bin';bin_dir.mkdir();data=work/'data';data.mkdir()
    target=data/'bookmarks.json'
    original=[dict(label='Original',url='https://example.test/')]
    config=work/'config.toml';config.write_text('')
    stub=bin_dir/'nvim';stub.write_text('''#!/usr/bin/python3
import os,json,sys
from pathlib import Path
p=Path(sys.argv[1]);mode=os.environ['SP_EDITOR_CASE']
if mode=='cancel':raise SystemExit(1)
if mode=='invalid':p.write_text('not JSON');raise SystemExit(0)
rows=json.loads(p.read_text());rows.append(dict(label='New',url='https://example.test/new'));p.write_text(json.dumps(rows))
if mode=='conflict':Path(os.environ['SP_TARGET']).write_text(json.dumps([dict(label='Concurrent',url='https://example.test/concurrent')]))
''');stub.chmod(0o755)
    env=dict(os.environ,PATH=str(bin_dir)+':/usr/bin:/bin',SIMPLEPICKER_DATA_DIR=str(data),SP_TARGET=str(target))
    for case in ('valid','cancel','invalid','conflict'):
        target.write_text(json.dumps(original))
        result=subprocess.run([str(root/'simplepicker-native'),'--config',str(config),'--bookmark-editor'],input='q\n',text=True,capture_output=True,env=dict(env,SP_EDITOR_CASE=case),timeout=10)
        assert result.returncode==0,(case,result.stderr)
        rows=json.loads(target.read_text())
        if case=='valid':
            assert len(rows)==2
            assert json.loads((data/'bookmarks.json.bak').read_text())==original
        elif case=='conflict':
            assert rows[0]['label']=='Concurrent'
            assert json.loads((data/'bookmarks-edit-recovery.json').read_text())[1]['label']=='New'
        else:assert rows==original
        assert target.stat().st_mode&0o077==0 or case in ('cancel','invalid','conflict')
        print('PASS: bookmark editor',case)

"""Restore clipboard history through the actual picker; all external actions are stubbed."""
import json,os,subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
    work=Path(tmp);bindir=work/'bin';bindir.mkdir();config=work/'config';(config/'simplepicker').mkdir(parents=True)
    helper=bindir/'helper'
    helper.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
if Path(sys.argv[0]).name=='cliphist':
 if sys.argv[-1]=='list':print('1\\tHistory fixture')
 elif sys.argv[1]=='decode':sys.stdin.buffer.read();sys.stdout.buffer.write(Path(os.environ['TEST_PAYLOAD']).read_bytes())
elif sys.argv[1]=='copy':
 Path(os.environ['TEST_COPY']).write_bytes(sys.stdin.buffer.read())
 Path(os.environ['TEST_ARGS']).write_text(json.dumps(sys.argv[2:]))
''');helper.chmod(0o755);(bindir/'cliphist').symlink_to(helper)
    (config/'simplepicker/config.toml').write_text(f'[desktop]\nbackend="generic"\n[commands]\ncopy=["{helper}","copy"]\npaste=["{helper}","paste"]\npaste_terminal=["{helper}","paste"]\n')
    env=dict(os.environ,HOME=tmp,XDG_CONFIG_HOME=str(config),XDG_DATA_HOME=str(work/'data'),SIMPLEPICKER_ASSETS=str(root/'assets'),PATH=str(bindir)+':'+os.environ['PATH'],TEST_PAYLOAD=str(work/'payload'),TEST_COPY=str(work/'copy'),TEST_ARGS=str(work/'args'),SP_TEST_PLAN=str(work/'plan'),GTK_A11Y='none')
    env.pop('SIMPLEPICKER_CONFIG',None);env.pop('SIMPLEPICKER_THEME',None)
    for name,payload,mime,plain in [
        ('recording',b'file:///home/example/Videos/a%20recording%20%231.mp4\r\n','text/uri-list',False),
        ('multiple files',b'file:///tmp/a.mp4\r\nfile:///tmp/b%0Ac.mp4\r\n','text/uri-list',False),
        ('localhost and comments',b'# copied files\r\nfile://localhost/tmp/a.mp4\r\n','text/uri-list',False),
        ('ordinary text',b'hello\nworld',None,False),
        ('URL',b'https://example.org/',None,False),
        ('mixed text',b'file:///tmp/a.mp4\nPlease open this movie',None,False),
        ('remote file URL',b'file://other-host/tmp/a.mp4',None,False),
        ('embedded NUL',b'file:///tmp/a.mp4\0hidden',None,False),
        ('explicit plain paste',b'file:///tmp/a.mp4\r\n','text/plain;charset=utf-8',True),
    ]:
        (work/'payload').write_bytes(payload)
        (work/'plan').write_text(json.dumps([dict(key='p',ctrl=True)] if plain else [dict(key='Return')]))
        result=subprocess.run([str(root/'tests/driver'),'--clipboard'],env=env,capture_output=True,timeout=15)
        assert result.returncode==0,(name,result.stderr)
        assert (work/'copy').read_bytes()==payload,name
        assert json.loads((work/'args').read_text())==(['--type',mime] if mime else []),name
        print('PASS:',name,flush=True)

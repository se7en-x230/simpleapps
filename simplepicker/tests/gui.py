"""GUI parity checks with isolated config/data and stubbed external actions."""
import json,os,subprocess,tempfile,time,struct,zlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='simplepicker-native-tests-') as temp:
    work=Path(temp);bin_dir=work/'bin';bin_dir.mkdir();data=work/'data';data.mkdir();config=work/'config';(config/'simplepicker').mkdir(parents=True)
    apps=work/'applications';apps.mkdir()
    system_data=work/'system-data';system_data.mkdir()
    for resource in ('mime','icons','glycin-loaders'):
        target=Path('/usr/share')/resource
        if target.exists():(system_data/resource).symlink_to(target)
    log=work/'actions.jsonl';copied=work/'copied';image=work/'image.png'
    def chunk(kind,payload):return struct.pack('!I',len(payload))+kind+payload+struct.pack('!I',zlib.crc32(kind+payload))
    image.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',2,2,8,6,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\xff\0\0\xff'*2)*2))+chunk(b'IEND',b''))
    stub=bin_dir/'helper'
    stub.write_text('''#!/usr/bin/python3
import os,sys,json
from pathlib import Path
name=Path(sys.argv[0]).name;args=sys.argv[1:]
with open(os.environ['SP_LOG'],'a') as f:f.write(json.dumps([name,*args])+'\\n')
if name=='cliphist':
 if args[-1:]==['list']:print('1\\tExample clipboard text\\n2\\t[[ binary data 80 B png 2x2 ]]\\n3\\t[[ binary data 90 B application/pdf ]]')
 elif args==['decode']:
  data=sys.stdin.buffer.read()
  sys.stdout.buffer.write(Path(os.environ['SP_IMAGE']).read_bytes() if data.startswith(b'2\\t') else b'Example clipboard text with a longer preview')
 elif args==['delete']:sys.stdin.buffer.read()
elif name=='qalc':print('4')
elif name=='fc-list':print('Sans\\nSerif\\nMonospace')
elif name=='wl-paste':print('https://example.test/test')
elif args and args[0]=='copy':Path(os.environ['SP_COPIED']).write_bytes(sys.stdin.buffer.read())
elif args and args[0]=='windows':print(json.dumps([dict(id='101',title='Test window',app_id='test',workspace='1',output='test',pid=1,focused=True)]))
elif args and args[0]=='current':print(json.dumps(dict(workspace='2',output='test')))
''');stub.chmod(0o755)
    for name in ('cliphist','qalc','fc-list','wl-paste','notify-send'):(bin_dir/name).symlink_to(stub)
    cfg=config/'simplepicker/config.toml'
    content=f'''[desktop]
backend="custom"
[commands]
copy=["{stub}","copy"]
open_url=["{stub}","open","{{url}}"]
paste=["{stub}","paste"]
paste_terminal=["{stub}","paste-terminal"]
[windows]
list=["{stub}","windows"]
current=["{stub}","current"]
focus=["{stub}","focus","{{id}}"]
close=["{stub}","close","{{id}}"]
move=["{stub}","move","{{id}}","{{workspace}}"]
'''
    for action,key in (('lock','e'),('logout','l'),('suspend','u'),('shutdown','s'),('hibernate','h'),('reboot','r')):
        content+=f'\n[power.{action}]\ncommand=["{stub}","power-{action}"]\n'
    cfg.write_text(content)
    (config/'simplepicker/websearch.json').write_text(json.dumps([dict(name='Test search',prefix='t',url='https://example.test/?q=%TERM%')]))
    (data/'bookmarks.json').write_text(json.dumps([dict(label='Example',url='https://example.test/')]))
    (apps/'native-test.desktop').write_text(f'''[Desktop Entry]
Type=Application
Name=Native Test App
Exec={stub} launch
Icon=utilities-terminal
Actions=New;
Keywords=testing;sample;
[Desktop Action New]
Name=New test window
Exec={stub} app-action
''')
    env=dict(os.environ,HOME=temp,XDG_CONFIG_HOME=str(config),XDG_DATA_HOME=str(work),XDG_DATA_DIRS=str(work/'system-data'),SIMPLEPICKER_ASSETS=str(root/'assets'),SIMPLEPICKER_DATA_DIR=str(data),PATH=str(bin_dir)+':/usr/bin:/bin',SP_LOG=str(log),SP_COPIED=str(copied),SP_IMAGE=str(image),G_DEBUG='fatal-criticals')
    env.pop('SIMPLEPICKER_CONFIG',None);env.pop('SIMPLEPICKER_THEME',None)
    def run(name,args,plan,expected=0,stdin=''):
        path=work/'plan.json';path.write_text(json.dumps(plan))
        result=subprocess.run([os.environ.get('SP_TEST_DRIVER',str(root/'tests/driver')),*args],input=stdin,text=True,capture_output=True,env=dict(env,SP_TEST_PLAN=str(path)),timeout=20)
        assert result.returncode==expected,(name,result.returncode,result.stdout,result.stderr)
        assert 'CRITICAL' not in result.stderr and 'TEST:' not in result.stderr,(name,result.stderr)
        print('PASS:',name,flush=True)
        return result
    run('short menu fits rows',['-d'],[{'max_panel_height':480,'key':'Escape'}],expected=1,stdin='One\nTwo\nThree\nFour\nFive\nSix\nClose\n')
    run('dmenu filtering and selection',['-d'],[{'query':'cafe'},{'key':'Return'}],stdin='Other\nCafé\n')
    run('masked input',['-x'],[{'query':'secret text'},{'key':'Return'}])
    run('app launch',['--apps'],[{'select':'native-test.desktop','key':'Return'}])
    run('desktop app actions',['--apps'],[{'select':'native-test.desktop','key':'a','ctrl':True},{'select':'New','key':'Return'}])
    run('runner',['--runner'],[{'query':str(stub)+' runner-test'},{'key':'Return'}])
    run('calculator evaluate/copy/edit/full',['--calc'],[{'query':'2+2'},{'key':'Return'},{'key':'e','ctrl':True},{'key':'f','ctrl':True}])
    assert copied.read_text()=='2+2 = 4'
    run('clipboard text preview/copy',['--clipboard'],[{'wait':700},{'expect_preview':'longer preview','key':'Return'}])
    assert copied.read_text().startswith('Example clipboard text')
    run('clipboard image preview/copy',['--clipboard'],[{'select':'2\t[[ binary data 80 B png 2x2 ]]','wait':1500},{'expect_preview':'image','key':'Return'}])
    assert copied.read_bytes()==image.read_bytes()
    run('clipboard delete and binary plain-paste refusal',['--clipboard'],[{'key':'d','ctrl':True},{'select':'3\t[[ binary data 90 B application/pdf ]]','key':'p','ctrl':True},{'close':True}])
    run('clipboard plain paste',['--clipboard'],[{'key':'p','ctrl':True}])
    run('web prefix',['--websearch'],[{'query':'t café words'},{'key':'Return'}])
    run('web engine menu',['--websearch'],[{'query':'plain query'},{'key':'Return'}])
    run('bookmark open/history',['--bookmarks'],[{'key':'Return'}])
    run('bookmark add with tag',['--bookmark-add'],[{'query':'New example'},{'key':'Return'},{'query':' Reference '},{'key':'Return'}])
    records=json.loads((data/'bookmarks.json').read_text())
    assert len(records)==2 and records[-1]['category']=='Reference'
    run('bookmark cancel at tag',['--bookmark-add'],[{'query':'Cancelled'},{'key':'Return'},{'key':'Escape'}])
    assert json.loads((data/'bookmarks.json').read_text())==records
    run('bookmark optional empty tag',['--bookmark-add'],[{'query':'Untagged'},{'key':'Return'},{'key':'Return'}])
    records=json.loads((data/'bookmarks.json').read_text())
    assert len(records)==3 and 'category' not in records[-1]
    run('window focus',['--windows'],[{'key':'Return'}])
    run('window move',['--windows'],[{'key':'m','ctrl':True}])
    run('window close',['--windows'],[{'key':'d','ctrl':True}])
    run('symbols',['--symbols'],[{'query':'smile'},{'key':'Return'}])
    run('font preview sample and copy',['--fonts'],[{'key':'t','ctrl':True},{'query':'Custom sample'},{'key':'Return'},{'key':'Return'}])
    assert (data/'font-preview.txt').read_text()=='Custom sample'
    run('power cancellation',['--power'],[{'close':True}])
    run('power selected action uses configured command',['--power'],[{'key':'e'}])
    # Python adapter exercises the unchanged public script API against the native UI.
    installed=str(Path.home()/'.local/lib/simplepicker')
    bridge_cases=[
        ("selection", "assert show_menu(line_search(['Café','Other']))=='Café'", [{'query':'cafe'},{'key':'Return'}]),
        ("input", "assert show_menu(lambda q:[],input_only=True)=='Typed value'", [{'query':'Typed value'},{'key':'Return'}]),
        ("preview/back", "assert Menu('Report').choose({'a':'Alpha','b':'Beta'},preview={'a':'Full alpha report','b':'Full beta report'})==BACK", [{'wait':500},{'expect_preview':'Full alpha','key':'h','ctrl':True}]),
    ]
    for name,body,steps in bridge_cases:
        path=work/'plan.json';path.write_text(json.dumps(steps))
        script=work/'bridge-test.py'
        script.write_text(f"import sys\nsys.path[:0]=[{str(root/'python')!r},{installed!r}]\nfrom ui import show_menu,line_search\nfrom simplepicker_api import Menu,BACK\n"+body+'\n')
        result=subprocess.run(['python3',str(script)],env=dict(env,SIMPLEPICKER_NATIVE=os.environ.get('SP_TEST_DRIVER',str(root/'tests/driver')),SP_TEST_PLAN=str(path)),capture_output=True,text=True,timeout=20)
        assert result.returncode==0,(name,result.stdout,result.stderr)
        print('PASS: script bridge '+name,flush=True)
    events=[json.loads(line) for line in log.read_text().splitlines()]
    for wanted in ('launch','app-action','runner-test','focus','move','close','power-lock','paste'):
        assert any(wanted in event for event in events),wanted
    assert not any('power-shutdown' in e or 'power-reboot' in e for e in events)
    (root/'tests/gui-actions.json').write_text(json.dumps(events,indent=2))
print('Native provider GUI checks passed; all external actions used test stubs.')

from pathlib import Path
import tempfile,os,json,subprocess,sys
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
    work=Path(tmp);bin_dir=work/'bin';bin_dir.mkdir();log=work/'calls.jsonl'
    helper=bin_dir/'stub'
    helper.write_text('''#!/usr/bin/python3
import os,sys,json
from pathlib import Path
name=Path(sys.argv[0]).name;args=sys.argv[1:]
with open(os.environ['SP_BACKEND_LOG'],'a') as f:f.write(json.dumps([name,*args])+'\\n')
if name=='mmsg':
 if args==['get','all-clients']:print(json.dumps(dict(clients=[dict(id=101,appid='app',title='Title',tags=[1],monitor='old',is_focused=True)])))
 elif args==['get','all-monitors']:print(json.dumps(dict(monitors=[dict(name='new',active=True,active_tags=[2,3])])))
elif name=='hyprctl':
 if args==['-j','clients']:print(json.dumps([dict(address='0xabc',title='Title',workspace=dict(name='1'),monitor=1,**{'class':'app'})]))
 elif args==['-j','activewindow']:print(json.dumps(dict(address='0xabc')))
 elif args==['-j','activeworkspace']:print(json.dumps(dict(id=2,monitor='new')))
elif name=='swaymsg':
 if args==['-r','-t','get_tree']:print(json.dumps(dict(type='root',nodes=[dict(type='output',name='old',nodes=[dict(type='workspace',name='1',nodes=[dict(id=101,app_id='app',name='Title',focused=True)])])])))
 elif args==['-r','-t','get_workspaces']:print(json.dumps([dict(name='2',output='new',focused=True)]))
 else:print('[{"success":true}]')
''');helper.chmod(0o755)
    for name in ('mmsg','hyprctl','swaymsg'):(bin_dir/name).symlink_to(helper)
    env=dict(os.environ,PATH=str(bin_dir)+':/usr/bin:/bin',SP_BACKEND_LOG=str(log))
    for backend,lua in [('mango',False),('sway',False),('hyprland',False),('hyprland',True)]:
        cfg=work/'config.toml';cfg.write_text(f'[desktop]\nbackend="{backend}"\nhyprland_dispatch="'+('lua' if lua else 'legacy')+'"\n')
        log.write_text('')
        result=subprocess.run([str(root/'tests/desktop-check'),str(root/'assets'),str(cfg)],env=env,capture_output=True,text=True)
        assert result.returncode==0,(backend,result.stderr)
        native_calls=log.read_text()
        log.write_text('')
        python_code=f'''import sys
sys.path.insert(0,{str(Path.home()/'.local/lib/simplepicker')!r})
import settings,desktop
settings.load({str(cfg)!r})
windows=desktop.windows();current=desktop.current()
for action in ['focus','close','move']:desktop.perform(action,windows[0],current)
'''
        reference=subprocess.run(['python3','-c',python_code],env=env,capture_output=True,text=True)
        assert reference.returncode==0,reference.stderr
        c=[json.loads(line) for line in native_calls.splitlines()]
        py=[json.loads(line) for line in log.read_text().splitlines()]
        assert sorted(c)==sorted(py),(backend,c,py)
        print('PASS: native commands match Python backend:',backend,'Lua' if lua else 'legacy')

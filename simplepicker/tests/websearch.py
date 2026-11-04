"""Exercise real GTK Websearch with URL opening stubbed out."""
import json,os,subprocess,tempfile,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='websearch-check-') as tmp:
 w=Path(tmp);cfg=w/'config/simplepicker';(cfg/'websearch').mkdir(parents=True)
 log=w/'urls';helper=w/'open'
 helper.write_text('#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\nwith Path('+repr(str(log))+').open("a") as f:f.write(sys.argv[1]+"\\n")\n');helper.chmod(0o755)
 (cfg/'config.toml').write_text('[commands]\nopen_url='+json.dumps([str(helper),'{url}'])+'\n')
 engines=[dict(name='Web engine',url='https://example.test/?q=%TERM%',prefix='w:'),dict(name='Picture engine',url='https://example.test/images?q=%TERM%',prefix='im:',type='images')]
 (cfg/'websearch/engines.json').write_text(json.dumps(engines))
 # Exercise actual theme overrides without modifying personal configuration.
 for f in ['style.css','status-colors.css']:
  shutil.copy2(Path.home()/'.config/simplepicker'/f,cfg/f)
 shutil.copytree(Path.home()/'.config/simple',w/'config/simple')
 style=root.parent/'style.css'
 if not style.exists():style=Path.home()/'.config/simplepicker/websearch/style.css'
 shutil.copy2(style,cfg/'websearch/style.css')
 env=dict(os.environ,XDG_CONFIG_HOME=str(w/'config'),SIMPLEPICKER_DATA_DIR=str(w/'state'),SIMPLEPICKER_ASSETS=str(root/'assets'),G_DEBUG='fatal-criticals',SIMPLEPICKER_VIM_MENU='1')
 env.pop('SIMPLEPICKER_THEME',None);env.pop('SIMPLEPICKER_CONFIG',None)
 extra=[]
 def run(name,plan,expected):
  log.write_text('');p=w/'plan.json';p.write_text(json.dumps(plan))
  out=subprocess.run([str(root/'tests/driver'),'--websearch',*extra],env=dict(env,SP_TEST_PLAN=str(p)),capture_output=True,text=True,timeout=15)
  assert out.returncode==0,(name,out.stderr)
  assert not any(x in out.stderr for x in ['CRITICAL','Theme parser error','TEST:']),(name,out.stderr)
  # URL helper is intentionally asynchronous.
  import time
  for _ in range(30):
   if log.read_text().splitlines()==expected:break
   time.sleep(.05)
  assert log.read_text().splitlines()==expected,(name,log.read_text())
  print('PASS',name,flush=True)
 run('one window and escaped query',[{'query':'café & cats'},{'key':'Return'}],['https://example.test/?q=caf%C3%A9%20%26%20cats'])
 run('image switch preserves query',[{'query':'cats'},{'key':'l','ctrl':True},{'select':'Picture engine','key':'Return'}],['https://example.test/images?q=cats'])
 run('web switch preserves query',[{'query':'cats'},{'key':'l','ctrl':True},{'key':'h','ctrl':True},{'select':'Web engine','key':'Return'}],['https://example.test/?q=cats'])
 run('image prefix overrides current mode',[{'query':'im: blue sky'},{'key':'Return'}],['https://example.test/images?q=blue%20sky'])
 run('empty input stays open',[{'key':'Return'},{'query':'   '},{'key':'Return'},{'close':True}],[])
 run('prefix alone stays open',[{'query':'im: '},{'key':'Return'},{'close':True}],[])
 run('mode change removes image prefix',[{'query':'im: blue sky'},{'key':'h','ctrl':True},{'select':'Web engine','key':'Return'}],['https://example.test/?q=blue%20sky'])
 run('escape cancels',[{'query':'nothing'},{'key':'Escape'}],[])

 actual=json.loads((Path.home()/'.config/simplepicker/websearch/engines.json').read_text())
 actual=[e for e in actual if e['name'].lower()!='ecosia']
 (cfg/'websearch/engines.json').write_text(json.dumps(actual))
 run('all configured web engines fit',[{'wait':500},{'expect_all_visible':True,'close':True}],[])
 run('all configured image engines fit',[{'key':'l','ctrl':True},{'wait':500},{'expect_all_visible':True,'close':True}],[])

 (cfg/'websearch/engines.json').write_text(json.dumps(engines))
 (w/'config/simple/keys.ini').write_text('[navigation]\nright=<Control>o\n')
 run('shared binding override',[{'query':'cats'},{'key':'o','ctrl':True},{'select':'Picture engine','key':'Return'}],['https://example.test/images?q=cats'])
 (cfg/'keys.ini').write_text('[navigation]\nright=<Control>p\n')
 run('app override wins',[{'query':'cats'},{'key':'p','ctrl':True},{'select':'Picture engine','key':'Return'}],['https://example.test/images?q=cats'])
 (cfg/'websearch/keys.ini').write_text('[navigation]\nright=<Control>n\n')
 run('module override wins',[{'query':'cats'},{'key':'n','ctrl':True},{'select':'Picture engine','key':'Return'}],['https://example.test/images?q=cats'])
 override=w/'custom.ini';override.write_text('[navigation]\nright=<Control>u\nactivate=<Control>e\n')
 extra[:]=['--keys',str(override)]
 run('custom override wins and inherits other keys',[{'query':'cats'},{'key':'u','ctrl':True},{'select':'Picture engine','key':'Return'},{'key':'e','ctrl':True}],['https://example.test/images?q=cats'])

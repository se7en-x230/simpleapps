import os,sys,tempfile,subprocess,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from client import Client
from mutagen.flac import FLAC
with tempfile.TemporaryDirectory(prefix='simpletag-live-') as d:
 r=Path(d);runtime=r/'run';runtime.mkdir(mode=0o700);music=r/'music';music.mkdir()
 cfg=r/'picard.ini';cfg.write_text('[setting]\ncheck_for_updates=false\ncheck_for_plugin_updates=false\nuse_adv_search_syntax=false\nsession_load_last_on_startup=false\nsession_autosave_interval_min=0\nrename_files=false\nmove_files=false\n')
 audio=music/'generated.flac'
 subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','anullsrc=r=44100:cl=mono','-t','0.1',str(audio)],check=True)
 env=dict(os.environ,HOME=d,XDG_CONFIG_HOME=str(r/'config'),XDG_DATA_HOME=str(r/'data'),XDG_CACHE_HOME=str(r/'cache'),XDG_STATE_HOME=str(r/'state'),XDG_RUNTIME_DIR=str(runtime),QT_QPA_PLATFORM='offscreen')
 os.environ['XDG_RUNTIME_DIR']=str(runtime);client=Client()
 with (r/'log').open('w') as log:
  p=subprocess.Popen([sys.executable,str(Path(__file__).with_name('picard-fixture.py')),'-s','-M','-P','-c',str(cfg),'--no-crash-dialog'],env=env,stdout=log,stderr=log)
  try:
   def wait(predicate,limit=20):
    deadline=time.monotonic()+limit
    while time.monotonic()<deadline:
     if p.poll() is not None:raise RuntimeError((r/'log').read_text()[-3500:])
     try:
      result=client.request('status')
      if predicate(result):return result
     except (ConnectionError,FileNotFoundError):pass
     time.sleep(.15)
    raise RuntimeError('Timed out: '+(r/'log').read_text()[-3500:])
   wait(lambda s:not s['busy'],40)
   assert client.request('load',folder=str(music))['ok']
   status=wait(lambda s:not s['busy'] and len(s['groups'])==1)
   assert status['groups'][0]['kind']=='unmatched'
   assert client.request('test-match')['ok']
   assert client.request('save',group='album:test')['ok']
   wait(lambda s:not s['busy'] and not s['groups'])
   assert FLAC(audio)['title']==['Simpletag saved test']
   assert audio.exists()
   saved = audio.read_bytes()
   assert client.request('load',folder=str(music))['ok']
   state = wait(lambda s:not s['busy'] and len(s['groups'])==1)
   assert client.request('remove',group=state['groups'][0]['id'])['ok']
   wait(lambda s:not s['groups'])
   assert audio.read_bytes()==saved
   assert client.request('load',folder=str(music))['ok']
   wait(lambda s:not s['busy'] and bool(s['groups']))
   assert client.request('clear')['ok']
   wait(lambda s:not s['groups'])
   assert audio.read_bytes()==saved
   assert client.request('test-quit')['ok'];p.wait(timeout=10)
   print('PASS real Picard: local socket, generated-folder load, tag save, successful removal from list; remove without saving leaves audio bytes unchanged')
  finally:
   if p.poll() is None:
    p.kill();p.wait(timeout=5)

#!/usr/bin/env python3
"""Record/stop lifecycle tests with fake capture/audio and a real process lock."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os,sys,subprocess,time,json,fcntl
app=Path(__file__).with_name('simplecapture')
with TemporaryDirectory() as tmp:
 root=Path(tmp);bins=root/'bin';bins.mkdir();runtime=root/'run';runtime.mkdir();config=root/'config/simplecapture';config.mkdir(parents=True)
 helper=bins/'helper';helper.write_text('''#!/usr/bin/env python3
import os,sys,time,signal,json
from pathlib import Path
from urllib.parse import urlparse,unquote
root=Path(os.environ['RECORD_TEST']);name=Path(sys.argv[0]).name
with (root/'calls').open('a') as f:f.write(json.dumps([name,*sys.argv[1:]])+'\\n')
if name=='slurp':
 if os.environ.get('CANCEL'):sys.exit(1)
 print('0,0 640x480')
elif name=='pactl':print('test-sink')
elif name=='wl-copy':
 payload=sys.stdin.buffer.read();video=Path(unquote(urlparse(payload.decode().strip()).path))
 assert video.read_bytes().endswith(b'trailer'), 'Copied before recorder finalized video'
 (root/'clipboard').write_bytes(payload)
else:
 target=Path(sys.argv[sys.argv.index('-f')+1]);target.write_bytes(b'video')
 state={'stop':False}
 def stop(*_):state['stop']=True
 signal.signal(signal.SIGINT,stop)
 (root/'started').write_text(str(target))
 while not state['stop']:time.sleep(.02)
 time.sleep(.1)
 with target.open('ab') as f:f.write(b'trailer')
''');helper.chmod(0o755)
 for name in ('wf-recorder','wl-screenrec','pactl','wl-copy','slurp'):(bins/name).symlink_to(helper)
 env=dict(os.environ,HOME=str(root),XDG_CONFIG_HOME=str(root/'config'),XDG_RUNTIME_DIR=str(runtime),WAYLAND_DISPLAY='test-private',PATH=str(bins)+':'+os.environ['PATH'],RECORD_TEST=str(root))
 for recorder,audio,copy in [('wf-recorder',True,True),('wl-screenrec',False,False)]:
  (root/'started').unlink(missing_ok=True);(root/'clipboard').unlink(missing_ok=True);(root/'calls').write_text('')
  settings=f'save_dir="{root}/shots"\nrecord_dir="{root}/videos with spaces"\nrecorder="{recorder}"\nrecord_audio={str(audio).lower()}\nrecord_copy={str(copy).lower()}\nnotify=false\nsettle_ms=0\n'
  (config/'config.toml').write_text(settings)
  first=subprocess.Popen([sys.executable,str(app),'--record'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  try:
   for _ in range(100):
    if (root/'started').exists():break
    if first.poll() is not None:raise AssertionError(first.communicate())
    time.sleep(.03)
   assert (root/'started').exists()
   stop=subprocess.run([sys.executable,str(app),'--record'],env=env,capture_output=True,timeout=5)
   assert stop.returncode==0,stop.stderr
   stdout,stderr=first.communicate(timeout=5);assert first.returncode==0,stderr
   assert not (runtime/'simplecapture-recording.pid').exists()
   assert (root/'clipboard').exists()==copy
   calls=[json.loads(line) for line in (root/'calls').read_text().splitlines()]
   actual=next(c for c in calls if c[0]==recorder)
   assert ('--audio=test-sink.monitor' in actual)==audio
   assert any(c[0]=='pactl' for c in calls)==audio
   assert Path((root/'started').read_text()).read_bytes()==b'videotrailer'
  finally:
   if first.poll() is None:first.terminate();first.wait(timeout=5)
 # Cancellation must never launch a recorder.
 (root/'calls').write_text('')
 result=subprocess.run([sys.executable,str(app),'--record'],env=env|{'CANCEL':'1'},capture_output=True,timeout=5)
 assert result.returncode==0,result.stderr
 assert not any(json.loads(line)[0] in ('wf-recorder','wl-screenrec') for line in (root/'calls').read_text().splitlines())
 # A mismatched start time must never signal the unrelated owner PID.
 guard=(runtime/'simplecapture-recording.pid.guard').open('w');fcntl.flock(guard,fcntl.LOCK_EX)
 (runtime/'simplecapture-recording.pid').write_text(f'{os.getpid()} 0\n')
 result=subprocess.run([sys.executable,str(app),'--record'],env=env,capture_output=True,timeout=5)
 assert result.returncode!=0
 print('PASS: toggle start/stop, finalize-before-copy, encoded file URI, audio on/off, both recorders, cancellation and stale-PID protection')

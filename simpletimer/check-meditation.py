from pathlib import Path
from tempfile import TemporaryDirectory
from importlib.machinery import SourceFileLoader
from unittest.mock import patch
import os,subprocess,wave,shutil
m=SourceFileLoader('timer',str(Path(__file__).with_name('simpletimer'))).load_module()
with TemporaryDirectory() as td:
 root=Path(td);state=root/'state.json';fast=root/'fast/start'
 t=m.Timers(m.DEFAULTS,state,fast)
 with patch.object(m.time,'time',return_value=10000):t.set_meditation(30);t.toggle('meditation')
 assert not t.meditation_events(10599)
 assert t.meditation_events(10600)==['Meditation · 10 minutes elapsed']
 assert not t.meditation_events(10600)
 with patch.object(m.time,'time',return_value=10630):t.toggle('meditation')
 assert t.value('meditation',12000)==1170 and not t.meditation_events(12000)
 t=m.Timers(m.DEFAULTS,state,fast)
 with patch.object(m.time,'time',return_value=12000):t.toggle('meditation')
 assert not t.meditation_events(12569)
 assert t.meditation_events(12570)==['Meditation · 20 minutes elapsed']
 assert t.meditation_events(13170)==['Meditation finished']
 assert not t.meditation_events(20000)
 t=m.Timers(m.DEFAULTS,state,fast);assert not t.meditation_events(20000)
 with patch.object(m.time,'time',return_value=20000):t.toggle('meditation')
 assert t.state('meditation')['total']==1800
 assert t.meditation_events(21205)==['Meditation · 20 minutes elapsed']
 assert not t.meditation_events(21206)
 assert t.meditation_events(24000)==['Meditation finished']
 for value in (-1,float('nan'),float('inf'),100001):
  before=state.read_bytes()
  try:t.set_meditation(value)
  except ValueError:pass
  else:raise AssertionError('Invalid duration accepted')
  assert state.read_bytes()==before
 with patch.object(m.time,'time',return_value=30000):t.set_meditation(0);t.toggle('meditation')
 assert t.value('meditation',30600)==600
 assert t.meditation_events(30600)==['Meditation · 10 minutes elapsed']
 assert t.meditation_events(31800)==['Meditation · 30 minutes elapsed']
 with patch.object(m.time,'time',return_value=31900):t.toggle('meditation')
 t=m.Timers(m.DEFAULTS,state,fast);assert t.value('meditation',40000)==1900
 assert not t.meditation_events(40000)
 with patch.object(m.time,'time',return_value=40000):t.toggle('meditation')
 assert t.meditation_events(40500)==['Meditation · 40 minutes elapsed']
 with patch.object(m.time,'time',return_value=40500):assert t.finish_meditation()
 assert not t.finish_meditation() and t.value('meditation',50000)==2400
 assert not t.meditation_events(50000)
 t.state('meditation')['mute_waypoints']=True;t.set_meditation(15)
 assert m.Timers(m.DEFAULTS,state,fast).state('meditation')['mute_waypoints'] is True
 assert not fast.exists()
 with patch.dict(os.environ,{'XDG_CONFIG_HOME':str(root/'config'),'XDG_STATE_HOME':str(root/'state')}):
  config=root/'config/simpletimer/config.toml';config.parent.mkdir(parents=True)
  config.write_text('meditation_minutes=0\n');assert m.settings(False)[0]['meditation_minutes']==0
  config.write_text('meditation_minutes=-1\n')
  try:m.settings(False)
  except ValueError:pass
  else:raise AssertionError('Invalid default accepted')
 frames=[]
 def player(command,**kwargs):
  assert command[0]=='/fake/paplay'
  with wave.open(command[1]) as f:
   assert f.getnchannels()==1;frames.append(f.getnframes())
  return subprocess.CompletedProcess(command,0,b'',b'')
 with patch.object(shutil,'which',side_effect=lambda name:'/fake/paplay' if name=='paplay' else None),patch.object(subprocess,'run',side_effect=player):
  m.play_bell();m.play_bell('boundary')
 assert frames==[70560,132300]
 with patch.object(shutil,'which',return_value=None):
  try:m.play_bell()
  except OSError:pass
  else:raise AssertionError('Missing sound player not reported')
print('PASS: fixed 10-minute cues, timed/open-ended sessions, pause/restart, overdue coalescing, finish once, mute persistence, two generated bells and player fallback')

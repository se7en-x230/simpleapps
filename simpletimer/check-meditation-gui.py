from pathlib import Path
from tempfile import TemporaryDirectory
from importlib.machinery import SourceFileLoader
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib,Gdk
m=SourceFileLoader('timer',str(Path(__file__).with_name('simpletimer'))).load_module()
present=Gtk.ApplicationWindow.present;errors=[];sounds=[];stage=0
with TemporaryDirectory() as td:
 root=Path(td);model=m.Timers(m.DEFAULTS|{'notify':False},root/'state',root/'fast/start')
 def patched(win):
  present(win);app=win.get_application()
  def tick():
   global stage
   try:
    if app.sound_busy:return True
    if stage==0:
     app.key(None,Gdk.KEY_5,0,0);assert app.mode=='meditation'
     assert app.entry.get_visible() and app.mute.get_visible()
     app.entry.set_text('30');app.apply();app.key(None,Gdk.KEY_space,0,0);stage=1
    elif stage==1:
     assert sounds==['boundary'];app.hide();clock.return_value=10600;app.tick();stage=2
    elif stage==2:
     assert sounds==['boundary','waypoint'];app.tick();assert len(sounds)==2
     app.key(None,Gdk.KEY_m,0,0);assert model.state('meditation')['mute_waypoints']
     clock.return_value=11200;app.tick();stage=3
    elif stage==3:
     assert len(sounds)==2
     app.select('countdown');clock.return_value=11800;app.tick();stage=4
    elif stage==4:
     assert sounds==['boundary','waypoint','boundary']
     app.select('meditation');app.entry.set_text('0');app.apply();assert app.mute.get_active()
     app.key(None,Gdk.KEY_m,0,0);clock.return_value=20000;app.action();stage=5
    elif stage==5:
     assert sounds[-1]=='boundary';clock.return_value=20600;app.tick();stage=6
    elif stage==6:
     assert sounds[-1]=='waypoint' and model.value('meditation')==600
     app.action();clock.return_value=21200;app.tick();assert model.value('meditation')==600
     app.action();app.key(None,Gdk.KEY_f,0,0);stage=7
    elif stage==7:
     assert sounds==['boundary','waypoint','boundary','boundary','waypoint','boundary']
     app.key(None,Gdk.KEY_f,0,0);assert model.state('meditation')['done']
     app.key(None,Gdk.KEY_h,0,0);assert app.mode=='fasting'
     app.key(None,Gdk.KEY_l,0,0);assert app.mode=='meditation'
     app.key(None,Gdk.KEY_Escape,0,0);assert not win.get_visible()
     print('PASS: meditation keyboard controls, fixed interval, start/end bells, mute leaves boundary bells audible, hidden-window alerts, open end and manual finish',flush=True)
     app.quit();return False
   except BaseException as exc:errors.append(exc);app.quit();return False
   return True
  GLib.timeout_add(150,tick)
 with patch.object(Gtk.ApplicationWindow,'present',patched),patch.object(m.time,'time',return_value=10000) as clock,patch.object(m,'play_bell',side_effect=lambda kind:sounds.append(kind)):
  m.gui(model,'meditation')
if errors:raise errors[0]

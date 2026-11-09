"""Exercise real GTK controls through the apps' capture-phase key handlers."""
import ast,sys,time
from pathlib import Path
from types import SimpleNamespace
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,GLib
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'simple-common'))
from simple_keyboard import control_key
Gtk.init();win=Gtk.Window();box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);win.set_child(box)
button=Gtk.Button(label='Action');check=Gtk.CheckButton(label='Toggle');slider=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,100,1);entry=Gtk.Entry()
for widget in [button,check,slider,entry]:box.append(widget)
win.present();hits=[];button.connect('clicked',lambda *_:hits.append(1))
def pump():
 until=time.monotonic()+.35
 while time.monotonic()<until:
  while GLib.MainContext.default().iteration(False):pass
  time.sleep(.005)
pump()
apps=['simplefiles','simplenotes','simpleimage','simplepdf','simplephoto','simpletimer','simplebookmarks','simplecapture']
for app in apps:
 tree=ast.parse((root/app/app).read_text())
 fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='key' and n.args.args[0].arg=='self')
 scope={'Gtk':Gtk,'Gdk':Gdk,'control_key':control_key}
 exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(root/app/app),'exec'),scope)
 handler=scope['key'];fake=SimpleNamespace(win=win,prefix='g')
 button.grab_focus();before=len(hits)
 assert handler(fake,None,Gdk.KEY_Return,0,0) is True
 pump();assert len(hits)==before+1,app
 assert handler(fake,None,Gdk.KEY_space,0,0) is False,app
 assert handler(fake,None,Gdk.KEY_Tab,0,0) is False and fake.prefix=='',app
 check.grab_focus();old=check.get_active();assert handler(fake,None,Gdk.KEY_Return,0,0) is True;pump();assert check.get_active()!=old,app
 slider.grab_focus();assert handler(fake,None,Gdk.KEY_Right,0,0) is False,app
 print('PASS focused controls:',app,flush=True)
entry.grab_focus();assert control_key(win,Gdk.KEY_Return,0) is None
assert control_key(win,Gdk.KEY_Tab,0) is False
button.grab_focus();assert control_key(win,Gdk.KEY_Return,Gdk.ModifierType.CONTROL_MASK) is None
win.destroy()

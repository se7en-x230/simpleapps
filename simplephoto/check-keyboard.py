"""Real photo UI: keyboard brush positioning/paint/erase/undo on temporary pixels."""
from pathlib import Path
from tempfile import TemporaryDirectory
from importlib.machinery import SourceFileLoader
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,GLib
from PIL import Image
import numpy as np
m=SourceFileLoader('photo',str(Path(__file__).with_name('simplephoto'))).load_module()
errors=[];done=[];present=Gtk.ApplicationWindow.present
with TemporaryDirectory() as tmp:
 path=Path(tmp)/'test.png';Image.new('RGB',(300,200),(80,100,120)).save(path);original=path.read_bytes()
 def patched(win):
  present(win);app=win.get_application();ticks=0
  def test():
   nonlocal ticks
   ticks+=1
   if (app.data is None or app.busy or not app.pix) and ticks<100:return True
   try:
    app.area.grab_focus();app.toggle_brush();app.keyboard_brush(Gdk.KEY_Right)
    first=app.cursor;app.keyboard_brush(Gdk.KEY_Right,True);assert app.cursor[0]>first[0]
    app.key(None,Gdk.KEY_p,0,0);assert np.asarray(app.mask).min()==0
    app.key(None,Gdk.KEY_P,0,Gdk.ModifierType.SHIFT_MASK);assert np.asarray(app.mask).min()>0
    app.undo_mask();assert np.asarray(app.mask).min()==0
    app.key(None,Gdk.KEY_Tab,0,0);assert path.read_bytes()==original
    done.append(True);print('PASS photo: keyboard brush move, paint, erase, undo; original untouched',flush=True)
   except BaseException as e:errors.append(e)
   app.quit();return False
  GLib.timeout_add(150,test)
 with patch.object(Gtk.ApplicationWindow,'present',patched):m.main([str(path)])
if errors:raise errors[0]
assert done

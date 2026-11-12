from pathlib import Path
from importlib.machinery import SourceFileLoader
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib,Gdk
m=SourceFileLoader('capture',str(Path(__file__).with_name('simplecapture'))).load_module()
present=Gtk.ApplicationWindow.present;errors=[]
def patched(win):
 present(win);app=win.get_application()
 def check():
  try:
   assert win.has_css_class('simple-app')
   assert win.get_child().get_first_child().has_css_class('title')
   assert app.list.has_css_class('simple-list') and win.get_height()<500
   for _ in range(8):app.key(None,Gdk.KEY_j,0,Gdk.ModifierType.CONTROL_MASK)
   assert app.list.get_selected_row().get_index()==4
   app.key(None,Gdk.KEY_k,0,0)
   assert app.list.get_selected_row().get_index()==3
   app.key(None,Gdk.KEY_Return,0,0)
  except BaseException as e:errors.append(e);win.close()
  return False
 GLib.timeout_add(300,check)
with patch.object(Gtk.ApplicationWindow,'present',patched):result=m.menu(m.DEFAULTS)
if errors:raise errors[0]
assert result['mode']=='fullscreen' and result['edit'] is False
print('PASS shared capture menu styling, compact height, keyboard boundaries and Enter action; no capture performed')

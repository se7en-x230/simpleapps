from pathlib import Path
from tempfile import TemporaryDirectory
from importlib.machinery import SourceFileLoader
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
m=SourceFileLoader('bookmarks',str(Path(__file__).with_name('simplebookmarks'))).load_module()
present=Gtk.Window.present;errors=[];passed=[]
with TemporaryDirectory() as td:
 store=m.Store(Path(td)/'bookmarks.json')
 def show(win):
  present(win)
  if win.get_title()!='Add bookmark':return
  app=win.get_application()
  def check():
   try:
    assert app and app.get_application_id()=='org.simpleapps.Simplebookmarks'
    assert not app.win.get_visible()
    assert win.get_visible() and win.get_transient_for() is None
    assert win.has_css_class('simple-app')
    assert win.get_width()<700 and win.get_height()<500,(win.get_width(),win.get_height())
    label,url,error=app.edit_fields
    label.set_text('Test');url.set_text('https://example.org');app.edit_tag.set_text('Test tag')
    error.get_next_sibling().get_last_child().emit('clicked')
    assert len(store.records)==1 and store.records[0]['category']=='Test tag'
    assert app.dialog is None
    passed.append(True)
   except BaseException as e:errors.append(e);app.quit()
   return False
  GLib.timeout_add(400,check)
 with patch.object(Gtk.Window,'present',show):m.gui(m.DEFAULTS,store,True)
if errors:raise errors[0]
assert passed
print('PASS standalone compact Add dialog, application identity, hidden manager, tag save and exit')

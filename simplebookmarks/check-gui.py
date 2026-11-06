from pathlib import Path
from tempfile import TemporaryDirectory
from importlib.machinery import SourceFileLoader
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib,Gdk,Gio
m=SourceFileLoader('bookmarks',str(Path(__file__).with_name('simplebookmarks'))).load_module()
present=Gtk.ApplicationWindow.present;errors=[];opened=[]
with TemporaryDirectory() as td:
 store=m.Store(Path(td)/'bookmarks.json')
 for name in ('Alpha','Beta','Gamma'):store.change(None,{'label':name,'url':'https://example.com/'+name,'category':'Reference' if name=='Gamma' else ''})
 def patched(win):
  present(win);app=win.get_application()
  def test():
   try:
    key=lambda name,mods=0:app.key(None,Gdk.keyval_from_name(name),0,mods)
    dialog=lambda name,mods=0:app.dialog_keys_controller.emit('key-pressed',Gdk.keyval_from_name(name),0,mods)
    ctrl=Gdk.ModifierType.CONTROL_MASK
    key('Return',ctrl);key('j');assert app.selected()==1
    key('x',ctrl);assert app.dialog is None
    key('e');assert app.dialog
    label,url,error=app.edit_fields;label.set_text('Edited');dialog('Tab');assert app.dialog.get_focus().is_ancestor(url)
    dialog('Return',ctrl);assert store.records[1]['label']=='Edited'
    key('x');dialog('Escape');assert len(store.records)==3
    key('x');dialog('Tab');dialog('Return');assert len(store.records)==2
    key('a');label,url,error=app.edit_fields;label.set_text('New');url.set_text('javascript:bad');dialog('Return',ctrl);assert app.dialog and error.get_text()
    url.set_text('https://example.org');dialog('Return',ctrl);assert len(store.records)==3
    app.search.set_text('Reference');app.refresh();assert len(app.visible)==1
    key('Return');assert opened==['https://example.com/Gamma']
    app.search.set_text('');app.refresh();assert app.visible[0]==1
    assert m.Usage(store.path).count('https://example.com/Gamma')==1
    assert not app.hint.get_wrap() and app.hint.get_layout().get_line_count()==1
    print('PASS: search, Vim navigation, modifier safety, edit/save, keyboard removal and browser handoff',flush=True)
   except BaseException as exc:errors.append(exc)
   app.quit();return False
  GLib.timeout_add(300,test)
 with patch.object(Gtk.ApplicationWindow,'present',patched),patch.object(Gio.AppInfo,'launch_default_for_uri',side_effect=lambda uri,_:opened.append(uri)):
  m.gui(m.DEFAULTS|{'close_after_open':False},store)
if errors:raise errors[0]

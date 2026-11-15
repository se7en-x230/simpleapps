from pathlib import Path
from tempfile import TemporaryDirectory
from importlib.machinery import SourceFileLoader
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib,Gdk
m=SourceFileLoader('notes',str(Path(__file__).with_name('simplenotes'))).load_module()
present=Gtk.ApplicationWindow.present;errors=[];passed=[]
def patched(win):
 present(win);app=win.get_application()
 def check():
  if app.path is None:return True
  def key(name,ctrl=False):app.key(None,Gdk.keyval_from_name(name),0,Gdk.ModifierType.CONTROL_MASK if ctrl else Gdk.ModifierType(0))
  def reset(text):
   app.buffer.set_text(text);app.buffer.place_cursor(app.buffer.get_start_iter());app.preview_mode()
  def pos():return app.buffer.get_iter_at_mark(app.buffer.get_insert()).get_offset()
  try:
   reset('one two\n  three\nlast')
   key('w');assert pos()==4
   key('e');assert pos()==6
   key('b');assert pos()==4
   key('0');assert pos()==0
   key('j');assert pos()==8
   key('I');assert app.mode=='edit' and pos()==10
   key('Escape');assert app.mode=='preview' and not app.editor.get_editable()
   key('A');assert pos()==15 and app.mode=='edit'
   key('Escape');key('o');assert app.text()=='one two\n  three\n\nlast' and app.mode=='edit'
   key('Escape');key('u');assert app.text()=='one two\n  three\nlast'
   key('r',True);assert app.text()=='one two\n  three\n\nlast'
   reset('abc\ndef');key('a');assert pos()==1 and app.mode=='edit'
   key('Escape');key('x');assert app.text()=='ac\ndef'
   key('u');assert app.text()=='abc\ndef'
   key('0');key('d');key('d');assert app.text()=='def'
   key('u');assert app.text()=='abc\ndef'
   reset('last');key('O');assert app.text()=='\nlast' and pos()==0 and app.mode=='edit'
   key('Escape');key('j');key('d');key('d');assert app.text()==''
   app.save();assert app.path.read_text()==''
   passed.append(True);print('PASS Vim insert modes, motions, Escape, x/dd, undo/redo and saved text')
  except BaseException as e:errors.append(e)
  finally:app.quit()
  return False
 GLib.timeout_add(200,check)
Gtk.ApplicationWindow.present=patched
with TemporaryDirectory() as td:
 Path(td,'Note.md').write_text('test')
 m.main(['--notes-dir',td])
if errors:raise errors[0]
assert passed

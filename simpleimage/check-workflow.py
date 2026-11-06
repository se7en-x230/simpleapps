"""Real editor/viewer integration in an isolated graphical session; synthetic files only."""
from importlib.machinery import SourceFileLoader
from pathlib import Path
from tempfile import TemporaryDirectory
import argparse,sys
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
from PIL import Image
root=Path(__file__).resolve().parent.parent
m=SourceFileLoader('viewer',str(root/'simpleimage/simpleimage')).load_module()
present=Gtk.ApplicationWindow.present;errors=[]
def patched(win):
    present(win);app=win.get_application();attempts=0
    def start():
        nonlocal attempts
        attempts+=1
        if not app.pixbuf:
            if attempts<40:return True
            errors.append(AssertionError('Viewer load timed out'));app.close();app.quit();return False
        app.toggle_grid();app.selection.set_selected(1);app.edit();GLib.timeout_add(200,check);return False
    def check():
        nonlocal attempts
        attempts+=1
        try:
            if '~2' not in str(app.current()) or app.pixbuf is None:
                assert attempts<100,'Saved copy did not arrive';return True
            assert app.show_grid and app.selection.get_selected()==app.index
            assert app.current().name=='second~2.png',app.current()
            assert len(app.files)==3
            assert (app.current().parent/'second.png').read_bytes()==original
            print('PASS: selected thumbnail edited, Save visible in crop/blur, real save event selects copy in viewer, original preserved',flush=True)
        except BaseException as e:errors.append(e)
        app.close();app.quit();return False
    GLib.timeout_add(200,start)
Gtk.ApplicationWindow.present=patched
with TemporaryDirectory() as td:
    folder=Path(td);Image.new('RGB',(640,360),'#708899').save(folder/'first.png');Image.new('RGB',(240,120),'#bb8044').save(folder/'second.png');original=(folder/'second.png').read_bytes()
    helper=folder/'editor-check.py'
    helper.write_text('''import sys
from pathlib import Path
from importlib.machinery import SourceFileLoader
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
m=SourceFileLoader('photo',PHOTO).load_module()
present=Gtk.ApplicationWindow.present
def patched(win):
 present(win);app=win.get_application()
 def loaded():
  if app.busy or app.data is None:return True
  app.toggle_crop();assert app.header.get_visible() and app.save_button.get_visible()
  app.toggle_crop();app.toggle_brush();assert app.header.get_visible() and app.save_button.get_visible()
  app.toggle_brush()
  saved=app.saved
  def finish(path):saved(path);app.quit()
  app.saved=finish;app.save_clicked();return False
 GLib.timeout_add(150,loaded)
Gtk.ApplicationWindow.present=patched
m.main(sys.argv[1:])
'''.replace('PHOTO',repr(str(root/'simplephoto/simplephoto'))))
    launcher=folder/'simplephoto';import shlex
    launcher.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' '+shlex.quote(str(helper))+' "$@"\n');launcher.chmod(0o755)
    m.gui(m.DEFAULTS|{'editor':[str(launcher)]},argparse.Namespace(paths=[folder/'first.png']))
if errors:raise errors[0]

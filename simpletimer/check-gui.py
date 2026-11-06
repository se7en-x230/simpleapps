from importlib.machinery import SourceFileLoader
from pathlib import Path
from tempfile import TemporaryDirectory
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib,Gdk
m=SourceFileLoader('timer',str(Path(__file__).with_name('simpletimer'))).load_module()
present=Gtk.ApplicationWindow.present
errors=[]
def patched(win):
    present(win);app=win.get_application()
    def check():
        try:
            app.select('countdown');app.entry.set_text('2');app.apply()
            assert model.value('countdown')==120
            app.action();assert model.state('countdown')['since'] is not None
            app.action();assert model.state('countdown')['since'] is None
            app.key(None,Gdk.KEY_4,0,0);assert app.mode=='fasting'
            app.entry.set_text('2');app.apply();assert 7198<model.value('fasting')<7202
            app.action();assert model.fast_start() is None
            app.key(None,Gdk.KEY_Escape,0,0);assert not win.get_visible()
            print('PASS: GTK modes, duration entry, start/pause, fasting, Escape hides',flush=True)
        except BaseException as exc:errors.append(exc)
        finally:app.quit()
        return False
    GLib.timeout_add(3500,check)
Gtk.ApplicationWindow.present=patched
with TemporaryDirectory() as tmp:
    root=Path(tmp);model=m.Timers(m.DEFAULTS|dict(notify=False),root/'state',root/'fast/start')
    m.gui(model,'countdown')
if errors:raise errors[0]

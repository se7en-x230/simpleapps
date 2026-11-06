"""Run in an isolated graphical session; only generated test images are trashed."""
from pathlib import Path
from tempfile import TemporaryDirectory
from importlib.machinery import SourceFileLoader
from unittest.mock import patch
import argparse,os
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib,Gdk
from PIL import Image
m=SourceFileLoader('viewer',str(Path(__file__).with_name('simpleimage'))).load_module()
errors=[];stage=0;ticks=0
present=Gtk.ApplicationWindow.present
with TemporaryDirectory(prefix="trash-test-",dir=Path(__file__).parent) as td:
    root=Path(td);os.environ['XDG_DATA_HOME']=str(root/'data');folder=root/'images';folder.mkdir()
    files=[folder/(n+'.png') for n in ('a','b','c')]
    for p in files:Image.new('RGB',(32,32),'orange').save(p)
    def patched(win):
        present(win);app=win.get_application();app.popup=lambda title,text:print(title,text,flush=True)
        def tick():
            global stage,ticks
            ticks+=1
            try:
                assert ticks<150,'Trash test timed out'
                if stage==0:
                    if app.pixbuf is None:return True
                    app.toggle_grid();app.selection.set_selected(1)
                    app.key(None,Gdk.KEY_x,0,Gdk.ModifierType.CONTROL_MASK)
                    assert getattr(app,'trash_dialog',None) is None and all(p.exists() for p in files)
                    app.key(None,Gdk.KEY_x,0,0);assert all(p.exists() for p in files);assert not app.trashing
                    app.trash_keys.emit('key-pressed',Gdk.KEY_Escape,0,0);assert app.trash_dialog is None
                    app.marked={files[0],files[1]};app.key(None,Gdk.KEY_x,0,0)
                    cancel=app.trash_dialog.get_focus()
                    app.trash_keys.emit('key-pressed',Gdk.KEY_Tab,0,0);assert app.trash_dialog.get_focus()!=cancel
                    app.trash_keys.emit('key-pressed',Gdk.KEY_ISO_Left_Tab,0,Gdk.ModifierType.SHIFT_MASK);assert app.trash_dialog.get_focus()==cancel
                    app.trash_keys.emit('key-pressed',Gdk.KEY_l,0,0)
                    app.trash_keys.emit('key-pressed',Gdk.KEY_Return,0,0);stage=1
                elif stage==1:
                    if app.trashing or app.pixbuf is None:return True
                    assert app.files==[files[2]] and not app.marked,(app.files,app.marked,[p.exists() for p in files],app.status.get_text())
                    assert not files[0].exists() and not files[1].exists() and files[2].exists()
                    assert len(list((root/'data/Trash/files').iterdir()))==2
                    app.trash();app.trash_keys.emit('key-pressed',Gdk.KEY_y,0,0);stage=2
                elif stage==2:
                    if app.trashing:return True
                    assert app.files==[] and app.pixbuf is None and app.picture.get_paintable() is None
                    assert app.store.get_n_items()==0 and not files[2].exists()
                    moved,failed=m.trash_paths([folder/'missing.png'])
                    assert not moved and len(failed)==1
                    print('PASS: Escape cancellation, Tab/Shift+Tab focus, l/Enter confirmation, y confirmation, marked batch, native Trash, grid refresh, last image, failure retention',flush=True)
                    app.close();app.quit();return False
            except BaseException as exc:
                errors.append(exc);app.close();app.quit();return False
            return True
        GLib.timeout_add(100,tick)
    with patch.object(Gtk.ApplicationWindow,'present',patched):
        m.gui(m.DEFAULTS,argparse.Namespace(paths=[files[0]]))
if errors:raise errors[0]

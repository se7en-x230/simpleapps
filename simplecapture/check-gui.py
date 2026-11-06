#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory
from importlib.machinery import SourceFileLoader
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
from PIL import Image
m=SourceFileLoader('capture',str(Path(__file__).with_name('simplecapture'))).load_module()
present=Gtk.ApplicationWindow.present

def patched(win):
 present(win);app=win.get_application()
 GLib.timeout_add(3500,lambda:app.choose('fullscreen',False))
Gtk.ApplicationWindow.present=patched
with TemporaryDirectory() as tmp:
 settings=m.DEFAULTS|dict(save_dir=Path(tmp),copy=False,save=True,notify=False)
 selected=m.menu(settings);assert selected['mode']=='fullscreen' and not selected['edit']
 path=m.capture(selected)
 with Image.open(path) as im:assert im.format=='PNG' and im.width>0 and im.height>0
 print('PASS: real capture menu, close-before-capture, grim desktop capture and saved PNG',flush=True)

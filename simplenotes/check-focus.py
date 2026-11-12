#!/usr/bin/env python3
"""Keyboard-focus regression using temporary notes only; no clipboard access."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from importlib.machinery import SourceFileLoader
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib,Gdk
m=SourceFileLoader('notes',str(Path(__file__).with_name('simplenotes'))).load_module()
with TemporaryDirectory() as tmp:
    root=Path(tmp);notes=root/'notes';notes.mkdir()
    (notes/'A.md').write_text('first');(notes/'B.md').write_text('second')
    os.environ['XDG_CONFIG_HOME']=str(root/'config');os.environ['XDG_STATE_HOME']=str(root/'state')
    cfg=root/'config/simplenotes';cfg.mkdir(parents=True)
    (cfg/'keys.ini').write_text('[interaction]\nstart_in_search=true\nescape_closes=false\n')
    state={'passed':False,'attempts':0};present=Gtk.ApplicationWindow.present
    def patched(win):
        present(win);app=win.get_application()
        def in_search():
            widget=win.get_focus()
            while widget:
                if widget is app.search:return True
                widget=widget.get_parent()
            return False
        def key(value):return app.key(None,value,0,Gdk.ModifierType(0))
        def check():
            state['attempts']+=1
            if app.path is None and state['attempts']<100:return True
            try:
                assert app.editor_card.has_css_class('card')
                assert app.editor_card.has_css_class('preview-card')
                assert app.editor_scroll.get_parent()==app.editor_card
                assert app.path.name=='A.md'
                assert in_search(),'Search must have startup focus'
                def ctrl(k):return app.key(None,k,0,Gdk.ModifierType.CONTROL_MASK)
                assert ctrl(Gdk.KEY_j);assert app.path.name=='B.md';assert in_search()
                assert ctrl(Gdk.KEY_k);assert app.path.name=='A.md';assert in_search()
                assert not key(Gdk.KEY_q),'Typing q in search must not close'
                assert ctrl(Gdk.KEY_Return);assert not in_search()
                assert key(Gdk.KEY_j);assert app.path.name=='B.md'
                assert key(Gdk.KEY_slash);assert in_search()
                app.search.set_text('second');assert app.path.name=='B.md'
                assert key(Gdk.KEY_Return);assert app.mode=='edit'
                ctrl(Gdk.KEY_Return);assert app.mode=='list'
                assert key(Gdk.KEY_slash);assert in_search()
                assert key(Gdk.KEY_Escape)
                state['passed']=True
                print('PASS search startup, Ctrl+J/K retains search, navigation mode, Enter edit, editor return and Escape close')
            finally:
                app.quit()
            return False
        GLib.timeout_add(50,check)
    Gtk.ApplicationWindow.present=patched
    m.main(['--notes-dir',str(notes)])
    assert state['passed']

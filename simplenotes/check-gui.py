#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory
from importlib.machinery import SourceFileLoader
import gi,time
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib,Gdk
m=SourceFileLoader('notes',str(Path(__file__).with_name('simplenotes'))).load_module()
work=TemporaryDirectory();root=Path(work.name)
(root/'Ideas.md').write_text('# Ideas\n\nBuild small tools that work well together.\n')
(root/'Projects').mkdir();(root/'Projects/Weekend.md').write_text('# Weekend\n\n- Sort photographs\n- Back up music\n')
(root/'Read later.md').write_text('Searchable content: cobalt\n')
state={'stage':0,'passed':False};present=Gtk.ApplicationWindow.present

def patched(win):
 present(win);app=win.get_application()
 def key(k,ctrl=False,shift=False):
  flags=(Gdk.ModifierType.CONTROL_MASK if ctrl else Gdk.ModifierType(0)) | (Gdk.ModifierType.SHIFT_MASK if shift else Gdk.ModifierType(0))
  app.key(None,k,0,flags)
 def check():
  if app.path is None:return True
  try:
   stage=state['stage']
   if stage==0:
    widget=app.win.get_focus()
    while widget and widget is not app.search: widget=widget.get_parent()
    assert widget is app.search, 'Search must be focused on startup'
    app.key(None,Gdk.KEY_Return,0,Gdk.ModifierType.CONTROL_MASK)
    key(Gdk.KEY_slash)
    app.search.set_text('cobalt');assert app.path.name=='Read later.md'
    app.search.set_text('');app.search.emit('activate');app.move()
    assert app.path.name=='Ideas.md';key(Gdk.KEY_j);assert app.path.name=='Weekend.md'
    key(Gdk.KEY_g);key(Gdk.KEY_g);assert app.path.name=='Ideas.md'
    app.search.set_text('cobalt');assert len(app.visible)==1 and app.path.name=='Read later.md'
    app.search.set_text('');app.move();key(Gdk.KEY_i);assert app.mode=='edit' and app.editor.get_editable()
    app.buffer.insert(app.buffer.get_end_iter(),'Autosaved line\n');state['stage']=1;return True
   if stage==1:
    assert 'Autosaved line' in (root/'Ideas.md').read_text();assert not app.dirty
    key(Gdk.KEY_Return,ctrl=True);assert app.mode=='list'
    # Clipboard capture and append use GTK's asynchronous clipboard.
    Gdk.Display.get_default().get_clipboard().set('Clipboard addition')
    app.append_clipboard();state['stage']=2;return True
   if stage==2:
    assert (root/'Ideas.md').read_text().endswith('Clipboard addition')
    app.buffer.insert(app.buffer.get_end_iter(),' pending edits')
    (root/'Ideas.md').write_text('External revision')
    assert not app.save();assert (root/'Ideas.md').read_text()=='External revision'
    assert app.draft_path().exists();assert app.close() is True
    # Saving a copy must retain both external revision and current edits.
    captured={}
    def ask(title,callback,initial=''):captured['callback']=callback
    app.ask_name=ask
    key(Gdk.KEY_S,ctrl=True,shift=True)
    captured['callback']('Recovered.md');state['stage']=3;return True
   if stage==3:
    assert app.path.name=='Recovered.md' and 'pending edits' in app.text()
    assert (root/'Ideas.md').read_text()=='External revision'
    assert app.mode=='edit';key(Gdk.KEY_Return,ctrl=True)
    key(Gdk.KEY_l);key(Gdk.KEY_Down);key(Gdk.KEY_g);key(Gdk.KEY_g);key(Gdk.KEY_h)
    assert app.mode=='list'
    app.copy();assert not app.dirty
    key(Gdk.KEY_Escape);state['passed']=True
    print('PASS: note navigation, content search, editing, autosave, clipboard append, conflict preservation, save-copy recovery, preview keys',flush=True)
    return False
  except Exception:
   import traceback;traceback.print_exc();app.quit();return False
  return True
 GLib.timeout_add(3000,check)
Gtk.ApplicationWindow.present=patched
m.main(['--notes-dir',str(root)])
assert state['passed']

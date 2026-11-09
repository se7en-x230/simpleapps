"""Chooser keyboard regression: focused buttons, typing, prefixes, multi/save modes.
Run with a graphical display. Uses only temporary files, never opens a real file.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from importlib.machinery import SourceFileLoader
import sys
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,GLib
m=SourceFileLoader('files',str(Path(__file__).with_name('simplefiles'))).load_module()
mode=sys.argv[1];tmp=TemporaryDirectory();root=Path(tmp.name)
(root/'a.txt').write_text('test');(root/'b.txt').write_text('test');out=root/'result'
args=[str(root),'--output',str(out)]
if mode=='save':args+=['--save']
if mode=='multiple':args+=['--multiple']
errors=[];done=[];present=Gtk.ApplicationWindow.present

def descendants(w):
 c=w.get_first_child()
 while c:
  yield c;yield from descendants(c);c=c.get_next_sibling()
def patched(win):
 present(win);app=win.get_application();ticks=0
 def check():
  nonlocal ticks
  ticks+=1
  if not app.items and ticks<50:return True
  try:
   def key(k,ctrl=False):return app.key(None,k,0,Gdk.ModifierType.CONTROL_MASK if ctrl else 0)
   buttons=[w for w in descendants(win) if isinstance(w,Gtk.Button)]
   cancel=next(w for w in buttons if w.get_label() and w.get_label().startswith('Cancel'))
   confirm=next(w for w in buttons if w.get_label() and '[Ctrl+Enter]' in w.get_label())
   # Verify Tab is not consumed even halfway through a Vim command.
   app.prefix='g';assert key(Gdk.KEY_Tab) is False;assert app.prefix==''
   # Real GTK focus traversal must reach both header controls.
   reached=set()
   for _ in range(50):
    win.child_focus(Gtk.DirectionType.TAB_FORWARD)
    focus=win.get_focus()
    if focus in (cancel,confirm):reached.add(focus)
   assert len(reached)==2,'Header buttons unreachable with Tab'
   app.selection.set_selected(app.visible.index(root/'a.txt'))
   if mode=='cancel':
    cancel.grab_focus();assert key(Gdk.KEY_Return) is True;expected=''
   elif mode=='escape':
    app.search.grab_focus();app.search.set_text('a');assert key(Gdk.KEY_Escape);expected=''
   elif mode=='confirm':
    confirm.grab_focus();assert key(Gdk.KEY_Return);expected=str(root/'a.txt')+'\n'
   elif mode=='typing':
    app.search.grab_focus();app.search.set_text('a.txt');assert key(Gdk.KEY_Return,True);expected=str(root/'a.txt')+'\n'
   elif mode=='multiple':
    app.marked={root/'a.txt':None,root/'b.txt':None};confirm.grab_focus();assert key(Gdk.KEY_Return)
    expected=str(root/'a.txt')+'\n'+str(root/'b.txt')+'\n'
   elif mode=='save':
    app.name.set_text('new.txt');app.name.grab_focus();assert key(Gdk.KEY_Return,True);expected=str(root/'new.txt')+'\n'
   else:raise ValueError(mode)
   # Gtk.Button.activate schedules its clicked signal after the key animation.
   def finish():
    try:assert out.read_text()==expected,(mode,out.read_text(),expected);done.append(True);print('PASS',mode,flush=True)
    except BaseException as e:errors.append(e)
    app.quit();return False
   app.hold();GLib.timeout_add(400,finish)
  except BaseException as e:errors.append(e);app.quit()
  return False
 GLib.timeout_add(100,check)
Gtk.ApplicationWindow.present=patched
m.main(args)
if errors:raise errors[0]
assert done,'Test did not complete'

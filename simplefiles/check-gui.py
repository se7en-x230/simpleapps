from pathlib import Path
from importlib.machinery import SourceFileLoader
import sys,gi,time
from tempfile import TemporaryDirectory
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib,Gdk
m=SourceFileLoader('files',str(Path(__file__).with_name('simplefiles'))).load_module()
mode=sys.argv[1];present=Gtk.ApplicationWindow.present
work=TemporaryDirectory();root=Path(work.name)
(root/'folder').mkdir();(root/'a.txt').write_text('Preview text\n');(root/'b.txt').write_text('Second file\n');(root/'.hidden').write_text('Hidden')
(root/'folder'/'nested.txt').write_text('Nested')
(root/'folder'/'.secret').write_text('Hidden')
if mode=='large':
 for i in range(10000):(root/f'item-{i:05}.txt').touch()
output=root/'result';state={'done':False};stage=0;started=time.monotonic()
arguments=[str(root),'--output',str(output)]
if mode in ('multiple','directory','save'):arguments+=['--'+mode]
if mode=='save':arguments[0]=str(root/'existing.txt');(root/'existing.txt').write_text('KEEP')
def patched(win):
 present(win);app=win.get_application()
 def key(k,ctrl=False):app.key(None,k,0,Gdk.ModifierType.CONTROL_MASK if ctrl else Gdk.ModifierType(0))
 def check():
  global stage
  if not app.items:return True
  try:
   if mode=='preview':
    if stage==0:
     assert app.folder_scroll.get_visible()
     assert app.folder_model.get_n_items()==1
     assert app.folder_model.get_string(0)=='nested.txt'
     key(Gdk.KEY_k);assert app.hovered()==app.visible[-1]
     key(Gdk.KEY_j);assert app.hovered()==root/'folder'
     key(Gdk.KEY_period);stage=1;return True
    if stage==1:
     assert app.folder_model.get_n_items()==2
     app.move(1);stage=2;return True
    assert not app.folder_scroll.get_visible()
    app.win.close();expected=[]
   elif mode=='open':
    if stage==0:
     assert app.hovered()==root/'folder';key(Gdk.KEY_l);stage=1;return True
    if app.cwd!=root/'folder':return True
    key(Gdk.KEY_Return);expected=[root/'folder'/'nested.txt']
   elif mode=='multiple':
    app.search.set_text('.txt');app.list.grab_focus();key(Gdk.KEY_space);key(Gdk.KEY_space);key(Gdk.KEY_Return)
    expected=[root/'a.txt',root/'b.txt']
   elif mode=='directory':key(Gdk.KEY_Return);expected=[root/'folder']
   elif mode=='save':
    if stage==0:
     app.name.set_text('existing.txt');app.confirm();stage=1;return True
    dialogs=[w for w in Gtk.Window.list_toplevels() if isinstance(w,Gtk.MessageDialog)]
    assert dialogs;dialogs[0].response(Gtk.ResponseType.NO)
    assert output.read_text()=='' and (root/'existing.txt').read_text()=='KEEP'
    app.name.set_text('new.txt');app.confirm();expected=[root/'new.txt'];assert not (root/'new.txt').exists()
   elif mode=='large':
    assert len(app.visible)==10004
    key(Gdk.KEY_G);assert app.hovered().name=='result'
    key(Gdk.KEY_g);key(Gdk.KEY_g);assert app.hovered()==root/'folder'
    app.search.set_text('item-09999');assert len(app.visible)==1
    app.list.grab_focus();key(Gdk.KEY_Return);expected=[root/'item-09999.txt']
   else:
    app.list.grab_focus();key(Gdk.KEY_q);expected=[]
   assert output.read_text()==''.join(str(p)+'\n' for p in expected),(mode,output.read_text(),expected)
   state['done']=True;print('PASS',mode,'elapsed',round(time.monotonic()-started,2),flush=True)
  except Exception:
   import traceback;traceback.print_exc();app.quit()
  return False
 GLib.timeout_add(3000,check)
Gtk.ApplicationWindow.present=patched
m.main(arguments)
assert state['done']

import os,sys,tempfile
from pathlib import Path
from importlib.machinery import SourceFileLoader
import cairo,gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib,Gdk
base=Path(__file__).parent
m=SourceFileLoader('pdf',str(base/'simplepdf')).load_module()
present=Gtk.ApplicationWindow.present
errors=[]
def patched(win):
    present(win);app=win.get_application()
    def first():
        try:
            assert app.doc.get_n_pages()==3
            assert app.area.get_content_width()>100
            app.goto(1);app.rotation=90;app.layout();app.save()
            app.open_file(app.path);assert app.page==1 and app.rotation==90
            app.rotation=0;app.layout();app.search('needle')
            app.record.setdefault('bookmarks',{})['Test']=2;app.save()
            app.outline()
            for w in app.get_windows():
                if w!=win:w.destroy()
            GLib.timeout_add(400,second)
        except BaseException as e:errors.append(e);app.quit()
        return False
    def second():
        try:
            assert len(app.hits)==3,len(app.hits)
            app.next_hit(1);assert app.page==1
            app.key(None,Gdk.KEY_G,0,0);assert app.page==2
            app.set_fit('width');app.layout()
            print('PASS: render, page navigation, saved position/rotation/bookmarks, search highlights, empty outline, fit width',flush=True)
        except BaseException as e:errors.append(e)
        finally:app.quit()
        return False
    GLib.timeout_add(3500,first)
Gtk.ApplicationWindow.present=patched
with tempfile.TemporaryDirectory() as td:
    path=Path(td)/'sample.pdf';surface=cairo.PDFSurface(str(path),595,842);ctx=cairo.Context(surface)
    for i in range(3):
        ctx.set_source_rgb(.15,.15,.15);ctx.select_font_face('Sans');ctx.set_font_size(32);ctx.move_to(60,100);ctx.show_text('Simplepdf '+str(i+1));ctx.set_font_size(18);ctx.move_to(60,150);ctx.show_text('A needle in this document.');ctx.show_page()
    surface.finish();sys.argv=['simplepdf',str(path)];m.main()
if errors:raise errors[0]

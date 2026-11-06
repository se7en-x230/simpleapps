from importlib.machinery import SourceFileLoader
from pathlib import Path
from tempfile import TemporaryDirectory
import argparse,sys
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib,Gdk
from PIL import Image
m=SourceFileLoader('viewer',str(Path(__file__).with_name('simpleimage'))).load_module()
present=Gtk.ApplicationWindow.present;errors=[]
def patched(win):
    present(win);app=win.get_application()
    def first():
        try:
            assert len(app.files)==3 and app.pixbuf
            assert app.pixbuf.get_width()==640,'Small image unexpectedly enlarged at decode'
            app.key(None,Gdk.KEY_R,0,0);assert app.displayed.get_width()==360
            app.key(None,Gdk.KEY_x,0,0);assert app.mirror
            app.key(None,Gdk.KEY_m,0,0);assert len(app.marked)==1
            app.key(None,Gdk.KEY_Return,0,0);assert app.show_grid
            assert app.thumbnail_size()==(174,120)
            app.key(None,Gdk.KEY_z,0,0);assert app.thumbnail_size()==(300,208)
            assert app.selection.get_selected()==0
            app.key(None,Gdk.KEY_z,0,0);assert app.thumbnail_size()==(174,120)
            app.key(None,Gdk.KEY_l,0,0);assert app.selection.get_selected()==1
            app.key(None,Gdk.KEY_Return,0,0)
            GLib.timeout_add(500,second)
        except BaseException as e:errors.append(e);app.close();app.quit()
        return False
    def second():
        try:
            assert app.index==1 and app.pixbuf.get_width()==120
            app.key(None,Gdk.KEY_1,0,0);assert not app.fit and app.zoom==1
            app.key(None,Gdk.KEY_equal,0,0);assert app.fit
            app.show(2);app.show(0) # Obsolete asynchronous load must not replace this image.
            GLib.timeout_add(500,third)
        except BaseException as e:errors.append(e);app.close();app.quit()
        return False
    def third():
        try:
            assert app.index==0 and app.pixbuf.get_width()==640
            app.slideshow();assert app.slide;app.slideshow();assert not app.slide
            output=app.current().parent/'print.pdf'
            result=app.print_images(output)
            assert result==Gtk.PrintOperationResult.APPLY and output.read_bytes().startswith(b'%PDF-')
            print('PASS: async loading, EXIF orientation, rotation/mirror, marks, thumbnail navigation, zoom, stale-load protection, slideshow',flush=True)
        except BaseException as e:errors.append(e)
        finally:app.close();app.quit()
        return False
    GLib.timeout_add(3500,first)
Gtk.ApplicationWindow.present=patched
with TemporaryDirectory() as td:
    root=Path(td)
    Image.new('RGB',(640,360),'#648898').save(root/'image1.jpg')
    im=Image.new('RGB',(240,120),'#b48a50');exif=im.getexif();exif[274]=6;im.save(root/'image2.jpg',exif=exif)
    Image.new('RGB',(800,500),'#668855').save(root/'image10.png')
    m.gui(m.DEFAULTS,argparse.Namespace(paths=[root/'image1.jpg']))
if errors:raise errors[0]

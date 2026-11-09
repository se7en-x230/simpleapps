from pathlib import Path
from importlib.machinery import SourceFileLoader
import gi
import warnings
gi.require_version('Gdk','4.0');gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf,GLib,Gio
m=SourceFileLoader('viewer',str(Path(__file__).with_name('simpleimage'))).load_module()
with warnings.catch_warnings():
 warnings.simplefilter('error',DeprecationWarning)
 for alpha in (False,True):
  channels=4 if alpha else 3;stride=12
  data=bytes([33,77,155,128][:channels]*3)+bytes(stride-channels*3)+bytes([88,99,111,255][:channels]*3)
  pix=GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(data),GdkPixbuf.Colorspace.RGB,alpha,8,3,2,stride)
  texture=m.texture_for_pixbuf(pix)
  decoded=GdkPixbuf.Pixbuf.new_from_stream(Gio.MemoryInputStream.new_from_bytes(texture.save_to_png_bytes()),None)
  assert decoded.get_width()==3 and decoded.get_height()==2
  actual=decoded.read_pixel_bytes().get_data();step=decoded.get_n_channels()
  assert actual[:3]==bytes([33,77,155])
  if alpha:assert actual[3]==128
  row=decoded.get_rowstride();assert actual[row:row+3]==bytes([88,99,111])
print('PASS: RGB/RGBA, transparent pixels and last-row padding without deprecated texture calls')

from pathlib import Path
from importlib.machinery import SourceFileLoader
from PIL import Image
import numpy as np,tempfile
m=SourceFileLoader('photo',str(Path(__file__).with_name('simplephoto'))).load_module()
mask=Image.new('L',(200,160),255)
m.paint_mask(mask,(50,80),(150,80),18)
a=np.asarray(mask);assert a[80,100]==0 and a[0,0]==255
assert ((a>0)&(a<255)).any()
m.paint_mask(mask,(100,80),(100,80),10,erase=True)
a=np.asarray(mask);assert a[80,100]>250 and a[80,60]<5
pixels=np.random.default_rng(4).integers(0,256,(160,200,3),dtype=np.uint8);im=Image.fromarray(pixels)
out=m.portrait_blur(im,mask,70);assert np.array_equal(np.asarray(out)[0,0],pixels[0,0]);assert not np.array_equal(np.asarray(out)[80,60],pixels[80,60])
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'brush.png';im.save(p);data=m.read(p);original=p.read_bytes();rect=(25,20,150,110)
 target=m.save(p,data,{'Portrait blur':70},rect,mask)
 expected=m.portrait_blur(im.crop((25,20,175,130)),mask.crop((25,20,175,130)),70)
 assert np.array_equal(np.asarray(Image.open(target)),np.asarray(expected))
 assert p.read_bytes()==original
print('PASS: feathered paint, erase, protected pixels, changed selected pixels, cropped export and untouched original')

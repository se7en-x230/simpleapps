from pathlib import Path
from importlib.machinery import SourceFileLoader
import tempfile,numpy as np
from PIL import Image
m=SourceFileLoader('enhance',str(Path(__file__).with_name('simplephoto'))).load_module()
a=np.random.default_rng(7).integers(0,256,(40,60,4),dtype=np.uint8);im=Image.fromarray(a)
assert np.array_equal(np.asarray(m.enhance(im,{})),a)
for control in m.CONTROLS:
 for value in (-100,100):
  out=np.asarray(m.enhance(im,{control:value}))
  assert np.array_equal(out[:,:,3],a[:,:,3])
  assert not np.array_equal(out[:,:,:3],a[:,:,:3]),control
neutral=Image.new('RGB',(5,5),(100,100,100))
assert np.asarray(m.enhance(neutral,{'Brightness':50}))[0,0,0]>100
assert np.asarray(m.enhance(neutral,{'Brightness':-50}))[0,0,0]<100
warm=np.asarray(m.enhance(neutral,{'Warmth':100}))[0,0];assert warm[0]>warm[2]
tint=np.asarray(m.enhance(neutral,{'Tint':100}))[0,0];assert tint[0]>tint[1]
gray=np.asarray(m.enhance(im,{'Saturation':-100}));assert np.array_equal(gray[:,:,0],gray[:,:,1])
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'photo.png';im.save(p);original=p.read_bytes();data=m.read(p)
 settings={'Contrast':20,'Shadows':30,'Saturation':15}
 target=m.save(p,data,settings);assert target.name=='photo~2.png'
 assert np.array_equal(np.asarray(Image.open(target)),np.asarray(m.enhance(data[0],settings)))
 assert m.save(p,data,{}).name=='photo~3.png';assert p.read_bytes()==original
 p.write_bytes(b'changed')
 try:m.save(p,data,{})
 except ValueError:pass
 else:raise AssertionError('changed source accepted')
print('PASS: neutral baseline, all eight controls, alpha preservation, colour directions, exact saved pixels, numbering and source protection')

from pathlib import Path
from importlib.machinery import SourceFileLoader
from PIL import Image
import numpy as np,tempfile
m=SourceFileLoader('photo',str(Path(__file__).with_name('simplephoto'))).load_module()
with tempfile.TemporaryDirectory() as td:
 p=Path(td)/'photo.png';a=np.random.default_rng(1).integers(0,256,(50,80,3),dtype=np.uint8);Image.fromarray(a).save(p)
 data=m.read(p);rect=(10,5,40,30);mask=Image.new('L',(80,50),255);m.paint_mask(mask,(20,20),(30,25),5)
 result=m.rotate_data(data,rect,mask,[mask],True);rotated,box,rotmask,history=result
 assert box==(15,10,30,40)
 assert np.array_equal(np.asarray(rotated[0]),np.rot90(a,-1))
 reverted=m.rotate_data(*result,False)
 assert np.array_equal(np.asarray(reverted[0][0]),a) and reverted[1]==rect
 assert np.array_equal(np.asarray(reverted[2]),np.asarray(mask))
 target=m.save(p,rotated,{},box,rotmask)
 assert np.array_equal(np.asarray(Image.open(target)),np.rot90(a[5:35,10:50],-1))
 assert np.array_equal(np.asarray(Image.open(p)),a)
print('PASS: both rotations, crop geometry, mask/history alignment, export and untouched original')

for horizontal,operation in ((True,Image.Transpose.FLIP_LEFT_RIGHT),(False,Image.Transpose.FLIP_TOP_BOTTOM)):
 mirrored=m.mirror_data(data,rect,mask,[mask],horizontal)
 expected=data[0].crop((10,5,50,35)).transpose(operation)
 x,y,w,h=mirrored[1]
 assert np.array_equal(np.asarray(mirrored[0][0].crop((x,y,x+w,y+h))),np.asarray(expected))
 restored=m.mirror_data(*mirrored,horizontal)
 assert np.array_equal(np.asarray(restored[0][0]),np.asarray(data[0]))
 assert np.array_equal(np.asarray(restored[2]),np.asarray(mask))
print('PASS: both mirror directions, crop alignment and mask roundtrip')

import hashlib,io,json,sys,tarfile,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import wallpaper_pack as pack
class Tests(unittest.TestCase):
 def fixture(self,root,entry='wallpaper-packs/theme/day.png',kind=None):
  here=root/'simpleinstaller';here.mkdir(exist_ok=True)
  archive=root/pack.FILENAME
  with tarfile.open(archive,'w:gz') as t:
   m=tarfile.TarInfo(entry);m.size=3
   if kind:m.type=kind;m.linkname='/tmp/outside';m.size=0
   t.addfile(m,io.BytesIO(b'png') if not kind else None)
  (here/pack.METADATA).write_text(json.dumps({'sha256':pack.digest(archive)}))
  return here,archive
 def test_lazy_without_archive(self):
  with tempfile.TemporaryDirectory() as td:
   for names,options in [(['simpleplayer'],set()),(['simplewallpaper'],set())]:
    with pack.prepare(Path(td),names,options,'/missing') as result:self.assertIsNone(result)
 def test_selected_extracts_and_cleans_up(self):
  with tempfile.TemporaryDirectory() as td:
   here,archive=self.fixture(Path(td))
   with pack.prepare(here,['simplewallpaper'],{'daylight'}) as result:
    self.assertEqual((result/'theme/day.png').read_bytes(),b'png')
   self.assertFalse(result.exists())
 def test_missing_and_corrupt(self):
  with tempfile.TemporaryDirectory() as td:
   here,archive=self.fixture(Path(td));archive.write_bytes(b'broken')
   with self.assertRaisesRegex(ValueError,'verification failed'):
    with pack.prepare(here,['simplewallpaper'],{'daylight'}):pass
   archive.unlink()
   with self.assertRaisesRegex(ValueError,'Copy it beside'):
    with pack.prepare(here,['simplewallpaper'],{'daylight'}):pass
 def test_unsafe_archives(self):
  for entry,kind in [('wallpaper-packs/../../escape',None),('wallpaper-packs/link',tarfile.SYMTYPE)]:
   with tempfile.TemporaryDirectory() as td:
    here,archive=self.fixture(Path(td),entry,kind)
    with self.assertRaisesRegex(ValueError,'Invalid wallpaper archive'):
     with pack.prepare(here,['simplewallpaper'],{'daylight'}):pass
 def test_override(self):
  with tempfile.TemporaryDirectory() as td:
   here,archive=self.fixture(Path(td));other=archive.with_name('other.tar.gz');archive.rename(other)
   with pack.prepare(here,['simplewallpaper'],{'daylight'},str(other)) as result:self.assertTrue(result.is_dir())
if __name__=='__main__':unittest.main()

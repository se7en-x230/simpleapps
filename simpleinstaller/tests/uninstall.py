import importlib.machinery,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
loader=importlib.machinery.SourceFileLoader('installer',str(BASE/'simpleinstaller'));spec=importlib.util.spec_from_loader('installer',loader);installer=importlib.util.module_from_spec(spec);loader.exec_module(installer)
u=installer.uninstall
class Tests(unittest.TestCase):
 def fixture(self,root):
  dirs={'home':root,'bin':root/'bin','data':root/'data','config':root/'config','src':root/'src','state':root/'state'}
  stage=root/'stage';stage.mkdir();files={};owners={}
  for name,apps in [('player',{'simpleplayer'}),('picker',{'simplepicker'}),('shared',{'simpleplayer','simplepicker'})]:
   source=stage/name;source.write_text(name);files[dirs['bin']/name]=(source,False);owners[source]=apps
  config=dirs['config']/'settings';files[config]=(stage/'player',True)
  u.registration(files,stage,['simpleplayer','simplepicker'],owners,dirs)
  installer.apply_files(files,dirs['state']/'simpleinstaller')
  return dirs
 def test_shared_and_personal_files_and_repeat(self):
  with tempfile.TemporaryDirectory() as td:
   dirs=self.fixture(Path(td));extra=dirs['data']/'personal';extra.parent.mkdir();extra.write_text('mine')
   before=u.registry_path(dirs).read_bytes();registry,selected,remove,keep=u.plan(dirs,['simpleplayer'])
   self.assertEqual(remove,[dirs['bin']/'player']);self.assertEqual(before,u.registry_path(dirs).read_bytes())
   backup=u.apply(dirs,['simpleplayer']);self.assertFalse((dirs['bin']/'player').exists());self.assertTrue((dirs['bin']/'shared').exists())
   self.assertTrue((dirs['config']/'settings').exists());self.assertTrue(extra.exists());self.assertTrue((backup/'receipt.json').is_file())
   self.assertIsNone(u.apply(dirs,['simpleplayer']))
   u.apply(dirs,['simplepicker']);self.assertFalse((dirs['bin']/'shared').exists());self.assertEqual(u.read(dirs)['apps'],[])
 def test_modified_preserved(self):
  with tempfile.TemporaryDirectory() as td:
   dirs=self.fixture(Path(td));p=dirs['bin']/'player';p.write_text('modified');u.apply(dirs,['simpleplayer']);self.assertEqual(p.read_text(),'modified')
 def test_rollback(self):
  with tempfile.TemporaryDirectory() as td:
   dirs=self.fixture(Path(td));original=u.registry_path(dirs).read_bytes();real=Path.unlink
   def fail(p,*args,**kwargs):
    if p==dirs['bin']/'shared':raise OSError('simulated failure')
    return real(p,*args,**kwargs)
   with patch.object(Path,'unlink',fail),self.assertRaises(OSError):u.apply(dirs,['simpleplayer','simplepicker'])
   self.assertEqual(original,u.registry_path(dirs).read_bytes())
   for p in ['player','picker','shared']:self.assertEqual((dirs['bin']/p).read_text(),p)
 def test_symlink_refused(self):
  with tempfile.TemporaryDirectory() as td:
   dirs=self.fixture(Path(td));p=dirs['bin']/'player';p.unlink();outside=Path(td)/'outside';outside.write_text('mine');p.symlink_to(outside)
   with self.assertRaises(ValueError):u.apply(dirs,['simpleplayer'])
   self.assertEqual(outside.read_text(),'mine')
 def test_shared_ownership_from_recipes(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);work=root/'work';work.mkdir();stage=root/'stage';stage.mkdir()
   owners=installer.stage_apps((BASE/'sources' if (BASE/'sources').is_dir() else BASE.parent),['simplewallpaper'],set(),stage,work)
   self.assertEqual(owners[stage/'.local/bin/simplewallpaper'],{'simplewallpaper'})
   self.assertEqual(owners[stage/'.local/bin/simple-open'],{'simplewallpaper'})
if __name__=='__main__':unittest.main()

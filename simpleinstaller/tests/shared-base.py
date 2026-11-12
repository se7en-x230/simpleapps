"""Two independent app installs share one native base; removal is reference counted."""
from pathlib import Path
import importlib.machinery, importlib.util, os, sys, tempfile, unittest
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
loader=importlib.machinery.SourceFileLoader('installer',str(BASE/'simpleinstaller'))
spec=importlib.util.spec_from_loader('installer',loader);installer=importlib.util.module_from_spec(spec);loader.exec_module(installer)
import recipes
SOURCE=BASE/'sources' if (BASE/'sources').is_dir() else BASE.parent

class SharedBase(unittest.TestCase):
 def test_independent_installs_reuse_and_last_removal(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);home=root/'home';home.mkdir()
   with patch.dict(os.environ,{'HOME':str(home),'XDG_CONFIG_HOME':str(home/'config'),'XDG_DATA_HOME':str(home/'data'),'XDG_STATE_HOME':str(home/'state')}):
    dirs=installer.directories();lib=home/'.local/lib/simple-common/libsimple-ui.so'
    for index,app in enumerate(['simplegarmin','simpletimer']):
     stage=root/('stage'+str(index));work=root/('work'+str(index));stage.mkdir();work.mkdir()
     real=recipes.subprocess.run
     def run(command,*args,**kwargs):
      if index and command[:2]==['make','-C']:raise AssertionError('Second Python app rebuilt the base')
      return real(command,*args,**kwargs)
     with patch.object(recipes.subprocess,'run',side_effect=run):
      owners=installer.stage_apps(SOURCE,[app],set(),stage,work)
     files=installer.payload(stage,dirs,[app],set(),'~/Music')
     installer.uninstall.registration(files,stage,[app],owners,dirs)
     installer.apply_files(files,dirs['state']/'simpleinstaller')
     if index==0:first_mtime=lib.stat().st_mtime_ns
     else:self.assertEqual(lib.stat().st_mtime_ns,first_mtime)
    registry=installer.uninstall.read(dirs)
    self.assertEqual(set(registry['files'][str(lib)]['owners']),{'simplegarmin','simpletimer'})
    self.assertEqual(list((home/'.local/lib').rglob('libsimple-ui.so')),[lib])
    installer.uninstall.apply(dirs,['simplegarmin'])
    self.assertTrue(lib.exists());self.assertTrue((dirs['bin']/'simpletimer').exists())
    installer.uninstall.apply(dirs,['simpletimer'])
    self.assertFalse(lib.exists());self.assertFalse((home/'.local/include/simple-ui.h').exists())
    self.assertTrue((dirs['config']/'simple/theme.css').exists())

if __name__=='__main__':unittest.main()

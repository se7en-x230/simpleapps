#!/usr/bin/env python3
import importlib.machinery,importlib.util,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1]
SOURCES=BASE/'sources' if (BASE/'sources').is_dir() else BASE.parent
import sys
sys.path.insert(0,str(BASE))
def module(name,path):
 loader=importlib.machinery.SourceFileLoader(name,str(path));spec=importlib.util.spec_from_loader(name,loader)
 result=importlib.util.module_from_spec(spec);loader.exec_module(result);return result
installer=module('installer',BASE/'simpleinstaller')
resolver=module('resolver',BASE/'runtime/simple-open.py')
player=module('playerconfig',SOURCES/'simpleplayer/scripts/simpleplayer-config.py')
class Tests(unittest.TestCase):
 def test_bundle_includes_license_grant(self):
  import tarfile
  with tempfile.TemporaryDirectory() as td:
   target=Path(td)/'timer.tar.gz'
   installer.bundle(SOURCES,target,'simpletimer')
   with tarfile.open(target) as archive:
    for prefix in ('simpletimer-installer/', 'simpletimer-installer/sources/'):
     self.assertIn(b'GNU GENERAL PUBLIC LICENSE',archive.extractfile(prefix+'LICENSE').read())
     self.assertIn(b'GPL-3.0-or-later',archive.extractfile(prefix+'COPYING').read())
    self.assertIn(b'GPL-3.0-or-later',archive.extractfile('simpletimer-installer/README.md').read())
 def test_framework_staging_and_portable_dependencies(self):
  result=subprocess.run([str(BASE/'simpleinstaller'),'--dependencies','simplegarmin'],text=True,capture_output=True)
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertIn('gtk4 >= 4.12',result.stdout)
  with tempfile.TemporaryDirectory() as td:
   stage=Path(td)/'stage';work=Path(td)/'work';stage.mkdir();work.mkdir()
   owners=installer.stage_apps(SOURCES,['simplegarmin'],set(),stage,work)
   library=stage/'.local/lib/simple-common/libsimple-ui.so'
   self.assertTrue(library.is_file())
   self.assertEqual(owners[library],{'simplegarmin'})
   self.assertTrue((stage/'.local/share/simple-common/simple_ui.py').is_file())
   dirs=installer.directories(Path(td)/'home')
   self.assertEqual(installer.destination(Path('.local/include/simple-ui.h'),dirs),Path(td)/'home/.local/include/simple-ui.h')

 def test_existing_picker_alias_is_preserved(self):
  with tempfile.TemporaryDirectory() as td:
   home=Path(td);dirs=installer.directories(home)
   dirs['bin'].mkdir(parents=True)
   (dirs['bin']/'simplepicker-native').write_text('native')
   (dirs['bin']/'simplepicker').symlink_to('simplepicker-native')
   stage=home/'stage';(stage/'.local/bin').mkdir(parents=True)
   (stage/'.local/bin/simplepicker').write_text('launcher')
   (stage/'.local/bin/simplepicker-native').write_text('new native')
   files=installer.payload(stage,dirs,['simplepicker'],set(),'~/Music')
   self.assertNotIn(dirs['bin']/'simplepicker',files)
   self.assertIn(dirs['bin']/'simplepicker-native',files)

 def test_dependency_choices(self):
  plain=installer.packages(['simpleplayer'],set());visual=installer.packages(['simpleplayer'],{'visualizer'})
  self.assertIn('mpv',plain);self.assertNotIn('cava',plain);self.assertIn('cava',visual)
  self.assertNotIn('gtk4-layer-shell',plain)
  self.assertNotIn('mpv',installer.packages(['simplepicker'],set()))
 def test_no_shell_evaluation(self):
  value='https://example.com/$(touch /tmp/not-executed);test'
  self.assertEqual(resolver.command('browser',[value],{'browser':['firefox']}),['firefox',value])
  with patch.object(resolver.shutil,'which',side_effect=lambda c:c=='konsole'),patch.dict(os.environ,{'XDG_CURRENT_DESKTOP':'KDE'}):
   self.assertEqual(resolver.command('terminal',['echo','a b'],{}),['konsole','-e','echo','a b'])
 def test_xdg_and_config_precedence(self):
  with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'HOME':td,'XDG_CONFIG_HOME':td+'/cfg','XDG_DATA_HOME':td+'/data','XDG_STATE_HOME':td+'/state'},clear=True):
   dirs=installer.directories();self.assertEqual(dirs['config'],Path(td)/'cfg')
   legacy=dirs['config']/'simplepicker/music/config.toml';legacy.parent.mkdir(parents=True);legacy.write_text('music_dir="/legacy"')
   self.assertEqual(player.music_directory(),'/legacy')
   own=dirs['config']/'simpleplayer/config.toml';own.parent.mkdir();own.write_text('music_dir="relative"\nvisualizer=false')
   self.assertEqual(player.music_directory(),str(own.parent/'relative'))
   self.assertFalse(player.configuration()[1]['visualizer'])
   with patch.dict(os.environ,{'SIMPLEPLAYER_CONFIG':str(legacy),'SIMPLEPLAYER_MUSIC_DIR':'/override'}):self.assertEqual(player.music_directory(),'/override')
   own.write_text('visualizer="false"')
   with self.assertRaises(ValueError):player.configuration()
 def test_preserve_and_idempotence(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);src=root/'source';src.write_text('new');dst=root/'existing';dst.write_text('old');state=root/'state'
   self.assertIsNone(installer.apply_files({dst:(src,True)},state));self.assertEqual(dst.read_text(),'old')
   receipt=installer.apply_files({dst:(src,False)},state);self.assertEqual(dst.read_text(),'new')
   data=json.loads(receipt.read_text());self.assertEqual(Path(data['files'][0]['backup']).read_text(),'old')
   self.assertIsNone(installer.apply_files({dst:(src,False)},state))
 def test_file_failure_rolls_back(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);src=root/'src';src.write_text('new');a=root/'a';a.write_text('old');b=root/'b';real_replace=os.replace
   def replace(src,dst):
    if dst==b:raise OSError('simulated full disk')
    return real_replace(src,dst)
   with patch.object(installer.os,'replace',side_effect=replace),self.assertRaises(OSError):installer.apply_files({a:(src,False),b:(src,False)},root/'state')
   self.assertEqual(a.read_text(),'old');self.assertFalse(b.exists())
 def test_symlink_does_not_write_outside(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);target=root/'target';target.write_text('outside');link=root/'link';link.symlink_to(target);src=root/'src';src.write_text('new')
   with self.assertRaises(ValueError):installer.apply_files({link:(src,False)},root/'state')
   self.assertEqual(target.read_text(),'outside')
 def test_plan_does_not_write_home(self):
  with tempfile.TemporaryDirectory() as td:
   result=subprocess.run([str(BASE/'simpleinstaller'),'--source-root',str(SOURCES),'--plan','simpleplayer'],env=dict(os.environ,HOME=td),capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(list(Path(td).iterdir()),[])
 def test_refresh_without_notification_service(self):
  with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'HOME':td,'XDG_CONFIG_HOME':td+'/cfg','XDG_CACHE_HOME':td+'/cache'},clear=False):
   root=Path(td);(root/'Music').mkdir();(root/'Music/Artist').mkdir();fake=root/'bin';fake.mkdir()
   notify=fake/'notify-send';notify.write_text('#!/bin/sh\nexit 1\n');notify.chmod(0o755)
   env=dict(os.environ,PATH=str(fake)+':'+os.environ['PATH'])
   result=subprocess.run(['bash',str(SOURCES/'simpleplayer/playback.sh'),'--refresh-library'],env=env,capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertEqual((root/'cache/simpleplayer/folders.index').read_text(),'Artist\n')
 def test_payload_respects_xdg(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);stage=root/'stage';app=stage/'.local/share/applications/simpleplayer.desktop';app.parent.mkdir(parents=True);app.write_text('Exec=simpleplayer\n')
   dirs={'home':root,'bin':root/'bin with space','config':root/'cfg','data':root/'data','state':root/'state','src':root/'src'}
   files=installer.payload(stage,dirs,['simpleplayer'],set(),'~/Music')
   self.assertIn(dirs['data']/'applications/simpleplayer.desktop',files)
   self.assertIn('bin with space',app.read_text());self.assertIn('Exec="',app.read_text())
   self.assertEqual(files[dirs['config']/'simpleplayer/config.toml'][0].read_text().splitlines()[-1],'visualizer = false')
if __name__=='__main__':unittest.main()

import sys,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from wm_config import settings,bindings
from launchers import launch_rows

class Readers(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.cfg=self.root/'simplepicker/keyboard';self.cfg.mkdir(parents=True)
 def tearDown(self):self.tmp.cleanup()
 def configure(self,wm,filename='main.conf',extra=''):
  self.path=self.root/filename
  (self.cfg/'config.ini').write_text(f'[shortcuts]\nenvironment={wm}\nconfig={self.path}\n[keyboard]\nenabled=false\n'+extra)
  return settings(self.root)
 def test_mango_sources_variables_and_no_execution(self):
  opt=self.configure('mango')
  self.path.write_text('var=browser,firefox\nsource=other.conf\nbind=Super,w,spawn,$browser --private-window\n')
  (self.root/'other.conf').write_text('bind=Super+Ctrl,v,spawn_shell,printf "hello # there" # comment\n')
  with patch('subprocess.run',side_effect=AssertionError('must not run')):
   rows=list(bindings(opt))
  self.assertEqual(rows[1][0],'Super+w');self.assertEqual(rows[1][3],('dispatch','spawn,firefox --private-window'))
  self.assertEqual(rows[0][1],'printf "hello # there"')
 def test_hypr_source_description_unbind_and_submap(self):
  opt=self.configure('hyprland')
  self.path.write_text('$mainMod = SUPER\n$terminal = foot\nsource=parts/*.conf\nbind=$mainMod,A,exec,old\nunbind=$mainMod,A\nsubmap=resize\nbind=,R,exec,hidden\nsubmap=reset\nbindd=$mainMod CTRL,T,Terminal,exec,$terminal --title hello\nbind=$mainMod,W,exec,firefox\nbind=$mainMod,W,killactive,\n')
  (self.root/'parts').mkdir();(self.root/'parts/one.conf').write_text('bind = $mainMod, D, exec, fuzzel\n')
  rows=list(bindings(opt));self.assertEqual([r[0] for r in rows],['Super+D','Super+Ctrl+T'])
  self.assertEqual(rows[1][3],('wm',['hyprctl','dispatch','exec','foot --title hello']))
 def test_cycles_and_missing_sources(self):
  opt=self.configure('mango');self.path.write_text('source=main.conf\n')
  with self.assertRaises(ValueError):list(bindings(opt))
  self.path.write_text('source=missing.conf\n')
  with self.assertRaises(FileNotFoundError):list(bindings(opt))
 def test_lua_uses_live_bindings_not_lua_execution(self):
  opt=self.configure('hyprland','hyprland.lua');self.path.write_text('os.execute("never run")')
  data=[dict(modmask=68,key='T',dispatcher='exec',arg='foot',submap=''),dict(modmask=0,key='A',dispatcher='exec',arg='hidden',submap='special')]
  with patch('wm_config.subprocess.run',return_value=SimpleNamespace(stdout=json.dumps(data))) as run:
   rows=list(bindings(opt));self.assertEqual(run.call_args.args[0],['hyprctl','-j','binds'])
  self.assertEqual(len(rows),1);self.assertEqual(rows[0][0],'Super+Ctrl+T')
 def test_optional_keyboard_names_and_uninstalled_apps(self):
  self.configure('mango',extra='[names]\nfirefox = Browser of choice\n')
  self.path.write_text('bind=Super,w,spawn,firefox\n')
  targets={}
  with patch('launchers.shutil.which',return_value=None):rows=launch_rows(self.root,targets)
  self.assertEqual(rows,{'Browser of choice':['Super+w']});self.assertFalse(settings(self.root)['keyboard'])
 def test_none_and_invalid_environment(self):
  self.configure('none')
  self.assertEqual(list(bindings(settings(self.root))),[])
  with self.assertRaises(ValueError):self.configure('unsupported')

if __name__=='__main__':unittest.main()

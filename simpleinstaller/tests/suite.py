from pathlib import Path
import sys,runpy,tempfile,unittest,subprocess,os,json
from unittest.mock import patch
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B));i=runpy.run_path(str(B/'simpleinstaller'),run_name='installer_test');import recipes
SOURCES=B/'sources' if (B/'sources').is_dir() else B.parent
class Suite(unittest.TestCase):
 def test_catalogue_and_optional_features(self):
  names=set(i['CATALOG']);self.assertIn('simplegarmin',names);i['validate_sources'](SOURCES,list(names))
  self.assertNotIn('cava',i['packages'](['simpleplayer'],set()))
  self.assertIn('cava',i['packages'](['simplelock'],{'lock_visualizer'}))
  self.assertNotIn('keepassxc',i['packages'](['simplemail'],set()))
  self.assertIn('mpv',i['packages'](['simpleplayer'],set()))
  self.assertNotIn('mpv',i['packages'](['simplecalendar'],set()))
 def test_source_export_excludes_binaries_and_caches(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);(r/'program').write_bytes(b'\x7fELFtest');(r/'main.py').write_text('pass');(r/'cache.pyc').write_bytes(b'abc')
   self.assertEqual(set(recipes.source_ignore(r,['program','main.py','cache.pyc'])),{'program','cache.pyc'})
   (r/'link').symlink_to('/etc/passwd')
   with self.assertRaises(ValueError):recipes.source_ignore(r,['link'])
 def test_plan_all_no_home_changes(self):
  with tempfile.TemporaryDirectory() as td:
   r=subprocess.run([str(B/'simpleinstaller'),'--plan','all','--youtube'],env=dict(os.environ,HOME=td),text=True,capture_output=True)
   self.assertEqual(r.returncode,0,r.stderr);self.assertIn('Simplelock',r.stdout);self.assertEqual(list(Path(td).iterdir()),[])
 def test_orphan_optional_feature_rejected(self):
  r=subprocess.run([str(B/'simpleinstaller'),'--plan','simplecalendar','--youtube'],text=True,capture_output=True)
  self.assertNotEqual(r.returncode,0);self.assertIn('owning app',r.stderr)
 def test_tools_installs_without_picker_app(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);stage=r/'stage';work=r/'work';stage.mkdir();work.mkdir()
   i['stage_apps'](SOURCES,['simple-tools'],set(),stage,work)
   self.assertFalse((stage/'.local/bin/simplepicker').exists())
   self.assertTrue((stage/'.local/share/simplepicker/python/simplepicker_api.py').is_file())
   self.assertTrue((stage/'.local/share/simple-common/theme_loader.py').is_file())
 def test_scrolling_tui_and_empty_optional_selection(self):
  class Screen:
   def __init__(self,keys):self.keys=iter(keys)
   def getmaxyx(self):return 14,60
   def erase(self):pass
   def refresh(self):pass
   def keypad(self,value):pass
   def addnstr(self,y,x,text,n,*args):assert 0<=y<14 and len(text[:n])+x<60
   def getch(self):return next(self.keys)
  rows=[(str(n),'App '+str(n),'Details') for n in range(20)]
  with patch.object(i['curses'],'curs_set'),patch.object(i['curses'],'wrapper',side_effect=lambda f:f(Screen([ord('G'),32,10]))):self.assertEqual(i['choose_rows']('Test',rows),{'19'})
  with patch.object(i['curses'],'curs_set'),patch.object(i['curses'],'wrapper',side_effect=lambda f:f(Screen([10]))):self.assertEqual(i['choose_rows']('Options',rows,allow_empty=True),set())
  groups={str(n):'First' if n<10 else 'Second' for n in range(20)}
  with patch.object(i['curses'],'curs_set'),patch.object(i['curses'],'wrapper',side_effect=lambda f:f(Screen([ord('G'),32,ord('g'),32,10]))):self.assertEqual(i['choose_rows']('Groups',rows,groups=groups),{'0','19'})
  apps,groups=i['app_menu_rows']();self.assertEqual(set(groups),set(i['CATALOG']))
  for group,_ in i['APP_GROUPS']:
   labels=[label for key,label,_ in apps if groups[key]==group]
   self.assertEqual(labels,sorted(labels,key=str.casefold))
 def test_preferences_and_default_preservation(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);stage=r/'stage';app=stage/'.local/share/applications/simplelock.desktop';app.parent.mkdir(parents=True);app.write_text('Exec=simplelock\n')
   dirs={'home':r,'bin':r/'bin','src':r/'src','config':r/'cfg','data':r/'data','state':r/'state'}
   target=dirs['config']/'simplelock/config.toml';target.parent.mkdir(parents=True);target.write_text('personal')
   files=i['payload'](stage,dirs,['simplelock'],{'lock_visualizer'},'~/Music',{'terminal':['kitty','--']})
   self.assertIn('visualizer = true',files[target][0].read_text())
   i['apply_files'](files,dirs['state']);self.assertEqual(target.read_text(),'personal')
   prefs=(dirs['config']/'simple/preferences.toml').read_text();self.assertIn('["kitty", "--"]',prefs)
if __name__=='__main__':unittest.main()

"""Desired-state selection must never turn a cancelled install into removal."""
import contextlib,io,sys,unittest
from pathlib import Path
from importlib.machinery import SourceFileLoader
from unittest.mock import patch
base=Path(__file__).resolve().parents[1];sys.path.insert(0,str(base))
m=SourceFileLoader('installer_manage',str(base/'simpleinstaller')).load_module()
class Terminal(io.StringIO):
 def isatty(self):return True
class Tests(unittest.TestCase):
 def session(self,before,desired,answer='y',success=True):
  state=set(before);calls=[]
  def install(args,names,options):
   calls.append(('install',set(names)))
   if isinstance(success,Exception):raise success
   if success:state.update(names)
   return success
  def remove(args):calls.append(('remove',set(args.uninstall)));return 0
  with contextlib.redirect_stdout(Terminal()),patch.object(m.sys.stdin,'isatty',return_value=True),patch.object(m.uninstall,'read',side_effect=lambda dirs:{'apps':sorted(state),'files':{}}),patch.object(m,'select_menu',return_value=desired) as menu,patch.object(m,'choose_preferences'),patch.object(m,'show_plan'),patch.object(m,'install',side_effect=install),patch.object(m,'remove_apps',side_effect=remove),patch('builtins.input',return_value=answer):
   m.main([])
   menu.assert_called_once_with(set(before)&set(m.CATALOG))
  return calls
 def test_keep_is_noop(self):self.assertEqual(self.session({'simpletimer'},{'simpletimer'}),[])
 def test_add_and_remove(self):self.assertEqual(self.session({'simpletimer'},{'simplenotes'}),[('install',{'simplenotes'}),('remove',{'simpletimer'})])
 def test_remove_all(self):self.assertEqual(self.session({'simpletimer'},set()),[('remove',{'simpletimer'})])
 def test_empty_new_install(self):self.assertEqual(self.session(set(),set()),[])
 def test_cancel_menu(self):self.assertEqual(self.session({'simpletimer'},None),[])
 def test_decline_plan(self):self.assertEqual(self.session({'simpletimer'},{'simplenotes'},answer='n'),[])
 def test_cancel_install_keeps_existing(self):self.assertEqual(self.session({'simpletimer'},{'simplenotes'},success=False),[('install',{'simplenotes'})])
 def test_failure_keeps_existing(self):
  with self.assertRaisesRegex(ValueError,'build failed'):self.session({'simpletimer'},{'simplenotes'},success=ValueError('build failed'))
 def test_other_bundle_apps_untouched(self):self.assertEqual(self.session({'simpletimer','unknown-app'},set()),[('remove',{'simpletimer'})])
 def test_menu_starts_checked(self):
  with patch.object(m,'choose_rows',return_value={'simpletimer'}) as choose:
   self.assertEqual(m.select_menu({'simpletimer'}),{'simpletimer'})
   self.assertEqual(choose.call_args.kwargs['chosen'],{'simpletimer'})
   self.assertTrue(choose.call_args.kwargs['allow_empty'])
if __name__=='__main__':unittest.main()

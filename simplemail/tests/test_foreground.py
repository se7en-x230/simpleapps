import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
from unittest.mock import patch
import mail_foreground as f
class Tests(unittest.TestCase):
 def test_hidden_is_shown_before_focused(self):
  c={'appid':f.APP_ID,'id':42,'is_minimized':True,'is_namedscratchpad':True,'is_visible':False}
  with patch.object(f,'command',side_effect=[{'clients':[c]},{'success':True},{'success':True}]) as call:
   self.assertTrue(f.raise_once());self.assertIn('toggle_named_scratchpad',call.call_args_list[1].args[2]);self.assertEqual(call.call_args_list[2].args[2],'focusid')
 def test_visible_is_never_toggled(self):
  c={'appid':f.APP_ID,'id':42,'is_minimized':False,'is_visible':True}
  with patch.object(f,'command',side_effect=[{'clients':[c]},{'success':True}]) as call:
   self.assertTrue(f.raise_once());self.assertEqual(call.call_args_list[1].args[2],'focusid')
 def test_already_focused_does_nothing(self):
  with patch.object(f,'command',return_value={'clients':[{'appid':f.APP_ID,'id':42,'is_focused':True}]}) as call:
   self.assertTrue(f.raise_once());self.assertEqual(call.call_count,1)
 def test_missing_window_retries_without_toggling_other_apps(self):
  with patch.object(f,'command',return_value={'clients':[{'appid':'other','id':8}]}) as call:
   self.assertFalse(f.raise_once());self.assertEqual(call.call_count,1)
if __name__=='__main__':unittest.main()

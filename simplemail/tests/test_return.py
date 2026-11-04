import ast,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
root=Path(__file__).parent
if not (root/'simplemail.py').exists():root=root.parent
sys.path.insert(0,str(root))
import mail_foreground as f
class ReturnTests(unittest.TestCase):
 def test_capture(self):
  with patch.object(f,'command',return_value={'clients':[{'id':7,'appid':'libreoffice-calc','is_focused':True}]}):
   self.assertEqual(f.capture_origin(),{'id':7,'appid':'libreoffice-calc'})
 def test_ignore_mail_as_origin(self):
  with patch.object(f,'command',return_value={'clients':[{'id':7,'appid':f.APP_ID,'is_focused':True}]}):self.assertIsNone(f.capture_origin())
 def test_restore_existing_origin(self):
  origin={'id':7,'appid':'libreoffice-calc'}
  with patch.object(f,'command',side_effect=[{'clients':[origin]},{'success':True}]) as command:
   self.assertFalse(f.restore_origin(origin));self.assertEqual(command.call_args.args,('mmsg','dispatch','focusid','client,7'))
 def test_closed_origin_is_ignored(self):
  with patch.object(f,'command',return_value={'clients':[{'id':7,'appid':'other'}]}) as command:
   f.restore_origin({'id':7,'appid':'libreoffice-calc'});self.assertEqual(command.call_count,1)
 def test_success_hides_only_export(self):
  tree=ast.parse((root/'simplemail.py').read_text())
  gui=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='gui')
  sent=next(n for n in gui.body if isinstance(n,ast.FunctionDef) and n.name=='sent')
  for exported in (False,True):
   with self.subTest(exported=exported):
    state={'draft':Mock(exported=exported,return_origin={'id':7,'appid':'libreoffice-calc'}),'window':Mock(),'inbox':None}
    env={'state':state,'discard':Mock(),'GLib':Mock(),'restore_origin':f.restore_origin}
    exec(compile(ast.Module(body=[sent],type_ignores=[]),'callback','exec'),env);env['sent']()
    self.assertEqual(state['window'].minimize.call_count,int(exported))
    self.assertEqual(env['GLib'].timeout_add.call_count,int(exported));env['discard'].assert_called_once()
if __name__=='__main__':unittest.main()

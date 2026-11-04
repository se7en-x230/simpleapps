import importlib.util,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
p=Path(__file__).resolve().parents[1]/'simplemail.py';spec=importlib.util.spec_from_file_location('mail_test',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 def run_request(self,args):
  with patch.object(sys,'argv',['simplemail',*args]),patch.object(m,'desktop_environment'),patch.object(m,'setup_config',return_value=(None,{})),patch.object(m,'setup_accounts',return_value=[{}]),patch.object(m,'settings',return_value={}),patch.object(m,'gui',return_value=0),patch.object(m,'launch_foreground') as foreground:
   self.assertEqual(m.main(),0);return foreground.call_count
 def test_background_does_not_raise(self):self.assertEqual(self.run_request(['--background']),0)
 def test_accounting_draft_raises_existing_instance(self):
  with tempfile.TemporaryDirectory() as folder:
   for k,v in {'recipient':'test@example.invalid','subject':'Test','body':'','attachments':'/tmp/test.pdf'}.items():Path(folder,k+'.txt').write_text(v)
   self.assertEqual(self.run_request(['--draft-dir',folder]),1)
if __name__=='__main__':unittest.main()

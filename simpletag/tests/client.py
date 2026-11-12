import importlib.util,json,unittest
from pathlib import Path
from unittest.mock import patch
p=Path(__file__).resolve().parents[1]/'client.py'
spec=importlib.util.spec_from_file_location('tag_client',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Socket:
 def __init__(self,response):self.response=json.dumps(response).encode()+b'\n'
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def settimeout(self,*args):pass
 def connect(self,*args):pass
 def sendall(self,*args):pass
 def recv(self,*args):return self.response
class Tests(unittest.TestCase):
 def test_old_bridge_remove_uses_only_selected_paths(self):
  path='/music/album $(literal)/track 1.flac'
  state={'busy':False,'groups':[{'id':'chosen','files':[{'path':path}]},{'id':'other','files':[{'path':'/other.flac'}]}]}
  with patch.object(m.socket,'socket',side_effect=[Socket({'error':'Unknown action.'}),Socket(state)]),patch.object(m.subprocess,'run') as run:
   self.assertTrue(m.Client().request('remove',group='chosen')['ok'])
   self.assertEqual(run.call_args.args[0],['picard','-e','REMOVE',path])
 def test_old_bridge_clear_waits_for_empty(self):
  responses=[Socket({'error':'Select a current album or folder first.'}),Socket({'busy':False}),Socket({'groups':[],'busy':False})]
  with patch.object(m.socket,'socket',side_effect=responses),patch.object(m.subprocess,'run') as run:
   self.assertTrue(m.Client().request('clear')['ok'])
   self.assertEqual(run.call_args.args[0],['picard','-e','REMOVE_ALL','-e','REMOVE_EMPTY'])
 def test_old_bridge_busy_not_removed(self):
  with patch.object(m.socket,'socket',side_effect=[Socket({'error':'Unknown action.'}),Socket({'busy':True})]),patch.object(m.subprocess,'run') as run:
   with self.assertRaises(ValueError):m.Client().request('remove',group='chosen')
   run.assert_not_called()
if __name__=='__main__':unittest.main()

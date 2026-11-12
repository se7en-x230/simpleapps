import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
from enum import Enum
import sys, tempfile, unittest
from unittest.mock import patch
src=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('engine',src/'bridge/engine.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class State(Enum):PENDING=0;NORMAL=1;CHANGED=2;ERROR=3
class File:
 def __init__(self,path,state=State.CHANGED):
  self.filename=path;self.state=state;self.orig_metadata={'title':'Before'};self.metadata={'title':'After'};self.parent=None;self.parent_item=None;self.saves=0
 def save(self):self.saves+=1;self.state=State.PENDING
class Tagger:
 def __init__(self):
  self.files=[];self.albums={};self.removed=[];self.shown=False;self._pending_files_count=0;self._saving_files_count=0
  self.thread_pool=self.priority_thread_pool=self.save_thread_pool=NS(activeThreadCount=lambda:0)
  self.webservice=NS(num_pending_web_requests=0);self._acoustid=NS(_running=False);self.use_acoustid=True;self.unclustered_files=object()
 def iter_all_files(self):return iter(self.files)
 def remove_files(self,files):
  self.removed+=files
  for f in files:
   if f in self.files:self.files.remove(f)
 def cluster(self,files,callback):self.clustered=files;callback()
 def autotag(self,items):self.looked_up=items
 def analyze(self,files):self.scanned=files
 def add_paths(self,paths):self.loaded=paths
 def bring_tagger_front(self):self.shown=True
class Tests(unittest.TestCase):
 def setUp(self):
  self.patch=patch.dict(sys.modules,{'picard.file':NS(File=NS(State=State))});self.patch.start();self.addCleanup(self.patch.stop)
  self.t=Tagger();self.e=m.Engine(self.t)
 def album(self,files,safe):
  self.t.files=files
  self.t.albums={'a':NS(id='a',metadata={'album':'Example'},iterfiles=lambda:[f for f in files if f in self.t.files],iter_correctly_matched_tracks=lambda:[NS(files=[f]) for f in safe if f in self.t.files])}
 def test_save_completion_errors_and_duplicates(self):
  good,bad,duplicate=[File('/music/'+n) for n in ('good.flac','bad.flac','duplicate.flac')]
  self.album([good,bad,duplicate],[good,bad]);self.e.action({'action':'save','group':'album:a'})
  self.e.snapshot();self.assertFalse(self.t.removed)
  good.state=State.NORMAL;bad.state=State.ERROR
  result=self.e.snapshot();self.assertEqual(self.t.removed,[good]);self.assertIn(bad,self.t.files);self.assertEqual(duplicate.saves,0)
  self.assertFalse(result['busy']);self.assertIn('could not',result['message'])
 def test_lookup_all_unmatched_and_scan_selected_folder(self):
  one=File('/one/first.flac');two=File('/two/second.flac');one.parent=two.parent=self.t.unclustered_files;self.t.files=[one,two]
  self.e.action({'action':'lookup','group':'folder:/one'});self.assertEqual(self.t.clustered,[one,two]);self.assertEqual(self.t.looked_up,[self.t.unclustered_files])
  self.e.action({'action':'scan','group':'folder:/two'});self.assertEqual(self.t.scanned,[two])
 def test_clear_on_close_never_saves(self):
  one=File('/one/a.flac');two=File('/two/b.flac');self.t.files=[one,two]
  self.e.action({'action':'clear'})
  self.assertEqual(self.t.removed,[one,two]);self.assertFalse(self.t.files)
  self.assertEqual(one.saves+two.saves,0)
 def test_clear_waits_for_work(self):
  self.t._pending_files_count=1
  with self.assertRaises(ValueError):self.e.action({'action':'clear'})
  self.assertFalse(self.t.removed)
 def test_remove_discards_only_selected_without_saving(self):
  one=File('/one/a.flac');two=File('/two/b.flac');self.t.files=[one,two]
  self.e.action({'action':'remove','group':'folder:/one'})
  self.assertEqual(self.t.removed,[one]);self.assertEqual(self.t.files,[two]);self.assertEqual(one.saves,0)
  with self.assertRaises(ValueError):self.e.action({'action':'remove','group':'missing'})
 def test_remove_matched_does_not_save(self):
  f=File('/music/a.flac');self.album([f],[f]);self.e.action({'action':'remove','group':'album:a'})
  self.assertEqual(f.saves,0);self.assertEqual(self.t.removed,[f])
 def test_remove_blocked_during_save(self):
  f=File('/music/a.flac');self.album([f],[f]);self.e.action({'action':'save','group':'album:a'})
  with self.assertRaises(ValueError):self.e.action({'action':'remove','group':'album:a'})
  self.assertFalse(self.t.removed)
 def test_idle_pipe_listener_is_not_work(self):
  self.t.pipe_handler=NS(pipe_running=True)
  self.t.thread_pool=NS(activeThreadCount=lambda:1)
  self.assertFalse(self.e.busy())
 def test_busy_rejects_actions(self):
  self.t._pending_files_count=1
  with self.assertRaises(ValueError):self.e.action({'action':'load','folder':'/tmp'})
 def test_folder_only_and_unknown_group(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'song.flac';p.touch()
   with self.assertRaises(ValueError):self.e.action({'action':'load','folder':str(p)})
   self.e.action({'action':'load','folder':d});self.assertEqual(self.t.loaded,[d])
  with self.assertRaises(ValueError):self.e.action({'action':'save','group':'missing'})
 def test_empty_folder_not_cwd(self):
  with self.assertRaises(ValueError):self.e.action({'action':'load'})
 def test_no_auto_save(self):
  f=File('/music/song.flac');self.album([f],[f]);s=self.e.snapshot()
  self.assertEqual(f.saves,0);self.assertEqual(s['groups'][0]['files'][0]['before']['title'],'Before')
 def test_scan_disabled(self):
  self.t.files=[File('/one/a.flac')];self.t.use_acoustid=False
  with self.assertRaises(ValueError):self.e.action({'action':'scan','group':'folder:/one'})
if __name__=='__main__':unittest.main()

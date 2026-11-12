"""Isolated real Picard harness; only generated test audio is accepted."""
import importlib.util,sys
from pathlib import Path
from types import SimpleNamespace as NS
from PyQt6 import QtCore
import picard.tagger
source=Path(__file__).resolve().parents[1]/'bridge'
spec=importlib.util.spec_from_file_location('test_bridge',source/'__init__.py',submodule_search_locations=[str(source)])
m=importlib.util.module_from_spec(spec);sys.modules['test_bridge']=m;spec.loader.exec_module(m)
original=picard.tagger.Tagger.run

def run(t):
 bridge=m.Bridge(t);t.test_bridge=bridge
 real=bridge.engine.action
 def action(request):
  if request.get('action')=='test-match':
   files=list(t.iter_all_files());assert len(files)==1
   f=files[0];assert Path(f.filename).is_relative_to(Path(sys.argv[sys.argv.index('-c')+1]).parent)
   f.metadata['title']='Simpletag saved test';f.update()
   t.albums['test']=NS(id='test',metadata={'album':'Test release'},iterfiles=lambda:[f] if f in t.files.values() else [],iter_correctly_matched_tracks=lambda:[NS(files=[f])])
   return {'ok':True}
  if request.get('action')=='test-quit':
   t.albums.pop('test',None);QtCore.QTimer.singleShot(100,t.quit);return {'ok':True}
  return real(request)
 bridge.engine.action=action
 return original(t)
picard.tagger.Tagger.run=run
picard.tagger.main(autoupdate=False)

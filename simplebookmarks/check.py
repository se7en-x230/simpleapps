from pathlib import Path
from tempfile import TemporaryDirectory
from importlib.machinery import SourceFileLoader
import json,os
from unittest.mock import patch
m=SourceFileLoader('bookmarks',str(Path(__file__).with_name('simplebookmarks'))).load_module()
with TemporaryDirectory() as td:
 root=Path(td);p=root/'bookmarks.json';s=m.Store(p)
 record={'label':'Example','url':'https://example.com','tag':'keep'}
 s.change(None,record);other=m.Store(p)
 s.change(0,record|{'label':'Edited'});assert json.loads(p.read_text())[0]['tag']=='keep'
 assert json.loads(p.with_suffix('.json.bak').read_text())==[record]
 try:other.change(None,record);raise AssertionError('stale edit accepted')
 except ValueError:pass
 s.change(0);assert json.loads(p.read_text())==[]
 p.write_text('broken');before=p.read_bytes()
 try:s.load();raise AssertionError('bad JSON accepted')
 except ValueError:pass
 assert p.read_bytes()==before
 for url in ('javascript:alert(1)','https://','bad','https://example.com\n'):assert not m.valid_url(url)
 legacy=root/'data/simplepicker/bookmarks.json';legacy.parent.mkdir(parents=True);legacy.write_text('[]')
 with patch.dict(os.environ,{'XDG_CONFIG_HOME':str(root/'config'),'XDG_DATA_HOME':str(root/'data')}):
  cfg,path=m.settings();assert path==legacy
  assert m.settings()[1]==legacy
print('PASS: atomic edits, backup, metadata, conflict protection, malformed input and legacy configuration')
with TemporaryDirectory() as td:
 p=Path(td)/'bookmarks.json';history=p.with_name('bookmark-history.json');history.write_text(json.dumps({'https://a.test':4,'https://b.test':9}))
 first=m.Usage(p);second=m.Usage(p);records=[dict(url='https://a.test'),dict(url='https://b.test'),dict(url='https://c.test')]
 assert first.order(records)==[1,0,2]
 first.opened('https://a.test');second.opened('https://a.test');assert m.Usage(p).count('https://a.test')==6
 assert m.category({'category':' Work '})=='Work'
print('PASS: existing usage ordering, persistent counts and concurrent history updates')

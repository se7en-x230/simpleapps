#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory
from importlib.machinery import SourceFileLoader
from unittest.mock import patch
import os,subprocess,json
m=SourceFileLoader('capture',str(Path(__file__).with_name('simplecapture'))).load_module()
with TemporaryDirectory() as tmp:
 root=Path(tmp);bin=root/'bin';bin.mkdir();config=root/'config';(config/'swappy').mkdir(parents=True)
 (config/'swappy/config').write_text('[Default]\nsave_dir='+str(root/'Existing shots')+'\n')
 fake=bin/'helper';fake.write_text('''#!/usr/bin/env python3
import sys,os,json
from pathlib import Path
name=Path(sys.argv[0]).name;root=Path(os.environ['TEST_ROOT'])
with (root/'calls').open('a') as f:f.write(json.dumps([name,*sys.argv[1:]])+'\\n')
if name=='slurp':
 if os.environ.get('CANCEL'):sys.exit(1)
 print('10,20 300x200')
elif name=='grim':sys.stdout.buffer.write(b'\\x89PNG\\r\\n\\x1a\\nfixture')
elif name=='swappy':
 conf=Path(os.environ['XDG_CONFIG_HOME'])/'swappy/config'
 (root/'editor-config').write_text(conf.read_text())
 sys.stdout.buffer.write(Path(sys.argv[2]).read_bytes()+b'edited')
elif name=='wl-copy':(root/'clipboard').write_bytes(sys.stdin.buffer.read())
''');fake.chmod(0o755)
 for name in ('grim','slurp','swappy','wl-copy'):(bin/name).symlink_to(fake)
 with patch.dict(os.environ,{'HOME':str(root),'XDG_CONFIG_HOME':str(config),'TEST_ROOT':str(root),'PATH':str(bin)+':'+os.environ['PATH']}):
  opts=m.load_config();assert opts['save_dir']==root/'Existing shots'
  opts.update(settle_ms=0,notify=False)
  original=(config/'swappy/config').read_text()
  m.capture(opts);assert (root/'clipboard').read_bytes().endswith(b'edited')
  assert (config/'swappy/config').read_text()==original
  assert 'Existing shots' in (root/'editor-config').read_text()
  (root/'calls').write_text('');before=(root/'clipboard').read_bytes()
  with patch.dict(os.environ,{'CANCEL':'1'}):assert m.capture(opts) is None
  assert (root/'clipboard').read_bytes()==before
  assert all(json.loads(line)[0]=='slurp' for line in (root/'calls').read_text().splitlines())
  opts.update(edit=False,save=True,mode='fullscreen')
  first=m.capture(opts);second=m.capture(opts);assert first!=second and first.is_file() and second.is_file()
  calls=[json.loads(line) for line in (root/'calls').read_text().splitlines()];assert ['grim','-'] in calls
  print('PASS: legacy save-directory migration, exact PNG output, isolated editor config, cancellation, fullscreen, unique saves')

#!/usr/bin/env python3
"""Core chooser contracts and optional Yazi integration, no GUI required."""
from importlib.machinery import SourceFileLoader
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os, subprocess
m=SourceFileLoader('simplefiles',str(Path(__file__).with_name('simplefiles'))).load_module()
with TemporaryDirectory() as tmp:
 root=Path(tmp); config=root/'config';config.mkdir()
 with patch.dict(os.environ,{'HOME':str(root),'XDG_CONFIG_HOME':str(config)}):
  b=m.bookmarks();assert b['h']==root and b['d']==root/'Downloads' and b['/']==Path('/')
  (config/'user-dirs.dirs').write_text('XDG_DOWNLOAD_DIR="$HOME/Inbox"\n')
  assert m.bookmarks()['d']==root/'Inbox'
  (config/'yazi').mkdir();(config/'yazi/keymap.toml').write_text('[mgr]\nkeymap=[{on=["g","p"],run="cd ~/Cloud"},{on=["g","x"],run="shell touch /tmp/SHOULD_NOT_EXIST"}]\n')
  assert m.bookmarks()['p']==root/'Cloud' and 'x' not in m.bookmarks()
  (config/'yazi/keymap.toml').write_text('malformed [');assert m.bookmarks()['h']==root
 folder=root/'folder';folder.mkdir();a=root/'a " $`.txt';a.write_text('original')
 assert m.initial_location(folder)==(folder,'')
 assert m.initial_location(root/'new.txt',True)==(root,'new.txt')
 assert m.chosen_paths(root,folder,{},directory=True)==[folder]
 assert m.chosen_paths(root,None,{},directory=True)==[root]
 assert m.chosen_paths(root,a,{},multiple=False)==[a]
 assert m.chosen_paths(root,None,{a:None},multiple=True)==[a]
 target=m.save_target(root,'new.txt');assert not target.exists()
 for bad in ('','../bad','a/b','a\nb'):
  try:m.save_target(root,bad)
  except ValueError:pass
  else:raise AssertionError(bad)
 output=root/'result';m.write_result([a],output);assert output.read_text()==str(a)+'\n'
 try:m.write_result([root/'a\nb'],output)
 except ValueError:pass
 else:raise AssertionError('newline must be rejected')
 assert a.read_text()=='original'
 # Check the adapter preserves exact arguments and never creates save placeholders.
 import shutil,json
 shutil.copy(Path(__file__).with_name('simplefiles-portal'),root/'simplefiles-portal')
 fake=root/'simplefiles';fake.write_text('#!/usr/bin/env python3\nimport sys,json\nfrom pathlib import Path\nPath(__file__).with_name("args.json").write_text(json.dumps(sys.argv[1:]))\n');fake.chmod(0o755)
 subprocess.run([str(root/'simplefiles-portal'),'1','0','1',str(target),str(output),'0'],check=True)
 assert json.loads((root/'args.json').read_text())==['--output',str(output),'--multiple','--save','--',str(target)]
 assert output.read_text()=='' and not target.exists()
print('PASS: portable defaults, optional bookmarks, chooser results, save safety, exact portal arguments')

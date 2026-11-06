#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory
from importlib.machinery import SourceFileLoader
from unittest.mock import patch
from gi.repository import GLib
import os,time
m=SourceFileLoader('notes',str(Path(__file__).with_name('simplenotes'))).load_module()
with TemporaryDirectory() as tmp:
 root=Path(tmp);notes=root/'Notes';notes.mkdir();store=m.Notes(notes)
 p=store.create('first','Original\r\n');text,etag=store.read(p);assert text=='Original\r\n'
 time.sleep(.01);etag=store.save(p,'Edited\n',etag);assert p.read_text()=='Edited\n'
 time.sleep(.01);p.write_text('External\n')
 try:store.save(p,'Must not overwrite',etag)
 except GLib.Error:pass
 else:raise AssertionError('Conflict was not rejected')
 assert p.read_text()=='External\n'
 try:store.create('first','overwrite')
 except FileExistsError:pass
 else:raise AssertionError('Existing note overwritten')
 for name in ('../escape','/tmp/outside','.hidden','folder/../escape','bad\nname'):
  try:store.target(name)
  except ValueError:pass
  else:raise AssertionError(name)
 (notes/'link').symlink_to(root,target_is_directory=True)
 try:store.target('link/escape')
 except ValueError:pass
 else:raise AssertionError('Symlink escaped root')
 (notes/'nested').mkdir();store.create('nested/ideas','Search this phrase')
 (notes/'image.png').write_bytes(b'\0png');(notes/'binary.dat').write_bytes(b'\0\xff');(notes/'.secret.md').write_text('hidden')
 assert {p.relative_to(notes).as_posix() for p,_ in store.scan()}=={'first.md','nested/ideas.md'}
 config=root/'config';config.mkdir()
 with patch.dict(os.environ,{'HOME':str(root),'XDG_CONFIG_HOME':str(config)}):
  assert m.configured_root(str(notes))==(notes,False)
  (config/'notesmanager').mkdir();(config/'notesmanager/config.toml').write_text('notes_dir="'+str(notes)+'"\n')
  assert m.configured_root()==(notes,False)
  (config/'simplenotes').mkdir();(config/'simplenotes/config.toml').write_text('notes_dir="../../Notes"\n')
  assert m.configured_root()[0].resolve()==notes
  assert m.settings()==m.DEFAULTS
  cfg=config/'simplenotes/config.toml'
  cfg.write_text('notes_dir="../../Notes"\nautosave=false\nautosave_delay_ms=1200\nfont_size=14\nwrap_text=false\nsearch_contents=false\nwindow_width=1200\nwindow_height=800\nsidebar_width=280\n')
  opts=m.settings();assert opts['font_size']==14 and not opts['autosave'] and not opts['search_contents']
  for invalid in ('font_size=0','autosave=1','unknown_option=true','window_width=640\nsidebar_width=600'):
   cfg.write_text(invalid)
   try:m.settings()
   except ValueError:pass
   else:raise AssertionError(invalid)
  cfg.unlink();m.ensure_config(notes);assert m.configured_root()[0].resolve()==notes
  before=cfg.read_text();m.ensure_config(root/'Other');assert cfg.read_text()==before
print('PASS: create, save, preserve external edits, no overwrite, path boundaries, scan and portable configuration')

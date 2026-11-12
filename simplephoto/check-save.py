"""Saving on filesystems without hard links must never overwrite another file."""
from pathlib import Path
from importlib.machinery import SourceFileLoader
from unittest.mock import patch
import errno,tempfile
from PIL import Image
m=SourceFileLoader('photo_save',str(Path(__file__).with_name('simplephoto'))).load_module()
with tempfile.TemporaryDirectory() as folder:
 root=Path(folder);source=root/'photo.png'
 Image.new('RGB',(8,8),(100,120,140)).save(source)
 original=source.read_bytes();data=m.read(source)
 existing=root/'photo~1.png';existing.write_bytes(b'existing version')
 for code in (errno.EPERM,errno.EOPNOTSUPP,errno.EXDEV,errno.ENOSYS):
  with patch.object(m.os,'link',side_effect=OSError(code,'hard links unavailable')):
   saved=m.save(source,data,{})
   assert saved.name == f'photo~{(errno.EPERM,errno.EOPNOTSUPP,errno.EXDEV,errno.ENOSYS).index(code)+2}.png'
   with Image.open(saved) as result:assert result.size==(8,8)
  assert source.read_bytes()==original
  assert existing.read_bytes()==b'existing version'
 stage=root/'stage';stage.write_bytes(b'complete copy');target=root/'partial'
 def interrupted(src,out):
  out.write(b'partial');raise OSError(errno.ENOSPC,'full')
 with patch.object(m.os,'link',side_effect=OSError(errno.EPERM,'unsupported')),patch.object(m.shutil,'copyfileobj',side_effect=interrupted):
  try:m.publish_copy(stage,target)
  except OSError as error:assert error.errno==errno.ENOSPC
  else:raise AssertionError('failed copy reported success')
 assert not target.exists() and stage.read_bytes()==b'complete copy'
 with patch.object(m.os,'link',side_effect=OSError(errno.EACCES,'denied')):
  try:m.publish_copy(stage,target)
  except OSError as error:assert error.errno==errno.EACCES
  else:raise AssertionError('permission error swallowed')
 assert not target.exists()
print('PASS: unsupported hard links, numbered copies, original/existing file protection, failed-copy cleanup, permission errors')

#!/usr/bin/env python3
"""Archive legacy source directories; keep one backward-compatible import path."""
from pathlib import Path
from datetime import datetime
import shutil,os

def migrate(home=None):
 explicit=home is not None;home=Path(home) if explicit else Path.home()
 source=home/'.local/src/simplemail' if explicit else Path(__file__).resolve().parent
 config=(home/'.config' if explicit else Path(os.environ.get('XDG_CONFIG_HOME',home/'.config')))/'simplemail'
 if not (source/'simplemail.py').is_file():raise RuntimeError('SimpleMail source missing at '+str(source))
 archive=(home/'.local/state' if explicit else Path(os.environ.get('XDG_STATE_HOME',home/'.local/state')))/'simplemail-layout-backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
 for name in ('scripts','tests'):
  old=config/name
  if old.is_symlink():
   if name=='scripts' and old.resolve()==source.resolve():continue
   raise RuntimeError('Unexpected SimpleMail '+name+' symlink; kept unchanged: '+str(old))
  if old.exists():
   archive.mkdir(parents=True,exist_ok=True);shutil.move(str(old),str(archive/name))
 config.mkdir(parents=True,exist_ok=True)
 link=config/'scripts'
 if not link.is_symlink():link.symlink_to(os.path.relpath(source,config),target_is_directory=True)
 return archive if archive.exists() else None
if __name__=='__main__':
 backup=migrate()
 print('SimpleMail source: '+str(Path(__file__).resolve().parent)+('; archived legacy code: '+str(backup) if backup else ''))

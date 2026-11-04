#!/usr/bin/env python3
from pathlib import Path
import os
import subprocess
source=Path(__file__).resolve().parent;config=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'simplemail'
config.mkdir(parents=True,exist_ok=True)
keys=config/'keys.ini'
if not keys.exists():keys.write_text((source/'defaults/keys.ini').read_text())
subprocess.run(['make','-C',str(source),'install'],check=True)
print('SimpleMail native frontend ready; existing IMAP/SMTP accounts preserved.')

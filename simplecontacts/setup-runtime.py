#!/usr/bin/env python3
from pathlib import Path
import os
import subprocess,requests,google.auth
h=Path.home();src=Path(__file__).parent
config=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'simplecontacts';config.mkdir(parents=True,exist_ok=True)
for p in (src/'defaults').iterdir():
 if not (config/p.name).exists():(config/p.name).write_text(p.read_text())
desktop=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'applications/simplecontacts.desktop';desktop.parent.mkdir(parents=True,exist_ok=True);desktop.write_text((src/'simplecontacts.desktop').read_text())
print('SimpleContacts ready; Google sign-in is per device.')

subprocess.run(['make','-C',str(src),'install'],check=True)

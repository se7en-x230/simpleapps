#!/usr/bin/env python3
from pathlib import Path
import os
import subprocess,sys
h=Path.home()
root=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'simple-calendar-runtime'
python=root/'bin/python'
requirements=['vdirsyncer[google]==0.21.0','icalendar==7.3.0','recurring-ical-events==3.8.2']
stamp=root/'requirements.txt'
expected='\n'.join(requirements)+'\n'+str(sys.version_info[:2])
if not python.exists() or not stamp.exists() or stamp.read_text()!=expected:
    subprocess.run([sys.executable,'-m','venv','--system-site-packages',str(root)],check=True)
    subprocess.run([str(python),'-m','pip','install',*requirements],check=True)
    stamp.write_text(expected)
subprocess.run([str(python),'-c','import icalendar,recurring_ical_events,vdirsyncer'],check=True)

source=Path(__file__).parent/'simple-calendar.desktop'
if source.exists():
    target=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'applications/simple-calendar.desktop'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(source.read_text())

config=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'simplecalendar'
config.mkdir(parents=True,exist_ok=True)
for source in (Path(__file__).parent/'defaults').glob('*'):
    target=config/source.name
    if source.is_file() and not target.exists():target.write_text(source.read_text())

subprocess.run(['make','-C',str(Path(__file__).parent),'install'],check=True)

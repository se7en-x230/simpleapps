#!/usr/bin/env python3
"""Run a personal Python menu with the test C UI, without editing its installation."""
import os,runpy,sys
from pathlib import Path
root=Path(__file__).resolve().parent
if len(sys.argv)<2:raise SystemExit('Usage: run-script.py /path/to/python-script [arguments]')
os.environ['SIMPLEPICKER_NATIVE']=str(root/'simplepicker-native')
sys.path.insert(0,str(root/'python'))
import ui  # Pin the native adapter before scripts prepend the installed library.
sys.argv=sys.argv[1:]
runpy.run_path(sys.argv[0],run_name='__main__')

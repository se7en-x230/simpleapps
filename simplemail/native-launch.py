#!/usr/bin/env python3
"""Desktop handoff; the application process is replaced by the native binary."""
import os,sys,json,subprocess,shutil
from pathlib import Path
from mail_foreground import capture_origin
from simplemail import desktop_environment

def main():
 desktop_environment();args=['--help' if x=='-h' else x for x in sys.argv[1:]];native=Path(shutil.which('simplemail-native') or Path(__file__).with_name('simplemail-native'))
 os.environ.setdefault('SIMPLEMAIL_SOURCE',str(Path(__file__).resolve().parent))
 if not native.is_file():raise RuntimeError('Native SimpleMail is missing. Build and install SimpleMail first.')
 maintenance=any(s in args for s in ('--encrypt-passwords','--migrate-keyring','--check','--check-server'))
 if maintenance:os.execv(sys.executable,[sys.executable,str(Path(__file__).with_name('simplemail.py')),*args])
 external='--draft-dir' in args or any(not s.startswith('-') for s in args)
 if external:
  origin=capture_origin()
  if origin:args+=['--origin',json.dumps(origin)]
 if '--background' not in args and '--help' not in args and '--quit' not in args:
  subprocess.Popen([sys.executable,str(Path(__file__).with_name('mail_foreground.py'))],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
 os.execv(str(native),[str(native),*args])
if __name__=='__main__':main()

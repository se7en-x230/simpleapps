#!/usr/bin/env python3
import argparse,sys,time,fcntl
import core,auth

def watch():
 core.init()
 with (core.ROOT/'worker.lock').open('a') as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return
  while True:
   if (core.ROOT/'google-token.json').exists():
    try:core.sync()
    except Exception as e:core.write(core.ROOT/'status.json',{'ok':False,'error':str(e)})
   time.sleep(1800)

if __name__=='__main__':
 p=argparse.ArgumentParser(description='SimpleContacts · Google Contacts and local address book')
 g=p.add_mutually_exclusive_group();g.add_argument('--sync',action='store_true');g.add_argument('--connect',action='store_true');g.add_argument('--watch',action='store_true');g.add_argument('--export',metavar='FILE')
 p.add_argument('--client-json');a=p.parse_args();core.init()
 try:
  if a.connect:auth.connect(a.client_json);print('Google Contacts connected and synced.')
  elif a.sync:core.sync();print('Contacts synced.')
  elif a.watch:watch()
  elif a.export:
   from pathlib import Path
   path=Path(a.export).expanduser()
   if path.exists():raise core.ContactError('Export file already exists; choose another filename.')
   print('Exported',core.export_vcard(path),'contacts.')
  else:
   import os
   from pathlib import Path
   os.execvp('simplecontacts-native',['simplecontacts-native'])
 except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)

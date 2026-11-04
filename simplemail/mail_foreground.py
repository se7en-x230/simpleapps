#!/usr/bin/env python3
"""Raise an explicitly requested mail draft, preserving Mango scratchpad behavior."""
import fcntl,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
APP_ID='com.go7.Simplemail'

def command(*args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=2)
    if result.returncode:raise RuntimeError('Window activation command failed')
    return json.loads(result.stdout)

def raise_once(app_id=APP_ID):
    clients=command('mmsg','get','all-clients').get('clients',[])
    target=next((c for c in clients if c.get('appid')==app_id),None)
    if target is None:return False
    if target.get('is_focused') and not target.get('is_minimized'):return True
    if target.get('is_minimized') or (target.get('is_namedscratchpad') and not target.get('is_visible')):
        # Toggle only a hidden window. An unconditional toggle would hide it
        # again on the next export, or strip its scratchpad status via focusid.
        result=command('mmsg','dispatch','toggle_named_scratchpad,^'+re.escape(app_id)+'$,none,true')
        if not result.get('success',False):return False
    result=command('mmsg','dispatch','focusid','client,'+str(int(target['id'])))
    return result.get('success',False)

def capture_origin():
    """Remember the window that requested an export, before presenting mail."""
    try:
        clients=command('mmsg','get','all-clients').get('clients',[])
        target=next((c for c in clients if c.get('is_focused') and c.get('appid')!=APP_ID),None)
        return {'id':int(target['id']),'appid':target['appid']} if target else None
    except (OSError,ValueError,KeyError,RuntimeError,subprocess.TimeoutExpired):return None

def restore_origin(origin):
    if not origin:return False
    try:
        clients=command('mmsg','get','all-clients').get('clients',[])
        target=next((c for c in clients if c.get('id')==origin['id'] and c.get('appid')==origin['appid']),None)
        if target and not target.get('is_minimized'):
            command('mmsg','dispatch','focusid','client,'+str(int(target['id'])))
    except (OSError,ValueError,KeyError,RuntimeError,subprocess.TimeoutExpired):pass
    return False  # One-shot GLib callback.

def main(app_id=APP_ID):
    runtime=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))
    lockpath=runtime/('simplemail-foreground-'+str(os.getuid())+'-'+re.sub('[^a-zA-Z0-9]','_',app_id)+'.lock')
    with lockpath.open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return 0
        if shutil.which('mmsg') and os.environ.get('MANGO_INSTANCE_SIGNATURE'):
            for _ in range(25):
                try:
                    if raise_once(app_id):return 0
                except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired):pass
                time.sleep(.1)
        elif shutil.which('wlrctl'):
            subprocess.run(['wlrctl','toplevel','focus','app_id:'+app_id],capture_output=True,timeout=3)
            return 0
    print('Simplemail: could not bring the draft window forward.',file=sys.stderr)
    return 1

if __name__=='__main__':sys.exit(main(sys.argv[1] if len(sys.argv)>1 else APP_ID))

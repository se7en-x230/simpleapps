#!/usr/bin/env python3
import argparse, fcntl, json, os, subprocess, sys, time, threading
from pathlib import Path
from datetime import date, datetime, timedelta
import core

def connect(provider=None,client_file=None,calendar_id=None):
    core.init()
    print('Connect a calendar\n\nGoogle needs a Desktop OAuth client JSON with the CalDAV API enabled.')
    print('Guide: https://developers.google.com/workspace/calendar/caldav/v2/guide')
    if (core.ROOT/'settings.json').exists():
        raise ValueError('An account is already configured. Keep its local data and sync history; use a separate account directory to change providers.')
    provider=provider or input('\nProvider [google/caldav]: ').strip() or 'google'
    if provider not in ('google','caldav'):raise ValueError('Choose google or caldav')
    local=core.ROOT/'calendars'/'main';local.mkdir(parents=True,exist_ok=True)
    conf='[general]\nstatus_path = '+json.dumps(str(core.ROOT/'sync-status'))+'\n'
    conf+='\n[pair calendar]\na = "local"\nb = "remote"\n'
    if provider=='google':
        client=Path(client_file or input('Desktop OAuth client JSON file path: ').strip()).expanduser()
        creds=json.loads(client.read_text()).get('installed')
        if not creds or not creds.get('client_id') or not creds.get('client_secret'):raise ValueError('Use a Desktop application OAuth client JSON')
        calendar=calendar_id or input('Google calendar ID (usually your Gmail address): ').strip()
        if not calendar or '\n' in calendar:raise ValueError('Calendar ID is required')
        conf+='collections = '+json.dumps([['main','main',calendar]])+'\n'
        remote='type = "google_calendar"\ntoken_file = '+json.dumps(str(core.ROOT/'google-token.json'))+'\n'
        remote+='client_id = '+json.dumps(creds['client_id'])+'\nclient_secret = '+json.dumps(creds['client_secret'])+'\n'
        if not (core.ROOT/'google-token.json').exists():
            sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'simple-common'))
            from google_oauth import authorize
            _,token=authorize('https://www.googleapis.com/auth/calendar',client)
            core.write(core.ROOT/'google-token.json',json.dumps(token))
        path=local.parent
    else:
        url=input('Full HTTPS CalDAV calendar collection URL: ').strip()
        if not url.startswith('https://'):raise ValueError('Use an HTTPS calendar collection URL')
        username=input('Username: ').strip()
        import getpass
        password=getpass.getpass('Password or app password: ')
        remote='type = "caldav"\nurl = '+json.dumps(url)+'\nusername = '+json.dumps(username)+'\npassword = '+json.dumps(password)+'\n'
        conf+='collections = null\n';path=local
    conf+='\n[storage local]\ntype = "filesystem"\npath = '+json.dumps(str(path))+'\nfileext = ".ics"\n\n[storage remote]\n'+remote
    core.write(core.ROOT/'vdirsyncer.conf',conf)
    with core.locked():
        binary=str(Path(sys.executable).parent/'vdirsyncer')
        subprocess.run([binary,'--config',str(core.ROOT/'vdirsyncer.conf'),'discover'],check=True)
        core.write(core.ROOT/'settings.json',json.dumps(dict(provider=provider,calendar='main')))
    if not core.sync():raise RuntimeError('Connection saved, but first sync failed. See Sync details in the calendar.')
    print('\nConnected. Events now sync in both directions.')
    input('Press Enter to close.')

def watch():
    core.init()
    with (core.ROOT/'worker.lock').open('a') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        next_sync=0
        while True:
            try:
                if time.monotonic()>=next_sync:
                    core.sync();next_sync=time.monotonic()+300
                core.project();core.notify_due()
            except Exception as exc:print(type(exc).__name__+': '+str(exc),flush=True)
            time.sleep(15)

def gui(day,show_report=False):
    os.execvp('simplecalendar-native',['simplecalendar-native','--day',day]+(['--show-90-day-report'] if show_report else []))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--day',default=date.today().isoformat());p.add_argument('--watch',action='store_true');p.add_argument('--sync',action='store_true');p.add_argument('--connect',action='store_true')
    p.add_argument('--show-90-day-report',action='store_true',help='Show the optional 90-day report button and marker');p.add_argument('--provider',choices=['google','caldav']);p.add_argument('--client-json');p.add_argument('--calendar-id')
    args=p.parse_args();core.init()
    try:
        if args.watch:watch()
        elif args.connect:connect(args.provider,args.client_json,args.calendar_id)
        elif args.sync:sys.exit(0 if core.sync() else 1)
        else:gui(args.day,args.show_90_day_report)
    except Exception as exc:
        print(str(exc),file=sys.stderr)
        if args.connect:input('Press Enter to close.')
        sys.exit(1)

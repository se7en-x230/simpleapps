"""Local iCalendar store, vdirsyncer transport, and dashboard projection."""
from pathlib import Path
from datetime import datetime, date, time, timedelta, timezone
from contextlib import contextmanager
from zoneinfo import ZoneInfo
import configparser, fcntl, hashlib, json, os, subprocess, sys, tempfile, uuid
from icalendar import Calendar, Event, Alarm
import recurring_ical_events

ROOT=Path(os.environ.get('SIMPLE_CALENDAR_HOME',str(Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'simple-calendar')))
CACHE=Path(os.environ.get('XDG_CACHE_HOME',str(Path.home()/'.cache')))/'simple-calendar/events.ini'
UTC=timezone.utc

def init():
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(ROOT,0o700)

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.calendar-')
    try:
        with os.fdopen(fd,'wb') as f:f.write(data if isinstance(data,bytes) else data.encode())
        os.replace(tmp,path)
    finally:
        Path(tmp).unlink(missing_ok=True)

def read_json(name,default):
    try:return json.loads((ROOT/name).read_text())
    except FileNotFoundError:return default

def settings():return read_json('settings.json',{})

def zone():
    try:return ZoneInfo(Path('/etc/localtime').resolve().as_posix().split('/zoneinfo/',1)[1])
    except (IndexError,ValueError):return datetime.now().astimezone().tzinfo

@contextmanager
def locked():
    init()
    with (ROOT/'operations.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        yield

def collections():
    return sorted(p for p in (ROOT/'calendars').glob('*') if p.is_dir() and not p.name.startswith('.'))

def collection(name):
    p=(ROOT/'calendars'/name).resolve()
    if p.parent!=(ROOT/'calendars').resolve() or not p.is_dir():raise ValueError('Choose a calendar first')
    return p

def local_dt(value):
    if isinstance(value,datetime):
        return value.replace(tzinfo=zone()) if value.tzinfo is None else value.astimezone(zone())
    return datetime.combine(value,time(),zone())

_view_cache={}
_view_stamp=None

def view_events(start,end):
    """Cache month windows for navigation; any local/synced file change invalidates."""
    global _view_stamp
    files=[]
    for directory in collections():
        for path in sorted(directory.glob('*.ics')):
            try:
                st=path.stat();files.append((str(path),st.st_mtime_ns,st.st_ctime_ns,st.st_size))
            except FileNotFoundError:continue
    stamp=(str(ROOT),str(zone()),tuple(files))
    if stamp!=_view_stamp:
        _view_cache.clear();_view_stamp=stamp
    a=start.date().replace(day=1)
    last=(end-timedelta(microseconds=1)).date().replace(day=1)
    b=(last+timedelta(days=32)).replace(day=1)
    key=(a,b)
    if key not in _view_cache:
        if len(_view_cache)>=12:_view_cache.pop(next(iter(_view_cache)))
        rows,errors=events(local_dt(a),local_dt(b))
        if errors:return rows,errors
        _view_cache[key]=(rows,errors)
    return _view_cache[key]

def events(start=None,end=None):
    start=start or datetime.now(zone())-timedelta(days=366)
    end=end or datetime.now(zone())+timedelta(days=730)
    result=[]; errors=[]
    for directory in collections():
        for path in directory.glob('*.ics'):
            try:
                raw=path.read_bytes(); cal=Calendar.from_ical(raw)
                masters=cal.walk('VEVENT')
                recurring=any('RRULE' in x or 'RDATE' in x or 'RECURRENCE-ID' in x for x in masters)
                for e in recurring_ical_events.of(cal).between(start,end):
                    if str(e.get('STATUS','')).upper()=='CANCELLED':continue
                    a=e.decoded('DTSTART'); b=e.decoded('DTEND',None)
                    if b is None:b=a+e.decoded('DURATION',timedelta(days=1) if not isinstance(a,datetime) else timedelta())
                    alarms=[]
                    for alarm in e.walk('VALARM'):
                        if str(alarm.get('ACTION','')).upper()!='DISPLAY':continue
                        trigger=alarm.decoded('TRIGGER',None)
                        if isinstance(trigger,timedelta):
                            base=b if alarm['TRIGGER'].params.get('RELATED','START')=='END' else a
                            alarms.append((local_dt(base)+trigger).isoformat())
                        elif isinstance(trigger,datetime):alarms.append(local_dt(trigger).isoformat())
                    result.append(dict(calendar=directory.name,file=path.name,hash=hashlib.sha256(raw).hexdigest(),
                        uid=str(e.get('UID','')),title=str(e.get('SUMMARY','Untitled event')),
                        start=local_dt(a).isoformat(),end=local_dt(b).isoformat(),
                        all_day=not isinstance(a,datetime),recurring=recurring,
                        description=str(e.get('DESCRIPTION','')),alarms=alarms,
                        editable=not recurring and 'ATTENDEE' not in e and 'ORGANIZER' not in e))
            except Exception as exc:
                errors.append(path.name+': '+type(exc).__name__)
    return sorted(result,key=lambda e:(e['start'],e['title'])),errors

def on_day(e,day):
    a=datetime.fromisoformat(e['start']);b=datetime.fromisoformat(e['end'])
    x=local_dt(day);y=x+timedelta(days=1)
    return a<y and (b>x or (a==b and x<=a<y))

def event_times(day,start,end,all_day,end_day=None):
    day=date.fromisoformat(day)
    last=date.fromisoformat(end_day) if end_day else day
    if last<day:raise ValueError('End date must not precede start date')
    if all_day:return day,last+timedelta(days=1)
    a=datetime.combine(day,time.fromisoformat(start),zone())
    b=datetime.combine(last,time.fromisoformat(end),zone())
    if b<=a:raise ValueError('End time must be later than start time')
    return a,b

def report_due(base):
    """User-requested +90-day estimate; receipt date can override in editor."""
    return (date.fromisoformat(base)+timedelta(days=90)).isoformat()


def reminder_values(value):
    """Accept legacy single values and up to five Google-compatible offsets."""
    values=value if isinstance(value,(list,tuple)) else ([] if value==-1 else [value])
    if len(values)>5:raise ValueError('Use at most five notifications')
    if any(type(n) is not int or not 0<=n<=40320 for n in values):
        raise ValueError('Notifications must be between the event start and four weeks before')
    return list(dict.fromkeys(values))

def add_alarms(event,title,values):
    for minutes in values:
        alarm=Alarm();alarm.add('ACTION','DISPLAY');alarm.add('DESCRIPTION',title.strip())
        alarm.add('TRIGGER',timedelta(minutes=-minutes));event.add_component(alarm)


def repeat_rule(repeat='none',repeat_interval=1):
    if repeat not in ('none','daily','weekly','monthly','yearly'):
        raise ValueError('Choose no repeat, daily, weekly, monthly or yearly')
    if type(repeat_interval) is not int or not 1<=repeat_interval<=99:
        raise ValueError('Repeat interval must be between 1 and 99')
    return None if repeat=='none' else {'FREQ':repeat.upper(),'INTERVAL':repeat_interval}


def add(calendar,title,day,start='09:00',end='10:00',all_day=False,reminder=1440,description='',end_day=None,repeat='none',repeat_interval=1):
    if not title.strip():raise ValueError('Enter an event title')
    rule=repeat_rule(repeat,repeat_interval)
    a,b=event_times(day,start,end,all_day,end_day)
    notifications=reminder_values(reminder)
    cal=Calendar();cal.add('VERSION','2.0');cal.add('PRODID','-//Simple Calendar//EN')
    e=Event();uid=str(uuid.uuid4());e.add('UID',uid);e.add('DTSTAMP',datetime.now(UTC))
    e.add('DTSTART',a);e.add('DTEND',b);e.add('SUMMARY',title.strip())
    if rule:e.add('RRULE',rule)
    if description.strip():e.add('DESCRIPTION',description.strip())
    add_alarms(e,title,notifications)
    cal.add_component(e)
    with locked():
        write(collection(calendar)/(uid+'.ics'),cal.to_ical())
        mark_pending()
        project()
    return uid

def update(event,title,day,start='09:00',end='10:00',all_day=False,reminder=1440,description='',end_day=None,repeat='none',repeat_interval=1):
    if not title.strip():raise ValueError('Enter an event title')
    rule=repeat_rule(repeat,repeat_interval)
    notifications=reminder_values(reminder)
    a,b=event_times(day,start,end,all_day,end_day)
    with locked():
        p=collection(event['calendar'])/event['file']
        if p.name!=event['file'] or p.suffix!='.ics':raise ValueError('Invalid event')
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=event['hash']:raise ValueError('Event changed. Reopen it before editing.')
        cal=Calendar.from_ical(raw);items=cal.walk('VEVENT')
        if len(items)!=1:raise ValueError('Manage this event in your calendar provider')
        e=items[0]
        if any(k in e for k in ('RRULE','RDATE','RECURRENCE-ID','ATTENDEE','ORGANIZER')):
            raise ValueError('Manage repeating events and invitations in your calendar provider')
        for key in ('DTSTART','DTEND','DURATION','SUMMARY','DESCRIPTION','DTSTAMP','LAST-MODIFIED','SEQUENCE'):
            if key=='SEQUENCE':sequence=int(e.get(key,0))+1
            e.pop(key,None)
        for key,value in [('DTSTART',a),('DTEND',b),('SUMMARY',title.strip()),('DESCRIPTION',description.strip()),
                          ('DTSTAMP',datetime.now(UTC)),('LAST-MODIFIED',datetime.now(UTC)),('SEQUENCE',sequence)]:e.add(key,value)
        if rule:e.add('RRULE',rule)
        e.subcomponents=[c for c in e.subcomponents if c.name!='VALARM']
        add_alarms(e,title,notifications)
        write(ROOT/'history'/(str(uuid.uuid4())+'.ics'),raw)
        write(p,cal.to_ical());mark_pending();project()


def mark_pending():
    s=read_json('sync.json',{});s.update(pending=True);write(ROOT/'sync.json',json.dumps(s))

def remove(event):
    with locked():
        p=collection(event['calendar'])/event['file']
        if p.name!=event['file'] or p.suffix!='.ics':raise ValueError('Invalid event')
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=event['hash']:raise ValueError('Event changed since it was displayed. Refresh and try again.')
        if not event.get('editable',not event['recurring']):raise ValueError('Remove recurring events in your calendar provider; this avoids deleting an entire series accidentally.')
        write(ROOT/'trash'/(str(uuid.uuid4())+'.ics'),raw)
        p.unlink()
        mark_pending();project()

def next_report(rows,today=None):
    today=today or datetime.now(zone()).date()
    days=[datetime.fromisoformat(e['start']).date() for e in rows
          if e['title'].removeprefix('🛂 ').strip().casefold()=='90-day report'
          and datetime.fromisoformat(e['start']).date()>=today]
    return min(days).isoformat() if days else ''


def project():
    rows,errors=events()
    days={}
    now=datetime.now(zone())
    for e in rows:
        a=datetime.fromisoformat(e['start']);b=datetime.fromisoformat(e['end'])
        day=max(a.date(),(now-timedelta(days=366)).date())
        last=min((b-timedelta(microseconds=1)).date() if b>a else a.date(),(now+timedelta(days=730)).date())
        while day<=last:
            label=('All day' if e['all_day'] else a.strftime('%H:%M') if day==a.date() else 'Continues')+' · '+e['title']
            days.setdefault(day.isoformat(),[]).append(label.replace('\n',' ').replace('\r',' '))
            day+=timedelta(days=1)
    def escaped(s):return s.replace('\\','\\\\').replace('\n','\\n').replace('\r','')
    output='[events]\n'+''.join(k+'='+escaped('\n'.join(v))+'\n' for k,v in sorted(days.items()))
    output+='\n[markers]\nreport='+next_report(rows)+'\n'
    upcoming=[e for e in rows if datetime.fromisoformat(e['end'])>=now]
    output+='\n[status]\n'
    state=read_json('sync.json',{})
    status='Connect a calendar' if not settings().get('provider') else ('Changes waiting to sync' if state.get('pending') else 'Calendar synced' if state.get('ok') else 'Calendar not synced')
    if state.get('error'):status='Calendar sync needs attention'
    if errors:status+=' · some events could not be read'
    output+='message='+escaped(status)+'\n'
    due=[e['title'] for e in rows if any(datetime.fromisoformat(at)<=now<datetime.fromisoformat(at)+timedelta(minutes=15) for at in e['alarms'])]
    if due:output+='alert='+escaped('Reminder · '+' · '.join(due))+'\n'
    if upcoming:
        e=upcoming[0];a=datetime.fromisoformat(e['start'])
        output+='next='+escaped(a.strftime('%d %b')+(' · All day' if e['all_day'] else a.strftime(' · %H:%M'))+' · '+e['title'])+'\n'
    write(CACHE,output)
    write(ROOT/'agenda.json',json.dumps(rows))
    return rows

def sync():
    with locked():
        if not settings().get('provider') or not (ROOT/'vdirsyncer.conf').exists():project();return False
        binary=Path(sys.executable).parent/'vdirsyncer'
        try:
            if settings().get("provider")=="google" and not (ROOT/"google-token.json").exists():
                raise RuntimeError("Google authorization is missing. Connect your calendar again.")
            result=subprocess.run([str(binary),'--config',str(ROOT/'vdirsyncer.conf'),'sync'],
                stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=180)
            write(ROOT/'sync.log',(result.stdout+result.stderr)[-20000:])
            if result.returncode:raise RuntimeError('Sync failed. Open calendar settings for details.')
            write(ROOT/'sync.json',json.dumps(dict(ok=True,pending=False,last=datetime.now(UTC).isoformat())))
        except Exception as exc:
            state=read_json('sync.json',{});state.update(ok=False,error=str(exc))
            write(ROOT/'sync.json',json.dumps(state));project();return False
        project();return True

def notify_due(now=None):
    now=now or datetime.now(zone())
    rows=read_json('agenda.json',[])
    sent=read_json('reminders.json',{})
    for e in rows:
        for at in e['alarms']:
            due=datetime.fromisoformat(at)
            key=hashlib.sha256((e['calendar']+e['uid']+e['start']+at).encode()).hexdigest()
            if key in sent or not due<=now<due+timedelta(minutes=15):continue
            # Locked surfaces show the agenda; avoid revealing details in desktop toasts while locked.
            if subprocess.run(['pgrep','-u',str(os.getuid()),'-x','simplelock'],stdout=subprocess.DEVNULL).returncode==0:continue
            r=subprocess.run(['notify-send','--app-name=Calendar','--urgency=normal','--',e['title'],
                'All day' if e['all_day'] else datetime.fromisoformat(e['start']).strftime('%H:%M')],timeout=10)
            if r.returncode==0:sent[key]=now.timestamp()
    sent={k:v for k,v in sent.items() if v>now.timestamp()-86400*35}
    write(ROOT/'reminders.json',json.dumps(sent))

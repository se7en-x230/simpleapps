#!/usr/bin/env python3
"""Persistent static or sunrise-aware wallpaper; optional smooth daylight transitions."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from zoneinfo import ZoneInfo

HOME = Path.home()
DATA_ROOT = Path(os.environ.get('XDG_DATA_HOME', HOME / '.local/share'))
CONFIG_ROOT = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config'))
DATA = Path(os.environ.get('SIMPLEWALLPAPER_DATA',DATA_ROOT / ('wallpaper' if (DATA_ROOT/'wallpaper').is_dir() else 'simplewallpaper')))
PUBLISHED = DATA_ROOT/'simplewallpaper/current'
CONFIG = Path(os.environ.get('SIMPLEWALLPAPER_CONFIG',CONFIG_ROOT / ('simplewallpaper/config.json' if (CONFIG_ROOT/'simplewallpaper/config.json').exists() or not (CONFIG_ROOT/'wallpaper/config.json').exists() else 'wallpaper/config.json')))
STATE = Path(os.environ.get('SIMPLEWALLPAPER_STATE',Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / ('wallpaper' if (DATA_ROOT/'wallpaper').is_dir() else 'simplewallpaper')))
THEMES = {'river-traveller': ('The Beginning', 'river-traveller'), 'tree-of-seasons': ('Tree of Our Seasons', 'tree-of-seasons'), 'gothic-autumn': ('Gothic Autumn', 'gothic-autumn'), 'forest': ('Forest monk', 'forest-monk-quiet'), 'sea': ('Sea monk', 'sea-monk'), 'lotus': ('Lotus monk', 'lotus-monk'), 'matrix': ('Matrix monk', 'matrix-monk'), 'journey': ('Journey · Lotus', 'journey-lotus'), 'journey-lotus': ('Journey · Lotus', 'journey-lotus'), 'journey-sea': ('Journey · Sea', 'journey-sea'), 'journey-forest': ('Journey · Forest', 'journey-forest'), 'journey-matrix': ('Journey · Matrix', 'journey-matrix')}

def theme_dir(config):
    if config.get('theme_directory'):
        path=Path(config['theme_directory']).expanduser();return path if path.is_absolute() else CONFIG.parent/path
    key = config.get('theme', 'forest')
    if key not in THEMES: raise ValueError('Unknown wallpaper theme: '+str(key))
    for root in (DATA, DATA_ROOT/'simplewallpaper', Path(__file__).resolve().parent):
        candidate = root/'themes'/THEMES[key][1]
        if candidate.is_dir():return candidate
    return DATA / 'themes' / THEMES[key][1]
DEFAULT = dict(theme='forest', mode='static', latitude=None, longitude=None, location='Not configured', timezone='auto', transition_seconds=8, portrait_follows_daylight=False)
PRESETS = {'Koh Tao': (10.0956, 99.8404), 'Berlin': (52.52, 13.405), 'Sydney': (-33.8688, 151.2093), 'Los Angeles': (34.0522, -118.2437)}


def notify(message):
    if shutil.which('notify-send'):
        try: subprocess.run(['notify-send', 'Wallpaper', message], check=False, timeout=5)
        except (OSError, subprocess.TimeoutExpired): pass


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.'+path.name)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2); stream.write('\n')
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def read_config():
    config = DEFAULT | (json.loads(CONFIG.read_text()) if CONFIG.exists() else {})
    if config['mode'] not in ('static', 'daylight'):
        raise ValueError('Wallpaper mode must be static or daylight')
    for field, limit in [('latitude', 90), ('longitude', 180)]:
        if config[field] is None:continue
        number = float(config[field])
        if not math.isfinite(number) or abs(number) > limit:
            raise ValueError('Invalid '+field)
        config[field] = number
    duration = float(config['transition_seconds'])
    if not math.isfinite(duration) or not 0 <= duration <= 120:
        raise ValueError('Fade duration must be between 0 and 120 seconds')
    if (config['latitude'] is None)!=(config['longitude'] is None):raise ValueError('Set both latitude and longitude')
    local_zone(config)
    theme_dir(config)
    return config


def local_zone(config):
    zone = config.get('timezone', 'auto')
    if zone != 'auto':
        return ZoneInfo(zone)
    # Re-read on every update, so changing the system zone needs no restart.
    env = os.environ.get('TZ', '').lstrip(':')
    if env:
        return ZoneInfo(env)
    path = Path('/etc/localtime')
    resolved = str(path.resolve())
    if '/zoneinfo/' in resolved:
        return ZoneInfo(resolved.split('/zoneinfo/', 1)[1])
    with path.open('rb') as stream:
        return ZoneInfo.from_file(stream, key='system')


@contextmanager
def locked():
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def schedule(config, now=None):
    if config['latitude'] is None or config['longitude'] is None:raise ValueError('Set your location before using daylight schedules')
    from astral import Observer
    from astral.sun import sunrise, sunset, elevation
    zone = local_zone(config)
    now = (now or datetime.now(timezone.utc)).astimezone(zone)
    observer = Observer(config['latitude'], config['longitude'])
    # Collect nearby rise/set events instead of assuming both exist on this date.
    # This also handles polar boundaries, overnight daylight and time-zone changes.
    events = []
    for offset in range(-2, 3):
        day = now.date() + timedelta(days=offset)
        for kind, function in [('rise', sunrise), ('set', sunset)]:
            try:
                event = function(observer, date=day, tzinfo=zone)
                events.append((event.timestamp(), kind, event))
            except ValueError:
                pass  # No crossing at this latitude/date.
    events.sort()
    instant = now.timestamp()
    past = [event for event in events if event[0] <= instant]
    future = [event for event in events if event[0] > instant]
    daylight = past[-1][1] == 'rise' if past else elevation(observer, now) > -0.833
    result = dict(theme=config.get('theme','forest'), now=now.isoformat(), timezone=str(zone), location=config['location'], mode=config['mode'], image='night.png', sunrise=None, sunset=None, next_change=None, slots=0)
    if not daylight:
        upcoming = next((e for e in future if e[1] == 'rise'), None)
        if upcoming:
            result['sunrise'] = result['next_change'] = upcoming[2].isoformat()
            following = next((e for e in future if e[1] == 'set' and e[0] > upcoming[0]), None)
            if following: result['sunset'] = following[2].isoformat()
        return result
    rising = next((e for e in reversed(past) if e[1] == 'rise'), None)
    setting = next((e for e in future if e[1] == 'set'), None)
    if rising and setting:
        start, end = rising[0], setting[0]
        result.update(sunrise=rising[2].isoformat(), sunset=setting[2].isoformat())
        slots = max(1, math.ceil((end-start)/3600))
        slot = min(slots-1, int((instant-start)//3600))
        index = round(11*slot/(slots-1)) if slots > 1 else 6
        following = min(start+(slot+1)*3600, end)
    else:
        # Polar daylight: maintain a gentle 24-hour cycle with no artificial night.
        start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        slots = 24; slot = min(23, int((instant-start)//3600))
        index = round(11*slot/23); following = start+(slot+1)*3600
    result.update(image=f'{6+index:02d}.png', slots=slots, next_change=datetime.fromtimestamp(following, zone).isoformat())
    return result


def command(argv, **kwargs):
    return subprocess.run(argv, capture_output=True, text=True, timeout=30, **kwargs)


def backend_query():
    return command(['awww', 'query'])


def ensure_backend():
    if backend_query().returncode == 0:
        return
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'awww.log').open('a') as log:
        child = subprocess.Popen(['awww-daemon', '--no-cache'], stdout=log, stderr=log, start_new_session=True)
    for _ in range(50):
        time.sleep(.1)
        if backend_query().returncode == 0:
            return
        if child.poll() is not None:
            break
    raise RuntimeError('Wallpaper renderer could not start; see '+str(STATE/'awww.log'))


def old_backgrounds():
    return command(['pgrep', '-u', str(os.getuid()), '-x', 'swaybg']).stdout.split()


def apply_image(image, duration=1):
    image = image.resolve(strict=True)
    old = old_backgrounds()
    if shutil.which('awww') and shutil.which('awww-daemon'):
        ensure_backend()
        # The path is supplied as a separate argument, including filenames with spaces.
        result = command(['awww', 'img', str(image), '--resize', 'crop', '--transition-type', 'fade' if duration else 'none', '--transition-duration', str(duration), '--transition-fps', '30', '--transition-bezier', '.25,.1,.25,1'])
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or 'Wallpaper renderer rejected the image')
    else:
        STATE.mkdir(parents=True, exist_ok=True)
        with (STATE/'swaybg.log').open('w') as log:
            child = subprocess.Popen(['swaybg', '-i', str(image), '-m', 'fill'], stdout=log, stderr=log, start_new_session=True)
        time.sleep(.4)
        if child.poll() is not None:
            raise RuntimeError('Could not display wallpaper')
    for pid in old:
        try: os.kill(int(pid), 15)
        except ProcessLookupError: pass


def require_daylight(config):
    if config['latitude'] is None or config['longitude'] is None:raise ValueError('Set your location before enabling daylight mode')
    theme = theme_dir(config)
    import astral  # A missing dependency produces a clear error before changing mode.
    if not shutil.which('awww') or not shutil.which('awww-daemon'):
        raise RuntimeError('Install awww and python-astral to use daylight mode')
    for name in [f'{i:02d}.png' for i in range(6,18)]+['night.png']:
        if not (theme/name).is_file(): raise ValueError('Missing wallpaper: '+str(theme/name))


def apply_daylight(config, force=False):
    state = schedule(config)
    image = (theme_dir(config)/state['image']).resolve()
    if not image.is_file(): raise ValueError('Missing scheduled portrait: '+str(image))
    link = DATA/'daylight-current.png'
    if not link.is_symlink() or os.readlink(link) != str(image):
        temporary = DATA/('.daylight-current-'+str(os.getpid()))
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(image)
        os.replace(temporary,link)
    if config['mode'] == 'daylight':
        query = backend_query()
        lines = query.stdout.strip().splitlines()
        if force or query.returncode or not lines or not all(str(image) in line for line in lines):
            apply_image(image, config['transition_seconds'])
    if config['mode']=='daylight':publish(image)
    atomic_json(STATE/'status.json', state)
    return state


def start_worker():
    # Reuse an existing service when present; no Newinit installation/import needed.
    names=[key for key in ('WAYLAND_DISPLAY','DISPLAY','DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR','XDG_CURRENT_DESKTOP') if key in os.environ]
    init=Path('/proc/1/comm').read_text().strip()
    if init=='dinit' and (CONFIG_ROOT/'dinit.d/wallpaper').is_file() and shutil.which('dinitctl'):
        if names:subprocess.run(['dinitctl','--user','setenv',*names],check=True,timeout=10)
        subprocess.run(['dinitctl','--user','stop','wallpaper'],check=True,timeout=15)
        subprocess.run(['dinitctl','--user','start','wallpaper'],check=True,timeout=15);return
    if (CONFIG_ROOT/'systemd/user/wallpaper.service').is_file() and shutil.which('systemctl'):
        if names:subprocess.run(['systemctl','--user','import-environment',*names],check=True,timeout=10)
        subprocess.run(['systemctl','--user','restart','wallpaper.service'],check=True,timeout=15);return
    # The worker takes a process lock, so repeated launches are harmless.
    subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)


def publish(image):
    PUBLISHED.parent.mkdir(parents=True,exist_ok=True)
    temporary=PUBLISHED.with_name('.current-'+str(os.getpid()))
    try:
        temporary.unlink(missing_ok=True);temporary.symlink_to(image.resolve());os.replace(temporary,PUBLISHED)
    finally:temporary.unlink(missing_ok=True)


def worker_log(message):
    print(datetime.now().astimezone().isoformat(), 'pid='+str(os.getpid()), message, flush=True)


def supervised_worker():
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE/'worker.log').open('a', buffering=1) as log:
        os.dup2(log.fileno(), 1); os.dup2(log.fileno(), 2)
        def stopped(signum, frame):
            worker_log('stopping: '+signal.Signals(signum).name)
            raise SystemExit(0)
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP): signal.signal(sig, stopped)
        worker_log('started')
        try: worker()
        finally: worker_log('worker exited')


def worker():
    display=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/os.environ.get('WAYLAND_DISPLAY','wayland-0')
    try:session=display.stat();identity=(session.st_dev,session.st_ino)
    except OSError:raise RuntimeError('Wayland display unavailable') from None
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE/'worker.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            worker_log('another worker already holds the lock'); return
        failures = 0
        while True:
            try:
                session=display.stat()
                if (session.st_dev,session.st_ino)!=identity:return
            except OSError:return
            try:
                with locked():
                    config = read_config()
                    if config['mode'] != 'daylight' and not config['portrait_follows_daylight']:
                        state = {'next_change': None}
                    else: state = apply_daylight(config)
                failures = 0
                next_time = datetime.fromisoformat(state['next_change']).timestamp() if state['next_change'] else time.time()+30
                delay = max(1, min(30, next_time-time.time()))
            except Exception as error:
                print(datetime.now().isoformat(), str(error), flush=True)
                failures += 1
                if failures == 1: notify('Daylight wallpaper: '+str(error))
                # On compositor logout the connection vanishes; next login restores mode.
                socket = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / os.environ.get('WAYLAND_DISPLAY', 'wayland-0')
                if not socket.exists(): worker_log('waiting for desktop display connection')
                delay = 30
            time.sleep(delay)


def enable(theme=None,directory=None):
    with locked():
        config = read_config(); config['mode'] = 'daylight'
        if theme is not None:config['theme']=theme;config.pop('theme_directory',None)
        if directory is not None:config['theme_directory']=str(Path(directory).expanduser().resolve())
        require_daylight(config)
        state = apply_daylight(config, True)
        atomic_json(CONFIG, config)
    start_worker()
    notify(theme_label(config)+' · '+config['location']+' · '+state['image'].removesuffix('.png'))


def static(source=None, restore=False):
    with locked():
        current = DATA/'current.png'; candidate = None
        if not source and not current.is_file():
            roots=[DATA_ROOT/'simple/images',Path(__file__).resolve().parent.parent/'simple-common/assets/images']
            source=next((p/'default-idle.png' for p in roots if (p/'default-idle.png').is_file()),None)
        try:
            if source:
                source = Path(source).expanduser().resolve(strict=True)
                if not source.is_file(): raise ValueError('Choose an image file')
                fd, name = tempfile.mkstemp(suffix='.png', dir=DATA); os.close(fd); candidate = Path(name)
                result = command(['magick', str(source)+'[0]', '-auto-orient', 'PNG:'+str(candidate)])
                if result.returncode: raise ValueError(result.stderr.strip() or 'Not a readable image')
            image = candidate or current
            if not image.is_file(): raise ValueError('No saved wallpaper; pass an image path to simplewallpaper')
            apply_image(image, 1)
            if candidate:
                candidate.replace(current)
                # Update renderer cache to the permanent path rather than the temporary file.
                apply_image(current, 0)
            config = read_config(); config['mode'] = 'static'; atomic_json(CONFIG, config);publish(current)
            if not restore: notify('Static wallpaper · '+(source.name if source else 'saved image'))
        finally:
            if candidate: candidate.unlink(missing_ok=True)
    if config['portrait_follows_daylight'] and theme_dir(config).is_dir(): start_worker()


def choose(title, options=None):
    if shutil.which('simplepicker') and (os.environ.get('WAYLAND_DISPLAY') or os.environ.get('DISPLAY')):
        argv=['simplepicker','-d','-p',title]
        if options is None:argv.insert(1,'-I')
        result=subprocess.run(argv,input='\n'.join(options or []),capture_output=True,text=True)
        return result.stdout.strip() if not result.returncode else ''
    if not sys.stdin.isatty():raise RuntimeError('Use simplewallpaper from a terminal, or install Simplepicker for the graphical menu')
    print('\n'+title)
    if options:
        for index,option in enumerate(options,1):print(f'{index}. {option}')
        choice=input('Choose a number (Enter cancels): ').strip()
        return options[int(choice)-1] if choice.isdigit() and 1<=int(choice)<=len(options) else ''
    return input('Value (Enter cancels): ').strip()


def set_location(lat, lon, name, zone='auto'):
    if not math.isfinite(lat) or not math.isfinite(lon) or abs(lat)>90 or abs(lon)>180:
        raise ValueError('Latitude must be -90…90; longitude -180…180')
    local_zone({'timezone':zone})
    with locked():
        config = read_config(); config.update(latitude=lat, longitude=lon, location=name, timezone=zone)
        atomic_json(CONFIG, config)
    if config['mode']=='daylight' or config['portrait_follows_daylight']: start_worker()


def theme_label(config):
    return Path(config['theme_directory']).name if config.get('theme_directory') else THEMES[config['theme']][0]


def menu():
    if not shutil.which('simplepicker') and not sys.stdin.isatty():
        if not shutil.which('simple-open'):raise RuntimeError('Run simplewallpaper in a terminal, or install the optional Simplepicker menu')
        subprocess.run(['simple-open','terminal',sys.executable,str(Path(__file__).resolve()),'--menu'],check=True);return
    config=read_config()
    choices=['Choose image file']
    choices+=['Static · saved wallpaper','Daylight · image folder']
    for key,label in [('matrix','Matrix monk'),('river-traveller','The Beginning'),('lotus','Lotus monk'),('gothic-autumn','Gothic Autumn'),('forest','Forest monk'),('tree-of-seasons','Tree of Our Seasons'),('sea','Sea monk')]:
        if theme_dir({'theme':key}).is_dir():choices.append('Daylight · '+label)
    if any(theme_dir({'theme':key}).is_dir() for key in ('journey-lotus','journey-sea','journey-forest','journey-matrix')):choices.append('Daylight · Journey')
    choices+=['Location · '+config['location'],'Fade duration','Today’s schedule']
    action=choose('Simplewallpaper · '+config['mode'],choices)
    if action=='Choose image file':
        image=choose('Image file path')
        if image:static(image)
    elif action=='Daylight · image folder':
        directory=choose('Image folder: 06.png–17.png and night.png')
        if directory:enable(directory=directory)
    elif action=='Daylight · The Beginning': enable('river-traveller')
    elif action=='Daylight · Gothic Autumn': enable('gothic-autumn')
    elif action=='Daylight · Tree of Our Seasons': enable('tree-of-seasons')
    elif action=='Daylight · Forest monk': enable('forest')
    elif action=='Daylight · Sea monk': enable('sea')
    elif action=='Daylight · Lotus monk': enable('lotus')
    elif action=='Daylight · Matrix monk': enable('matrix')
    elif action=='Daylight · Journey':
        options={'Lotus · dawn to awakening': 'journey-lotus', 'Sea · dawn to awakening': 'journey-sea', 'Forest · dawn to awakening': 'journey-forest', 'Matrix · dawn to awakening': 'journey-matrix'}
        selection=choose('Choose a journey',list(options))
        if selection in options: enable(options[selection])
    elif action=='Static · saved wallpaper': static()
    elif action.startswith('Location ·'):
        place=choose('Sunrise location', list(PRESETS)+['Custom coordinates'])
        if place in PRESETS: set_location(*PRESETS[place],place)
        elif place=='Custom coordinates':
            answer=choose('Latitude longitude (example: 10.0956 99.8404)')
            if answer:
                lat,lon=map(float,answer.replace(',',' ').split());set_location(lat,lon,'Custom location')
    elif action=='Fade duration':
        value=choose('Fade between images', ['No fade','3 seconds','8 seconds','15 seconds','30 seconds'])
        if value:
            with locked():
                config=read_config();config['transition_seconds']=0 if value=='No fade' else int(value.split()[0]);atomic_json(CONFIG,config)
    elif action=='Today’s schedule':
        status=schedule(config)
        def clock(value): return datetime.fromisoformat(value).strftime('%H:%M') if value else 'No crossing today'
        notify(f"{config['location']} · {status['timezone']}\nSunrise {clock(status['sunrise'])} · Sunset {clock(status['sunset'])}\nCurrent: {status['image']} · next {clock(status['next_change'])}")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_mutually_exclusive_group()
    for name in ('restore','daylight','static','menu','status','worker'): actions.add_argument('--'+name,action='store_true')
    actions.add_argument('--location',nargs=2,type=float,metavar=('LAT','LON'))
    parser.add_argument('--name',default='Custom location');parser.add_argument('--timezone',default='auto')
    parser.add_argument('--theme',choices=THEMES,help='Choose a daylight theme (also enables daylight mode)')
    parser.add_argument('--theme-directory',help='Daylight image folder containing 06.png through 17.png and night.png')
    parser.add_argument('--at',help='ISO time for a read-only --status preview; include UTC offset')
    parser.add_argument('images',nargs='*');args=parser.parse_args()
    if args.worker: supervised_worker()
    elif args.status:
        now=datetime.fromisoformat(args.at) if args.at else None
        if now and now.tzinfo is None: raise ValueError('--at needs a timezone offset')
        config=read_config()
        print(json.dumps(schedule(config,now) if config['mode']=='daylight' else dict(mode='static',image=str(DATA/'current.png'),location=config['location']),indent=2))
    elif args.location: set_location(*args.location,args.name,args.timezone)
    elif args.menu: menu()
    elif args.daylight or args.theme or args.theme_directory: enable(args.theme,args.theme_directory)
    elif args.static: static()
    elif args.restore:
        if read_config()['mode']=='daylight':
            require_daylight(read_config())
            with locked(): apply_daylight(read_config(),True)
            start_worker()
        else: static(restore=True)
    elif args.images: static(args.images[0])
    else: menu()


if __name__=='__main__':
    try: main()
    except (OSError,ValueError,RuntimeError,ImportError,subprocess.SubprocessError) as error:
        print('Wallpaper:',error,file=sys.stderr);notify(str(error));sys.exit(1)

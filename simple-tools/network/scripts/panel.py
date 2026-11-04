#!/usr/bin/env python3
"""On-demand Simplepicker network UI. NetworkManager and BlueZ own connections."""
import os as _path_os, sys as _path_sys
from pathlib import Path as _Path
_roots=[_Path(__file__).resolve().parents[3],_Path(_path_os.environ.get('XDG_DATA_HOME',_Path.home()/'.local/share')),_Path.home()/'.local/src']
if _path_os.environ.get('SIMPLE_SOURCE_ROOT'):_roots.insert(0,_Path(_path_os.environ['SIMPLE_SOURCE_ROOT']))
for _root in reversed(_roots):
    for _name in ('simplepicker/python','simple-common'):
        if (_root/_name).is_dir():_path_sys.path.insert(0,str(_root/_name))
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tomllib

HOME = Path.home()
HERE = Path(__file__).resolve().parent
from ui import show_menu as native_show_menu
import re
import tempfile
import settings
CONFIG = Path(os.environ.get('SIMPLEPICKER_NETWORK_CONFIG', Path(os.environ.get('XDG_CONFIG_HOME', HOME/'.config'))/'simplepicker/network/config.toml'))
PREFS = tomllib.loads(CONFIG.read_text()) if CONFIG.exists() else {}
UI = PREFS.get('ui', {})
THEME = os.environ.get('SIMPLEPICKER_THEME') or str(CONFIG.parent/'style.css')
if not Path(THEME).is_file(): THEME = None
ICONS = {'wifi': 'network-wireless-symbolic', 'bt': 'bluetooth-symbolic'}


def show_menu(search, **kwargs):
    # Use the same floating window mode as the music menus.
    original = settings.path()
    text = original.read_text() if original.is_file() else ''
    match = re.search(r'(?ms)^\[ui\]\s*\n(.*?)(?=^\[|\Z)', text)
    if match:
        section = match.group(1)
        section = re.sub(r'(?m)^layer_shell\s*=.*$', 'layer_shell = "off"', section) if re.search(r'(?m)^layer_shell\s*=', section) else 'layer_shell = "off"\n' + section
        text = text[:match.start(1)] + section + text[match.end(1):]
    else:
        text += '\n[ui]\nlayer_shell = "off"\n'
    with tempfile.NamedTemporaryFile(mode='w', prefix='.network-window-', suffix='.toml', dir=original.parent) as temporary:
        temporary.write(text)
        temporary.flush()
        snapshot = Path(temporary.name)
        # settings.path may have an explicit override; temporarily select the snapshot.
        previous_settings_path = settings._path
        settings._path = snapshot
        try:
            return native_show_menu(search, **kwargs)
        finally:
            settings._path = previous_settings_path


def notify(message):
    subprocess.run(['notify-send', '-a', 'Simplepicker network', 'Network and Bluetooth', str(message)], check=False)


def backend(mode, action='--status', *args):
    command = [sys.executable, str(HERE/('bluetooth_backend.py' if mode == 'bt' else 'network_backend.py')), action, *args]
    result = subprocess.run(command, capture_output=True, text=True, timeout=110 if action == '--connect' else 40)
    if result.returncode:
        detail = result.stderr.strip()
        if not detail:
            try: detail = json.loads(result.stdout).get('error', '')
            except ValueError: pass
        raise RuntimeError(detail or 'Action failed; check the device and connection.')
    return json.loads(result.stdout) if action == '--status' else None


def choose(title, rows, *, mode='wifi', shortcuts=(), details=True):
    # Stable opaque row IDs keep names containing separators/newlines harmless.
    lookup = {str(i): row for i, row in enumerate(rows)}
    def search(query):
        words = query.casefold().split()
        return [key for key, row in lookup.items() if all(w in (row[0]+' '+row[1]).casefold() for w in words)]
    key = show_menu(search, title='Network and Bluetooth', prompt=title,
        width=int(UI.get('width', 960)) if details else 650,
        height=int(UI.get('height', 560)) if details else min(600, 180+len(rows)*74),
        labels={k:r[0] for k,r in lookup.items()}, subtitles={k:r[1] for k,r in lookup.items()},
        icons={k:r[2] for k,r in lookup.items()}, default_icon=ICONS[mode],
        icon_size=int(UI.get('icon_size', 28)), theme=THEME, shortcuts=shortcuts,
        row_shortcuts=[('c','Copy info',lambda key,q: (copy(lookup[key][3]) or {}) if key in lookup else {})] if details else [],
        text_preview=(lambda k: lookup[k][3]) if details else None)
    if key is None: return None
    if key in lookup: return lookup[key][4]
    return key


def row(label, subtitle, icon, detail, action):
    return (label, subtitle, icon, detail, action)


def copy(text):
    subprocess.run(['wl-copy'], input=text, text=True, check=True)
    notify('Information copied to clipboard.')


def device_text(mode, device, connected):
    name=device.get('name', device.get('ssid', 'Device'))
    values=[name, 'Connected' if connected else device.get('action', 'Connect'), '']
    if mode == 'bt':
        values += ['Address   '+device['mac'], 'Battery   '+(device.get('battery','?')+'%' if device.get('battery','?') != '?' else 'Not reported')]
        if device.get('profile'): values += ['Audio   '+device['profile']]
    else:
        values += ['Interface   '+device['iface'], 'Security   '+device.get('security','Unknown')]
        if device.get('kind') != 'ethernet': values += ['Signal   '+str(device.get('signal', '?'))+'%']
        if device.get('freq'): values += [('Link speed   ' if device.get('kind') == 'ethernet' else 'Frequency   ')+device['freq']]
        if device.get('ip'): values += ['IP address   '+device['ip']]
    return '\n'.join(values)


def rows_for(mode, status):
    rows=[]
    connected = status.get('connected', []) if mode == 'bt' else ([status['connected']] if status.get('connected') else [])
    if mode == 'wifi':
        connected += [d for d in status.get('wired', []) if not any(c['iface'] == d['iface'] for c in connected)]
    for active, devices in [(True, connected), (False, status.get('devices' if mode == 'bt' else 'networks', []))]:
        for d in devices:
            icon = 'network-wired-symbolic' if d.get('kind') == 'ethernet' else ICONS[mode]
            if mode == 'bt' and d.get('profile'): icon='audio-headphones-symbolic'
            detail=device_text(mode,d,active)
            subtitle='Connected' if active else d.get('action','Connect')
            subtitle += ' · '+ (d.get('profile') or d['mac']) if mode == 'bt' else ' · '+(d.get('ip') or str(d.get('signal',0))+'% · '+d.get('security',''))
            rows.append(row(d.get('name',d.get('ssid','Device')), subtitle, icon, detail+'\n\nEnter: device actions\nCtrl+C: copy details', ('device',d,active)))
    if not rows:
        rows.append(row('No connected or available devices',status.get('error') or 'Scan to discover devices',ICONS[mode],status.get('error') or 'Use Scan to find nearby devices.','scan'))
    power=status.get('power','off')
    rows += [row('Scan for devices' if mode=='bt' else 'Scan for Wi-Fi','Discover nearby devices' if mode=='bt' else 'Refresh available networks','view-refresh-symbolic','Scan runs only when requested.\n\nBluetooth discovery lasts eight seconds.','scan'),
             row('Bluetooth '+power if mode=='bt' else 'Wi-Fi '+power,'Enter to turn '+('off' if power=='on' else 'on'),'system-shutdown-symbolic','Toggle this radio.\n\nWi-Fi power does not affect wired Ethernet.','power')]
    if mode=='bt': rows.append(row('Repair Bluetooth audio','Reconnect speaker and restore preferred output','audio-speakers-symbolic','Run your existing Bluetooth audio repair.','repair'))
    else: rows.append(row('Internet information','Public IP · location · provider · latency','network-workgroup-symbolic','Check internet connectivity and public-IP information on demand.','internet'))
    rows += [row('Device settings' if mode=='bt' else 'Advanced settings','Simpleblue' if mode=='bt' else 'nmtui','preferences-system-symbolic','Full settings, saved connections and additional device options.','advanced'),
             row('Network' if mode=='bt' else 'Bluetooth','Switch panel',ICONS['wifi' if mode=='bt' else 'bt'],'Switch between Network and Bluetooth.','switch')]
    if mode=='bt':
        rows.insert(0, row('Sound', 'Outputs, microphones and application volume', 'audio-volume-high-symbolic',
                           'Open Sound controls.\n\nChoose an audio output, adjust volume or change a device profile.', 'sound'))
    return rows


def device_menu(mode,d,active):
    text=device_text(mode,d,active)
    action='disconnect' if active else 'connect'
    while True:
        result=choose(d.get('name',d.get('ssid','Device')),[
            row(action.capitalize() if active else d.get('action','Connect'),text.split('\n')[1],ICONS[mode],text,action),
            row('Copy information','Copy device details to clipboard','edit-copy-symbolic',text,'copy'),
            row('Back','Return to devices','go-previous-symbolic',text,'back')],mode=mode,
            shortcuts=[('h','Back','back')])
        if result in (None,'back'): return
        if result=='copy': copy(text); continue
        if result=='connect' and mode=='wifi':
            backend(mode,'--connect',d['ssid'],d['iface'])
        else: backend(mode,'--'+result,d['mac'] if mode=='bt' else d['iface'])
        return


def internet():
    notify('Checking internet connection…')
    result=subprocess.run([sys.executable,str(HERE/'internet_status.py')],capture_output=True,text=True,check=True,timeout=22)
    data=json.loads(result.stdout)
    text='\n'.join(f'{label}   {data.get(key,"Unavailable")}' for key,label in [('state','Internet'),('ip','Public IP'),('location','Location'),('isp','Provider'),('ping','Latency'),('pingTarget','Ping target')])
    while True:
        result=choose('Internet information',[row(label,str(data.get(key,'Unavailable')),'network-workgroup-symbolic',text,('copy',str(data.get(key,'Unavailable')))) for key,label in [('state','Internet'),('ip','Public IP'),('location','Location'),('isp','Provider'),('ping','Latency')]]+[row('Copy all information','Enter to copy','edit-copy-symbolic',text,('copy',text)),row('Back','Return to network','go-previous-symbolic',text,'back')],shortcuts=[('h','Back','back')])
        if result in (None,'back'): return
        copy(result[1])


def prompt(message, confirm):
    if confirm:
        result=choose(message,[row('Confirm pairing',message,'bluetooth-symbolic',message,'yes'),row('Cancel','Reject pairing','window-close-symbolic',message,'no')],mode='bt',details=False)
        return 0 if result=='yes' else 1
    result=show_menu(lambda q:[],title='Bluetooth pairing',prompt=message,input_only=True,width=650,height=200,theme=THEME,default_icon=ICONS['bt'])
    if not result: return 1
    print(result)
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['wifi','bt'],nargs='?',default='wifi')
    parser.add_argument('--pair-prompt');parser.add_argument('--confirm',action='store_true')
    args=parser.parse_args()
    if args.pair_prompt: return prompt(args.pair_prompt,args.confirm)
    state=Path(os.environ.get('XDG_RUNTIME_DIR', HOME/'.cache'))/'simplepicker-network'
    state.mkdir(parents=True,exist_ok=True)
    lock=(state/'menu.lock').open('w')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: return 0
    mode=args.mode
    shortcuts=[('n','Network','wifi'),('b','Bluetooth','bt'),('r','Refresh','refresh'),('s','Scan','scan'),('a','Advanced','advanced'),('h','Back','back')]
    while True:
        try: status=backend(mode)
        except Exception as error: status={'error':str(error),'power':'unknown'}
        rows=rows_for(mode,status)
        result=choose('Bluetooth' if mode=='bt' else 'Network',rows,mode=mode,shortcuts=[s for s in shortcuts if s[2] != mode] + ([('o','Sound','sound'),('f','Repair','repair')] if mode=='bt' else []))
        if result in (None,'back'): return 0
        try:
            if result in ('wifi','bt'): mode=result
            elif result=='switch': mode='wifi' if mode=='bt' else 'bt'
            elif result=='refresh': pass
            elif result=='sound':
                helper='simple-sound'
                subprocess.Popen([str(helper)],start_new_session=True)
                return 0
            elif result=='scan':
                notify('Scanning for Bluetooth devices…' if mode=='bt' else 'Scanning for Wi-Fi…')
                backend(mode,'--scan')
            elif result=='power': backend(mode,'--toggle')
            elif result=='advanced':
                subprocess.Popen(['simple-network-advanced',mode],start_new_session=True)
                return 0
            elif result=='repair':
                repaired=subprocess.run([str('bluetooth-audio-repair')],capture_output=True,text=True,timeout=100)
                if repaired.returncode:
                    detail=next((line for line in reversed(repaired.stdout.splitlines()) if line.startswith('Repair failed:')),None)
                    raise RuntimeError(detail or repaired.stderr.strip() or 'Bluetooth repair failed without an explanation.')
            elif result=='internet': internet()
            elif isinstance(result,tuple) and result[0]=='device': device_menu(mode,*result[1:])
        except Exception as error:
            notify(str(error))

if __name__=='__main__':
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))
    try: raise SystemExit(main())
    except Exception as error:
        notify(str(error)); raise SystemExit(1)

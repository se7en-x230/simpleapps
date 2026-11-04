#!/usr/bin/env python3
"""Controller-scoped BlueZ operations. Never silently use the internal radio."""
import os as _path_os, sys as _path_sys
from pathlib import Path as _Path
_roots=[_Path(__file__).resolve().parents[3],_Path(_path_os.environ.get('XDG_DATA_HOME',_Path.home()/'.local/share')),_Path.home()/'.local/src']
if _path_os.environ.get('SIMPLE_SOURCE_ROOT'):_roots.insert(0,_Path(_path_os.environ['SIMPLE_SOURCE_ROOT']))
for _root in reversed(_roots):
    for _name in ('simplepicker/python','simple-common'):
        if (_root/_name).is_dir():_path_sys.path.insert(0,str(_root/_name))
import json
import os
import tomllib
import socket
import time
import re
import subprocess
import sys
from pathlib import Path
import dbus
from dbus.mainloop.glib import DBusGMainLoop
import dbus.service
from gi.repository import GLib

CONFIG = Path(os.environ.get('SIMPLEPICKER_NETWORK_CONFIG', Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'simplepicker/network/config.toml'))
ADAPTER = 'org.bluez.Adapter1'
DEVICE = 'org.bluez.Device1'
PROPS = 'org.freedesktop.DBus.Properties'
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'simpleblue'/('adapter-'+socket.gethostname()+'.json')

def notify(message):
    subprocess.run(['notify-send', '-a', 'Network popup', 'Bluetooth', str(message)], check=False)

def icon(device):
    kind = str(device.get('Icon', ''))
    return '🎧' if 'head' in kind else '󰓃' if 'audio' in kind else '󰌌' if 'keyboard' in kind else '󰍽' if 'mouse' in kind else ''

def main():
    config = tomllib.loads(CONFIG.read_text()).get('bluetooth', {}) if CONFIG.exists() else {}
    config = {**config, **config.get('hosts', {}).get(socket.gethostname(), {})}
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    objects = dbus.Interface(bus.get_object('org.bluez', '/'), 'org.freedesktop.DBus.ObjectManager').GetManagedObjects()
    adapters = [(p,v[ADAPTER]) for p,v in objects.items() if ADAPTER in v]
    preferred = config.get('preferred', '').upper()
    if STATE.is_file():
        preferred = json.loads(STATE.read_text())['address'].upper()
    command = sys.argv[1]
    if command == '--select-adapter':
        address = sys.argv[2].upper()
        if not any(str(v['Address']).upper() == address for _, v in adapters):
            raise RuntimeError('Adapter unavailable; refresh and choose an available adapter.')
        STATE.parent.mkdir(parents=True, exist_ok=True)
        temporary = STATE.with_suffix('.tmp')
        temporary.write_text(json.dumps({'address': address})+'\n')
        temporary.replace(STATE)
        return
    path = next((p for p,v in adapters if str(v['Address']).upper() == preferred), None) if preferred else next((p for p,v in adapters if v.get('Powered')), adapters[0][0] if adapters else None)
    command = sys.argv[1]
    if command == '--status':
        result = dict(power='off', connected=[], devices=[], adapterPath=str(path or ''), adapterName=str(objects[path][ADAPTER].get('Alias', 'Bluetooth')) if path else 'Bluetooth', error='')
        result['adapters'] = [dict(address=str(v['Address']), name=str(v.get('Alias', 'Bluetooth')),
                                   powered=bool(v.get('Powered')), selected=p == path) for p, v in adapters]
        if path is None:
            result['error'] = 'Configured Bluetooth adapter unavailable'
        else:
            result['power'] = 'on' if objects[path][ADAPTER]['Powered'] else 'off'
            profiles = {}
            try:
                cards = json.loads(subprocess.check_output(['pactl', '--format=json', 'list', 'cards'], timeout=3, stderr=subprocess.DEVNULL))
                for card in cards:
                    active = card.get('active_profile', '')
                    profiles[card['name']] = active.get('name', '') if isinstance(active, dict) else active
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            for p, v in objects.items():
                d = v.get(DEVICE)
                if not d or d.get('Adapter') != path:
                    continue
                mac = str(d['Address'])
                profile = next((a for name,a in profiles.items() if mac.replace(':','_').lower() in name.lower()), '')
                item = dict(id=mac, mac=mac, name=str(d.get('Alias', d.get('Name', mac))), icon=icon(d),
                            battery=str(v.get('org.bluez.Battery1', {}).get('Percentage', '?')),
                            profile='Hi-Fi (A2DP)' if 'a2dp' in profile else 'Headset (HFP)' if 'headset' in profile or 'hfp' in profile else '',
                            paired=bool(d.get('Paired')), trusted=bool(d.get('Trusted')), blocked=bool(d.get('Blocked')),
                            action='Blocked' if d.get('Blocked') else 'Connect' if d.get('Paired') else 'Pair')
                result['connected' if d.get('Connected') else 'devices'].append(item)
        print(json.dumps(result))
        return
    if not path:
        raise RuntimeError('Configured Bluetooth adapter unavailable')
    if command == '--prefer-usb':
        for p,v in objects.items():
            if ADAPTER in v and str(v[ADAPTER]['Address']).upper() == config.get('internal', '').upper():
                dbus.Interface(bus.get_object('org.bluez',p), PROPS).Set(ADAPTER, 'Powered', dbus.Boolean(False))
        return
    if command == '--toggle':
        dbus.Interface(bus.get_object('org.bluez',path), PROPS).Set(ADAPTER, 'Powered', dbus.Boolean(not objects[path][ADAPTER]['Powered']))
        return
    if command == '--scan':
        adapter = dbus.Interface(bus.get_object('org.bluez', path), ADAPTER)
        adapter.StartDiscovery()
        try: time.sleep(8)
        finally: adapter.StopDiscovery()
        return
    mac = sys.argv[2].upper()
    if not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}', mac):
        raise ValueError('Invalid device address')
    dp = next((p for p,v in objects.items() if DEVICE in v and v[DEVICE].get('Adapter') == path and str(v[DEVICE]['Address']).upper() == mac), None)
    if not dp:
        raise RuntimeError('Device not found on the selected adapter. Scan again with the device in pairing mode.')
    device = dbus.Interface(bus.get_object('org.bluez',dp), DEVICE)
    if command == '--forget':
        dbus.Interface(bus.get_object('org.bluez', path), ADAPTER).RemoveDevice(dp, timeout=20)
    elif command in ('--trust', '--untrust', '--block', '--unblock'):
        prop = 'Trusted' if command in ('--trust', '--untrust') else 'Blocked'
        value = command in ('--trust', '--block')
        dbus.Interface(bus.get_object('org.bluez', dp), PROPS).Set(DEVICE, prop, dbus.Boolean(value))
    elif command == '--disconnect':
        device.Disconnect(timeout=20)
    elif command == '--connect':
        if objects[dp][DEVICE].get('Blocked'):
            raise RuntimeError('Unblock this device before connecting.')
        if not objects[dp][DEVICE].get('Paired'):
            pair(bus, device, objects[dp][DEVICE].get('Alias', mac))
            dbus.Interface(bus.get_object('org.bluez',dp), PROPS).Set(DEVICE, 'Trusted', dbus.Boolean(True))
        device.Connect(timeout=25)
    else:
        raise ValueError('Unknown action')

class Rejected(dbus.DBusException):
    _dbus_error_name = 'org.bluez.Error.Rejected'

class Agent(dbus.service.Object):
    def __init__(self, bus, name):
        super().__init__(bus, '/network_popup_agent')
        self.name = str(name)
        self.prompt = None
    def dialog(self, *args):
        message = args[args.index('--text')+1]
        command = [sys.executable, str(Path(__file__).resolve().parent/'connectivity.py'), '--pair-prompt', message]
        if '--question' in args: command.append('--confirm')
        self.prompt = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
        try: value, _ = self.prompt.communicate(timeout=75)
        except subprocess.TimeoutExpired:
            self.prompt.terminate(); self.prompt.communicate()
            raise Rejected('Pairing prompt timed out')
        if self.prompt.returncode != 0: raise Rejected('Pairing cancelled')
        return value.strip()
    @dbus.service.method('org.bluez.Agent1', in_signature='ou', out_signature='')
    def RequestConfirmation(self, device, passkey):
        self.dialog('--question', '--text', f'Pair with {self.name}?\nConfirm that both devices show {passkey:06d}.')
    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='s')
    def RequestPinCode(self, device):
        return self.dialog('--entry', '--text', f'Enter the PIN for {self.name}')
    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='u')
    def RequestPasskey(self, device):
        value = self.dialog('--entry', '--text', f'Enter the six-digit passkey for {self.name}')
        if not value.isdigit() or len(value)>6: raise Rejected('Invalid passkey')
        return dbus.UInt32(value)
    @dbus.service.method('org.bluez.Agent1', in_signature='os', out_signature='')
    def DisplayPinCode(self, device, pin):
        notify(f'Enter PIN {pin} on {self.name}.')
    @dbus.service.method('org.bluez.Agent1', in_signature='ouq', out_signature='')
    def DisplayPasskey(self, device, passkey, entered):
        if entered == 0: notify(f'Enter {passkey:06d} on {self.name}, then press Enter.')
    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='')
    def RequestAuthorization(self, device):
        self.dialog('--question', '--text', f'Allow pairing with {self.name}?')
    @dbus.service.method('org.bluez.Agent1', in_signature='os', out_signature='')
    def AuthorizeService(self, device, uuid):
        self.dialog('--question', '--text', f'Allow {self.name} to connect?')
    @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
    def Cancel(self):
        if self.prompt and self.prompt.poll() is None: self.prompt.terminate()
    @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
    def Release(self):
        self.Cancel()

def pair(bus, device, name):
    agent = Agent(bus, name)
    manager = dbus.Interface(bus.get_object('org.bluez','/org/bluez'), 'org.bluez.AgentManager1')
    manager.RegisterAgent('/network_popup_agent', 'KeyboardDisplay')
    loop = GLib.MainLoop()
    errors = []
    def done(): loop.quit()
    def failed(error): errors.append(error);loop.quit()
    try:
        device.Pair(reply_handler=done, error_handler=failed, timeout=90)
        loop.run()
        if errors: raise errors[0]
    finally:
        agent.Cancel()
        manager.UnregisterAgent('/network_popup_agent')

if __name__ == '__main__':
    try: main()
    except Exception as error:
        if len(sys.argv)>1 and sys.argv[1]=='--status':
            print(json.dumps(dict(power='off',connected=[],devices=[],adapterPath='',error=str(error))))
        else: notify(str(error))
        print(error, file=sys.stderr)
        sys.exit(1)

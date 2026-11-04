#!/usr/bin/env python3
"""NetworkManager status and explicit user actions; never rescan during polling."""
import os as _path_os, sys as _path_sys
from pathlib import Path as _Path
_roots=[_Path(__file__).resolve().parents[3],_Path(_path_os.environ.get('XDG_DATA_HOME',_Path.home()/'.local/share')),_Path.home()/'.local/src']
if _path_os.environ.get('SIMPLE_SOURCE_ROOT'):_roots.insert(0,_Path(_path_os.environ['SIMPLE_SOURCE_ROOT']))
for _root in reversed(_roots):
    for _name in ('simplepicker/python','simple-common'):
        if (_root/_name).is_dir():_path_sys.path.insert(0,str(_root/_name))
import json
import subprocess
import sys
import gi
gi.require_version('NM', '1.0')
from gi.repository import NM

def run(*args):
    return subprocess.run(['nmcli', '--wait', '25', *args], capture_output=True, text=True, timeout=30)

def ssid(ap):
    value = ap.get_ssid()
    return bytes(value.get_data()).decode('utf-8', 'replace') if value else ''

def address(device):
    config=device.get_ip4_config()
    return ', '.join(a.get_address() for a in config.get_addresses()) if config else 'No IP'

def network(ap, device):
    name=ssid(ap)
    security='WPA/RSN' if ap.get_rsn_flags() or ap.get_wpa_flags() else 'WEP' if ap.get_flags() & getattr(NM, '80211ApFlags').PRIVACY else 'Open'
    return dict(id=device.get_iface()+'|'+name,ssid=name,name=name,icon='󰤨',signal=int(ap.get_strength()),security=security,
                iface=device.get_iface(),kind='wifi',freq=f'{ap.get_frequency()} MHz',action='Connect')

def main():
    command=sys.argv[1] if len(sys.argv)>1 else '--status'
    if command=='--connect':
        subprocess.Popen(['simple-open','terminal','python3',__file__,'--connect-terminal',sys.argv[2],sys.argv[3]], start_new_session=True)
        return
    if command=='--connect-terminal':
        result=subprocess.run(['nmcli','--ask','--wait','60','device','wifi','connect',sys.argv[2],'ifname',sys.argv[3]])
        if result.returncode:
            subprocess.run(['notify-send','Wi-Fi connection failed','Check the password and network availability.'])
            input('Press Enter to close… ')
        return
    client=NM.Client.new(None)
    devices=client.get_devices()
    wifi=[d for d in devices if d.get_device_type()==NM.DeviceType.WIFI]
    if command=='--status':
        active=None; wired=[]; networks={}
        for device in devices:
            if device.get_device_type()==NM.DeviceType.ETHERNET and device.get_state()==NM.DeviceState.ACTIVATED:
                wired.append(dict(id='Ethernet · '+device.get_iface(),ssid='Ethernet · '+device.get_iface(),name='Ethernet',
                    icon='󰈀',signal=100,security='Wired',ip=address(device),freq=f'{device.get_speed()} Mbps',iface=device.get_iface(),kind='ethernet'))
        for device in wifi:
            ap_active=device.get_active_access_point()
            for ap in device.get_access_points():
                item=network(ap,device)
                if not item['ssid']: continue
                if ap_active and ap.get_path()==ap_active.get_path():
                    item['ip']=address(device);active=item
                previous=networks.get(item['id'])
                if not previous or item['signal']>previous['signal']: networks[item['id']]=item
        if active: networks.pop(active['id'],None)
        print(json.dumps(dict(power='on' if client.wireless_get_enabled() else 'off',connected=active or (wired[0] if wired else None),
            networks=sorted(networks.values(),key=lambda x:-x['signal']),wifiAvailable=bool(wifi),wired=wired)))
        return
    if command=='--toggle': result=run('radio','wifi','off' if client.wireless_get_enabled() else 'on')
    elif command=='--scan': result=run('device','wifi','rescan')
    elif command=='--disconnect': result=run('device','disconnect',sys.argv[2])
    else: raise ValueError('Unknown command')
    if result.returncode: raise RuntimeError(result.stderr.strip() or 'NetworkManager action failed')

if __name__=='__main__':
    try: main()
    except Exception as error:
        if len(sys.argv)<2 or sys.argv[1]=='--status':
            print(json.dumps(dict(power='off',connected=None,networks=[],error=str(error))))
        else: subprocess.run(['notify-send','Network action failed',str(error)])
        sys.exit(1)

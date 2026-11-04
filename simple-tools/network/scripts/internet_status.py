#!/usr/bin/env python3
"""Bounded internet diagnostics, independent of NetworkManager polling."""
import os as _path_os, sys as _path_sys
from pathlib import Path as _Path
_roots=[_Path(__file__).resolve().parents[3],_Path(_path_os.environ.get('XDG_DATA_HOME',_Path.home()/'.local/share')),_Path.home()/'.local/src']
if _path_os.environ.get('SIMPLE_SOURCE_ROOT'):_roots.insert(0,_Path(_path_os.environ['SIMPLE_SOURCE_ROOT']))
for _root in reversed(_roots):
    for _name in ('simplepicker/python','simple-common'):
        if (_root/_name).is_dir():_path_sys.path.insert(0,str(_root/_name))
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import json
import os
import re
import subprocess


def run(args, timeout=9):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, 'LC_ALL': 'C'}).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ''


def fetch(url, *extra):
    return run(['curl', '--silent', '--fail', '--noproxy', '*',
                '--connect-timeout', '3', '--max-time', '7', *extra, url])


def ping():
    output = run(['ping', '-n', '-c', '2', '-W', '2', '-w', '5', '1.1.1.1'], 6)
    match = re.search(r'= [\d.]+/([\d.]+)/', output)
    return round(float(match.group(1)), 1) if match else None


def location():
    try:
        data = json.loads(fetch('https://ipwho.is/'))
        if data.get('success') is True:
            ip = str(ipaddress.ip_address(data['ip']))
            place = ', '.join(dict.fromkeys(str(data[k]) for k in ('city', 'country') if data.get(k)))
            return {'ip': ip, 'location': place or 'Unavailable',
                    'isp': str((data.get('connection') or {}).get('isp') or '')}
    except (ValueError, KeyError, TypeError):
        pass
    try:
        ip = str(ipaddress.ip_address(fetch('https://api.ipify.org')))
        return {'ip': ip, 'location': 'Unavailable', 'isp': ''}
    except ValueError:
        return {'ip': 'Unavailable', 'location': 'Unavailable', 'isp': ''}


def status():
    with ThreadPoolExecutor(max_workers=3) as pool:
        latency = pool.submit(ping)
        https = pool.submit(fetch, 'https://www.gstatic.com/generate_204',
                            '--output', '/dev/null', '--write-out', '%{http_code}')
        geo = pool.submit(location)
        ms, code, details = latency.result(), https.result(), geo.result()
    # ICMP can be blocked on a working connection. A public-IP lookup also
    # proves HTTPS access when the dedicated connectivity endpoint is blocked.
    online = code == '204' or details['ip'] != 'Unavailable'
    return {**details, 'state': 'Online' if online else 'Limited' if ms is not None else 'Unreachable',
            'ping': f'{ms:g} ms' if ms is not None else 'No reply',
            'pingTarget': '1.1.1.1'}


if __name__ == '__main__':
    print(json.dumps(status()))

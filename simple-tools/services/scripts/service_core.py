"""Read service state and build explicit dinit/systemd commands, without shell evaluation."""
import os as _path_os, sys as _path_sys
from pathlib import Path as _Path
_roots=[_Path(__file__).resolve().parents[3],_Path(_path_os.environ.get('XDG_DATA_HOME',_Path.home()/'.local/share')),_Path.home()/'.local/src']
if _path_os.environ.get('SIMPLE_SOURCE_ROOT'):_roots.insert(0,_Path(_path_os.environ['SIMPLE_SOURCE_ROOT']))
for _root in reversed(_roots):
    for _name in ('simplepicker/python','simple-common'):
        if (_root/_name).is_dir():_path_sys.path.insert(0,str(_root/_name))
from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import tomllib
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

MODULE = _Path(_path_os.environ.get('XDG_CONFIG_HOME',_Path.home()/'.config'))/'simplepicker/services'
VALID_NAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.:@\\-]*\Z')


def manager():
    name = Path('/proc/1/comm').read_text().strip()
    if name not in ('dinit', 'systemd'):
        raise RuntimeError('Unsupported running service manager: ' + name + '. Expected dinit or systemd.')
    return name


def load_config():
    with (MODULE / 'config.toml').open('rb') as stream:
        config = tomllib.load(stream)
    lines = config.get('log_lines', 200)
    if type(lines) is not int or not 10 <= lines <= 2000:
        raise ValueError('log_lines must be between 10 and 2000.')
    if not isinstance(config.get('services'), list) or not config['services']:
        raise ValueError('Configure at least one [[services]] entry.')
    seen = set()
    for entry in config.get('services', []):
        if not isinstance(entry, dict):
            raise ValueError('Invalid service entry.')
        if set(entry) - {'id', 'name', 'scope', 'dinit', 'systemd', 'icon', 'web', 'impact', 'group', 'log_paths'}:
            raise ValueError('Unknown service configuration field.')
        for key in ('icon', 'web', 'impact', 'group'):
            if key in entry and not isinstance(entry[key], str):
                raise ValueError(key + ' must be text.')
        for key in ('id', 'name', 'scope', 'dinit'):
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise ValueError('Missing service field: ' + key)
        if entry['id'] in seen or not VALID_NAME.fullmatch(entry['id']):
            raise ValueError('Invalid or duplicate service ID.')
        seen.add(entry['id'])
        if entry['scope'] not in ('user', 'system') or not VALID_NAME.fullmatch(entry['dinit']):
            raise ValueError('Invalid service scope or dinit name.')
        units = entry.get('systemd')
        if not isinstance(units, list) or not units or not all(isinstance(u, str) and VALID_NAME.fullmatch(u) and u.endswith('.service') for u in units):
            raise ValueError('systemd must list valid service unit names.')
        paths = entry.get('log_paths', [])
        if not isinstance(paths, list) or not all(isinstance(p, str) and Path(p).expanduser().is_absolute() for p in paths):
            raise ValueError('log_paths must list absolute paths (or ~/paths).')
        web = entry.get('web')
        if web and web != 'syncthing' and urlsplit(web).scheme not in ('http', 'https'):
            raise ValueError('Web interfaces must use http or https.')
    return config


@dataclass
class Status:
    state: str
    unit: str
    detail: str = ''
    installed: bool = True
    accessible: bool = True


def execute(argv, *, privileged=False, auth=False, timeout=12):
    env = dict(os.environ, LC_ALL='C', SYSTEMD_COLORS='0', SYSTEMD_PAGER='cat')
    # Never inherit a user-daemon socket override for a system request.
    env.pop('DINIT_SOCKET_PATH', None)
    if privileged:
        env['SUDO_ASKPASS'] = str(Path(__file__).resolve().parent/'service-askpass')
        argv = ['sudo', '-A' if auth else '-n', '--', *argv]
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, errors='replace', timeout=timeout, env=env)
        return result.returncode, (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, 'The request timed out. Refresh status to check whether it completed.'
    except OSError as error:
        return 127, str(error)


def ctl(kind, scope):
    return [kind + 'ctl' if kind == 'dinit' else 'systemctl', '--user' if scope == 'user' else '--system']


def parse_dinit(text):
    found = {}
    for line in text.splitlines():
        match = re.match(r'^(\[.*\])\s+(\S+)(.*)$', line)
        if not match:
            continue
        indicator, name, extra = match.groups()
        state = ('Starting' if '<<' in indicator else 'Stopping' if '>>' in indicator
                 else 'Failed' if 'X' in indicator else 'Running' if '+' in indicator
                 else 'Skipped' if 's' in indicator else 'Stopped' if '-' in indicator else 'Unknown')
        found[name] = Status(state, name, extra.strip())
    return found


def properties(text):
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)


def dinit_exists(scope, name):
    paths = ([Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'dinit.d',
              Path.home() / '.dinit.d', Path('/etc/dinit.d/user')]
             if scope == 'user' else [Path('/etc/dinit.d'), Path('/usr/lib/dinit.d')])
    return any((p / name).is_file() for p in paths)


def inventory(entries, kind, auth=False):
    result = {}
    if kind == 'dinit':
        for scope in ('user', 'system'):
            group = [e for e in entries if e['scope'] == scope]
            if not group:
                continue
            argv = ctl(kind, scope) + ['list']
            code, text = execute(argv)
            if code and scope == 'system':
                code, text = execute(argv, privileged=True, auth=auth, timeout=120 if auth else 12)
            parsed = parse_dinit(text) if not code else {}
            for e in group:
                unit = e['dinit']
                exists = unit in parsed or dinit_exists(scope, unit)
                if not exists:
                    status = Status('Not installed', unit, installed=False)
                elif code:
                    status = Status('Authentication required' if scope == 'system' else 'Manager unavailable', unit, text, accessible=False)
                else:
                    status = parsed.get(unit, Status('Stopped', unit, 'Service is not currently loaded.'))
                result[e['id']] = status
        return result
    if kind != 'systemd':
        raise ValueError('Unsupported service manager.')
    for e in entries:
        candidates = []
        canonical = set()
        for unit in e['systemd']:
            code, text = execute(ctl(kind, e['scope']) + ['show', unit, '--no-pager',
                '--property=Id,LoadState,ActiveState,SubState,Result,MainPID,UnitFileState'])
            props = properties(text)
            if props.get('LoadState') == 'not-found':
                continue
            if code or not props.get('LoadState'):
                candidates.append(Status('Manager unavailable', unit, text, accessible=False))
                break
            actual_id = props.get('Id', unit)
            if actual_id in canonical:
                continue
            canonical.add(actual_id)
            active = props.get('ActiveState', 'unknown')
            state = {'active': 'Running', 'inactive': 'Stopped', 'failed': 'Failed',
                     'activating': 'Starting', 'deactivating': 'Stopping', 'reloading': 'Reloading'}.get(active, active.title())
            if props['LoadState'] == 'masked':
                state = 'Masked'
            elif props['LoadState'] != 'loaded':
                state = 'Unavailable'
            candidates.append(Status(state, unit, '\n'.join(f'{k}: {v}' for k, v in props.items())))
        active = [s for s in candidates if s.state in ('Running', 'Starting', 'Reloading', 'Stopping')]
        if len(active) > 1:
            chosen = Status('Multiple units active', active[0].unit,
                            'Check these units before controlling this service:\n' + '\n'.join(s.unit for s in active), accessible=False)
        else:
            chosen = next(iter(active), next(iter(candidates), None))
        result[e['id']] = chosen or Status('Not installed', e['systemd'][0], installed=False)
    return result


def action_command(kind, entry, status, action):
    if action not in ('start', 'stop', 'restart'):
        raise ValueError('Only start, stop and restart are supported.')
    if not status.installed or not status.accessible or status.state in ('Masked', 'Unavailable'):
        raise ValueError('Read the service status before changing it.')
    allowed = [entry['dinit']] if kind == 'dinit' else entry['systemd']
    if status.unit not in allowed:
        raise ValueError('Service unit is not in this entry’s configuration.')
    return ctl(kind, entry['scope']) + [action, status.unit]


def change(kind, entry, status, action):
    argv = action_command(kind, entry, status, action)
    # No --force, --pin, enable, disable, or automatic retry of a state change.
    code, text = execute(argv, privileged=entry['scope'] == 'system', auth=True, timeout=120)
    if code:
        raise RuntimeError(text or 'Service action failed.')
    return text or 'Request completed.'


def detail(kind, entry, status):
    if not status.installed or not status.accessible:
        return status.state + '\n' + status.detail
    code, text = execute(ctl(kind, entry['scope']) + ['status', status.unit] + (['--no-pager', '--full'] if kind == 'systemd' else []),
                         privileged=kind == 'dinit' and entry['scope'] == 'system', auth=entry['scope'] == 'system', timeout=120)
    return text or status.state


def logs(kind, entry, status, lines):
    if not status.installed:
        return 'Service is not installed.'
    system = entry['scope'] == 'system'
    if kind == 'systemd':
        argv = ['journalctl'] + (['--user'] if not system else []) + ['--unit', status.unit, '--no-pager', '--lines', str(lines), '--output=short-iso']
        code, text = execute(argv, privileged=system, auth=system, timeout=120)
        if code:
            raise RuntimeError(text)
        return text or 'No journal entries.'
    reports = []
    code, text = execute(ctl(kind, entry['scope']) + ['catlog', status.unit], privileged=system, auth=system, timeout=120)
    if not code:
        reports.append('Service log buffer\n' + ('\n'.join(text.splitlines()[-lines:]) or 'The log buffer is empty.'))
    elif 'not configured to buffer' not in text and 'not loaded' not in text:
        reports.append('Service log buffer unavailable\n' + text)
    for value in entry.get('log_paths', []):
        path = str(Path(value).expanduser())
        code, text = execute(['tail', '-n', str(lines), '--', path])
        if code and system:
            code, text = execute(['tail', '-n', str(lines), '--', path], privileged=True, auth=True, timeout=120)
        reports.append(path + '\n' + (text if text else 'No entries.') + ('\nCould not read this log.' if code else ''))
    return '\n\n'.join(reports) if reports else 'No retained log is configured for this dinit service.\nThe service status may still include its last exit reason.'


def web_url(entry):
    value = entry.get('web')
    if value != 'syncthing':
        return value
    base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state'))
    for path in (state / 'syncthing/config.xml', base / 'syncthing/config.xml'):
        if not path.is_file():
            continue
        gui = ET.parse(path).getroot().find('gui')
        if gui is None or gui.get('enabled', 'true') == 'false':
            raise ValueError('The Syncthing web interface is disabled.')
        address = gui.findtext('address', '127.0.0.1:8384')
        url = urlsplit('http://' + address)
        if not url.hostname or not url.port:
            raise ValueError('Syncthing does not use a supported TCP web address.')
        host = '127.0.0.1' if url.hostname in ('0.0.0.0', '::') else url.hostname
        if ':' in host:
            host = '[' + host + ']'
        return ('https' if gui.get('tls') == 'true' else 'http') + f'://{host}:{url.port}'
    raise ValueError('No local Syncthing configuration was found.')

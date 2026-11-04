"""User configuration. Commands are argv arrays, never implicit shell code."""
import copy
import os
from pathlib import Path
import re
import tomllib

DEFAULTS = {
    'desktop': {'backend': 'auto', 'hyprland_dispatch': 'legacy'},
    'ui': {'layer_shell': 'auto'},
    'windows': {'list': [], 'current': [], 'focus': [], 'close': [], 'move': []},
    'commands': {
        'open_url': ['simple-open', 'browser', '{url}'],
        'edit_bookmarks': ['simple-open', 'terminal', 'python3', '{editor}'],
        'copy': ['wl-copy'],
        'paste': ['{wtype}', '-s', '200', '-M', 'ctrl', '-k', 'v', '-m', 'ctrl'],
        'paste_terminal': ['{wtype}', '-s', '200', '-M', 'ctrl', '-M', 'shift', '-k', 'v', '-m', 'shift', '-m', 'ctrl'],
    },
    'power': {
        'lock': {'label': 'Lock', 'key': 'e', 'enabled': True, 'icon': '', 'command': ['swaylock', '-f', '-c', '000000']},
        'logout': {'label': 'Logout', 'key': 'l', 'enabled': True, 'icon': '', 'command': []},
        'suspend': {'label': 'Suspend', 'key': 'u', 'enabled': True, 'icon': '', 'command': ['loginctl', 'suspend']},
        'shutdown': {'label': 'Shutdown', 'key': 's', 'enabled': True, 'icon': '', 'command': ['loginctl', 'poweroff']},
        'hibernate': {'label': 'Hibernate', 'key': 'h', 'enabled': True, 'icon': '', 'command': ['loginctl', 'hibernate']},
        'reboot': {'label': 'Reboot', 'key': 'r', 'enabled': True, 'icon': '', 'command': ['loginctl', 'reboot']},
    },
}
_config = None
_path = None


def path():
    return _path or Path(os.environ.get('SIMPLEPICKER_CONFIG', str(Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'simplepicker/config.toml'))).expanduser()


def load(filename=None):
    global _config, _path
    if filename is not None:
        _path = Path(filename).expanduser()
    target = path()
    if (filename is not None or 'SIMPLEPICKER_CONFIG' in os.environ) and not target.is_file():
        raise ValueError(f'Config does not exist: {target}')
    config = copy.deepcopy(DEFAULTS)
    data = tomllib.loads(target.read_text()) if target.exists() else {}
    def merge(base, incoming, prefix=''):
        if not isinstance(incoming, dict):
            raise ValueError(f'{prefix} must be a table')
        for key, value in incoming.items():
            name = prefix + key
            if key not in base:
                raise ValueError(f'Unknown config setting: {name}')
            if isinstance(base[key], dict):
                merge(base[key], value, name + '.')
            elif type(value) is not type(base[key]):
                raise ValueError(f'Invalid type for {name}')
            elif isinstance(value, list) and (any(not isinstance(v, str) or '\0' in v for v in value) or (value and not value[0])):
                raise ValueError(f'{name} must be an argv array of strings')
            else:
                base[key] = value
    merge(config, data)
    if config['desktop']['backend'] not in ('auto', 'mango', 'hyprland', 'sway', 'custom', 'generic'):
        raise ValueError('desktop.backend: use auto, mango, hyprland, sway, custom or generic')
    if config['desktop']['hyprland_dispatch'] not in ('legacy', 'lua'):
        raise ValueError('desktop.hyprland_dispatch: use legacy or lua')
    if config['ui']['layer_shell'] not in ('auto', 'required', 'off'):
        raise ValueError('ui.layer_shell: use auto, required or off')
    keys = set()
    for name, action in config['power'].items():
        resolve_icon(action['icon'], target.parent)
        if not action['enabled']:
            continue
        key = action['key'].lower()
        if len(key) != 1 or not key.isascii() or not key.isalnum() or key in keys:
            raise ValueError(f'power.{name}.key must be a unique ASCII letter or digit')
        if not action['label'].strip():
            raise ValueError(f'power.{name}.label cannot be empty')
        keys.add(key)
    _config = config
    return config


def get():
    return _config if _config is not None else load()


def expand(argv, **values):
    # Expand environment/home before substitution: window titles/URLs stay literal.
    def arg(value):
        value = os.path.expanduser(os.path.expandvars(value))
        return re.sub(r'\{([a-z_]+)\}', lambda m: str(values[m[1]]) if m[1] in values else m[0], value)
    return [arg(value) for value in argv]


def command(name, **values):
    argv = expand(get()['commands'][name], **values)
    if not argv:
        raise ValueError(f'commands.{name} is disabled')
    return argv


def resolve_icon(value, directory=None):
    """Return (file|theme, value), or None for the system default."""
    if not value:
        return None
    if not value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError('Power icon must be an icon name or image path')
    expanded = os.path.expanduser(os.path.expandvars(value))
    if '/' in expanded or value.startswith(('~', '$', '.')):
        icon = Path(expanded)
        if not icon.is_absolute():
            icon = (directory or path().parent) / icon
        if not icon.is_file():
            raise ValueError(f'Power icon does not exist: {icon}')
        return 'file', str(icon)
    return 'theme', value

"""Small read-only WM adapters. Reading a config never evaluates its commands."""
import configparser
import glob
import json
import os
from pathlib import Path
import re
import shlex
import subprocess


def settings(root=None):
    root = Path(root) if root else Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))
    path = root/'simplepicker/keyboard/config.ini'
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(path)
    wm = cfg.get('shortcuts', 'environment', fallback='auto').lower()
    if wm == 'auto':
        desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
        wm = 'hyprland' if 'hypr' in desktop or os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') else 'mango' if 'mango' in desktop or (root/'mango/config.conf').exists() else 'none'
    if wm not in ('mango', 'hyprland', 'none'):
        raise ValueError('Unsupported shortcuts environment: '+wm)
    default = root/('mango/config.conf' if wm == 'mango' else 'hypr/hyprland.conf')
    if wm == 'hyprland' and (root/'hypr/hyprland.lua').exists():
        default = root/'hypr/hyprland.lua'
    value = cfg.get('shortcuts', 'config', fallback=str(default))
    config = Path(os.path.expandvars(value)).expanduser()
    if not config.is_absolute():
        config = path.parent/config
    enabled = cfg.get('keyboard', 'enabled', fallback='auto').lower()
    if enabled not in ('auto','true','false','yes','no','1','0'):
        raise ValueError('keyboard.enabled must be auto, true or false')
    enabled = (root/'simplepicker/keyboard/config.json').is_file() if enabled == 'auto' else enabled in ('true','yes','1')
    return {'environment':wm, 'config':config, 'keyboard':enabled,
            'names':dict(cfg.items('names')) if cfg.has_section('names') else {}}


def uncomment(line):
    quote = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
        elif char == '\\':
            escaped = True
        elif quote:
            if char == quote:quote = None
        elif char in ('"', "'"):
            quote = char
        elif char == '#' and (index == 0 or line[index-1].isspace()):
            return line[:index].strip()
    return line.strip()


def config_lines(path, wm, variables=None, active=None, depth=0):
    variables = {} if variables is None else variables
    active = set() if active is None else active
    path = path.resolve()
    if path in active or depth > 32:
        raise ValueError('Recursive configuration include: '+str(path))
    active.add(path)
    def expand(value):
        return re.sub(r'\$\{(\w+)\}|\$(\w+)', lambda match:variables.get(match[1] or match[2],os.environ.get(match[1] or match[2],match[0])),value)
    try:
        for raw in path.read_text().splitlines():
            line = uncomment(raw)
            if not line or '=' not in line:continue
            key, value = (part.strip() for part in line.split('=',1))
            value = expand(value)
            if wm == 'mango' and key == 'var':
                name, definition = value.split(',',1);variables[name.strip()] = definition.strip();continue
            if wm == 'hyprland' and key.startswith('$'):
                variables[key[1:]] = value;continue
            if key == 'source':
                child = Path(value.strip('"\'')).expanduser()
                if not child.is_absolute():child = path.parent/child
                matches = sorted(glob.glob(str(child)))
                if not matches and not glob.has_magic(str(child)):
                    raise FileNotFoundError('Included configuration not found: '+str(child))
                for filename in matches:
                    yield from config_lines(Path(filename),wm,variables,active,depth+1)
            else:
                yield key,value
    finally:
        active.remove(path)


def shortcut(modifiers, key):
    mods = [part.title().replace('Control','Ctrl') for part in re.split(r'[+_\s]+',modifiers.strip()) if part and part.lower() != 'none']
    return '+'.join([*mods,key.strip()])


def description(command):
    try:words=shlex.split(command)
    except ValueError:return command
    if not words:return 'Application'
    return Path(words[0]).name.replace('_',' ').replace('-',' ').capitalize()


def hypr_live():
    result = subprocess.run(['hyprctl','-j','binds'],capture_output=True,text=True,timeout=3,check=True)
    for bind in json.loads(result.stdout):
        if bind.get('dispatcher') not in ('exec','execr') or bind.get('submap'):continue
        mask = bind.get('modmask',0)
        mods = '+'.join(name for bit,name in [(64,'Super'),(8,'Alt'),(4,'Ctrl'),(1,'Shift')] if mask & bit)
        key = bind.get('key') or 'code:'+str(bind.get('keycode',0))
        command = bind['arg']
        yield shortcut(mods,key), command, bind.get('description') or description(command), ('wm', ['hyprctl','dispatch',bind['dispatcher'],command])


def bindings(options):
    wm,path = options['environment'], options['config']
    if wm == 'none':return
    if wm == 'hyprland' and path.suffix == '.lua':
        # Lua can generate bindings dynamically. Ask the running compositor;
        # never execute or attempt to interpret a user's Lua configuration.
        yield from hypr_live();return
    submap = ''
    found = {}
    for directive,value in config_lines(path,wm):
        if directive == 'submap':submap = '' if value == 'reset' else value;continue
        if wm == 'hyprland' and directive == 'unbind':
            parts=value.split(',',1)
            if len(parts)==2:found.pop(shortcut(*parts).lower(),None)
            continue
        if not re.fullmatch(r'bind[a-z]*',directive):continue
        if submap:continue
        descriptive = wm == 'hyprland' and 'd' in directive[4:]
        parts = value.split(',',4 if descriptive else 3)
        if len(parts) < (5 if descriptive else 4):continue
        mods,key = parts[:2]
        if descriptive:note,action,command = parts[2:]
        else:action,command=parts[2:];note=''
        action,command = action.strip(),command.strip()
        found.pop(shortcut(mods,key).lower(),None)
        if wm == 'mango':
            if action not in ('spawn','spawn_shell','toggle_named_scratchpad'):continue
            target=('dispatch', action+','+command)
        else:
            if action not in ('exec','execr'):continue
            target=('wm',['hyprctl','dispatch',action,command])
        keys=shortcut(mods,key)
        label_command = command.split(',',2)[-1] if action == 'toggle_named_scratchpad' else command
        found[keys.lower()] = (keys,command,note.strip() or description(label_command),target)
    yield from found.values()

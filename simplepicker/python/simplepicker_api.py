"""Small public helper for personal Simplepicker tools. UI internals stay in ui.py."""
from enum import Enum
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tomllib


class Action(Enum):
    BACK = 'back'
    REFRESH = 'refresh'
    TERMINAL = 'terminal'


BACK = Action.BACK
REFRESH = Action.REFRESH
TERMINAL = Action.TERMINAL


def notify(title, message, *, error=False, success=False):
    try:
        if shutil.which('notify-send'):
            icon = 'dialog-error-symbolic' if error else 'emblem-ok-symbolic' if success else 'dialog-information-symbolic'
            marker = '✕ ' if error else '✓ ' if success else ''
            urgency = 'critical' if error else 'normal'
            result = subprocess.run(['notify-send', '-a', 'Simplepicker', '-i', icon,
                                     '-u', urgency, '--', marker + title, str(message)], capture_output=True)
            if result.returncode == 0:
                return
    except OSError:
        pass
    if error:
        print(f'{title}: {message}', file=sys.stderr)


def copy_text(text, *, title='Simplepicker'):
    """Copy via the configured clipboard command. Return success; never close a menu."""
    from settings import command
    try:
        result = subprocess.run(command('copy'), input=text, text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or 'Clipboard command failed')
    except (OSError, ValueError, RuntimeError) as error:
        notify('Copy failed', str(error), error=True)
        return False
    notify(title, 'Copied to clipboard.', success=True)
    return True


class Menu:
    """A menu that remembers its last activated item when returning from a child."""
    def __init__(self, title='Simplepicker', *, width=820, icon='view-list-symbolic', theme=None, keys=None, key_scope=None):
        self.keys, self.key_scope = keys, key_scope
        self.title, self.width, self.icon, self.theme = title, width, icon, theme
        self.selected = None

    def choose(self, items, *, prompt=None, descriptions=None, preview=None, icons=None,
               on_select=None, shortcuts=(), width=None, height=570, search_items=None):
        """items: {stable_id: label}, or a list of unique strings. Returns ID/Action/None."""
        from ui import normalize, show_menu
        keys_used = set()
        for key, _label, _value in shortcuts:
            if not isinstance(key, str) or len(key) != 1 or key.lower() in keys_used:
                raise ValueError('Shortcut keys must be unique')
            keys_used.add(key.lower())
        labels = dict(items) if isinstance(items, dict) else {item: item for item in items}
        visible_keys = list(labels)
        labels.update(search_items or {})
        if not all(isinstance(key, str) and isinstance(label, str) for key, label in labels.items()):
            raise ValueError('Menu IDs and labels must be strings')
        keys = list(labels)
        searchable = {key: normalize(label + ' ' + (descriptions or {}).get(key, '')) for key, label in labels.items()}

        def search(query):
            words = normalize(query).split()
            return [key for key in keys if all(word in searchable[key] for word in words)] if words else visible_keys

        def activate(key):
            self.selected = key
            return bool(on_select(key)) if on_select else False

        result = show_menu(search, prompt=prompt or self.title, title=self.title,
                           width=width or self.width, height=height, default_icon=self.icon,
                           labels=labels, subtitles=descriptions, icons=icons, theme=self.theme, keys=self.keys, key_scope=self.key_scope,
                           selected_row=visible_keys.index(self.selected) if self.selected in visible_keys else 0,
                           text_preview=preview.get if isinstance(preview, dict) else preview,
                           shortcuts=[('left', 'Back', BACK), *shortcuts], on_select=activate)
        if isinstance(result, str) and result in labels:
            self.selected = result
        return result

    def details(self, content, *, sections=False, terminal=None):
        """Display a dashboard report with copy, refresh and optional terminal actions."""
        from info_panel import show_report
        return show_report(self.title, content, sections=sections, terminal=terminal, keys=self.keys, key_scope=self.key_scope)


def load_tools(path):
    """Load a small, explicit tool registry. Commands are argv lists, never implicit shell."""
    with Path(path).open('rb') as source:
        config = tomllib.load(source)
    if set(config) - {'title', 'tools', 'icon', 'theme', 'keys', 'key_scope', 'group_icons', 'max_height'}:
        raise ValueError('Unknown top-level tool configuration key')
    if not isinstance(config.get('title', 'System'), str):
        raise ValueError('title must be text')
    for field in ('icon', 'theme', 'keys', 'key_scope'):
        if field in config and not isinstance(config[field], str):
            raise ValueError(f'{field} must be text')
    max_height = config.get('max_height', 570)
    if type(max_height) is not int or not 360 <= max_height <= 1200:
        raise ValueError('max_height must be an integer between 360 and 1200')
    group_icons = config.get('group_icons', {})
    if not isinstance(group_icons, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in group_icons.items()):
        raise ValueError('group_icons must map category names to icon names')
    tools = config.get('tools', [])
    if not isinstance(tools, list):
        raise ValueError('tools must be a list of [[tools]] entries')
    ids = set()
    for tool in tools:
        if not isinstance(tool, dict) or set(tool) - {'id', 'name', 'group', 'command', 'handler', 'close_after', 'icon'}:
            raise ValueError('Invalid or unknown tool field')
        for field in ('id', 'name'):
            if not isinstance(tool.get(field), str) or not tool[field].strip():
                raise ValueError(f'Tool {field} must be nonempty text')
        if tool['id'] in ids:
            raise ValueError('Duplicate tool ID: ' + tool['id'])
        ids.add(tool['id'])
        if 'icon' in tool and not isinstance(tool['icon'], str):
            raise ValueError('Tool icon must be text')
        if 'group' in tool and (not isinstance(tool['group'], str) or not tool['group'].strip()):
            raise ValueError('Tool group must be nonempty text')
        if ('command' in tool) == ('handler' in tool):
            raise ValueError('Each tool needs exactly one command or handler')
        if 'command' in tool:
            argv = tool['command']
            if not isinstance(argv, list) or not argv or not all(isinstance(v, str) for v in argv) or not argv[0]:
                raise ValueError('Tool command must be a nonempty argv list')
        if 'handler' in tool and (not isinstance(tool['handler'], str) or not tool['handler']):
            raise ValueError('Tool handler must be nonempty text')
        if not isinstance(tool.get('close_after', False), bool):
            raise ValueError('close_after must be true or false')
    return config


class ToolMenu:
    """Configurable root/groups; optional named Python handlers supplied by the caller."""
    def __init__(self, path, *, handlers=None):
        self.config = load_tools(path)
        self.handlers = handlers or {}
        self.tools = {t['id']: t for t in self.config.get('tools', [])}
        for tool in self.tools.values():
            if 'handler' in tool and tool['handler'] not in self.handlers:
                raise ValueError('Unknown handler: ' + tool['handler'])
        self.title = self.config.get('title', 'System')
        self.menus = {}

    def invoke(self, tool):
        try:
            if 'handler' in tool:
                self.handlers[tool['handler']]()
            else:
                argv = [os.path.expanduser(os.path.expandvars(arg)) for arg in tool['command']]
                result = subprocess.run(argv, check=False)
                if result.returncode:
                    notify(tool['name'], f'Command exited with status {result.returncode}', error=True)
                    return False
            return tool.get('close_after', False)
        except OSError as error:
            notify(tool['name'], str(error), error=True)
            return False

    def run(self, *, start=None):
        if start:
            if start not in self.tools:
                raise ValueError('Unknown starting tool: ' + start)
            if self.invoke(self.tools[start]):
                return
        self._level(None)

    def _level(self, group):
        menu = self.menus.setdefault(group, Menu(self.title if group is None else self.title + ' / ' + group,
                                               icon=self.config.get('group_icons', {}).get(group, self.config.get('icon', 'view-list-symbolic')),
                                               theme=self.config.get('theme'), keys=self.config.get('keys'), key_scope=self.config.get('key_scope')))
        labels, targets, icons, search_items, descriptions = {}, {}, {}, {}, {}
        for tool in self.tools.values():
            category = tool.get('group')
            if group is None and category:
                key = 'group:' + category
                labels[key], targets[key] = category, ('group', category)
                if category in self.config.get('group_icons', {}): icons[key] = self.config['group_icons'][category]
                tool_key = 'tool:' + tool['id']
                search_items[tool_key] = tool['name']
                targets[tool_key] = ('tool', tool)
                descriptions[tool_key] = category
                if 'icon' in tool:
                    icons[tool_key] = tool['icon']
            elif category == group:
                key = 'tool:' + tool['id']
                labels[key], targets[key] = tool['name'], ('tool', tool)
                if 'icon' in tool:
                    icons[key] = tool['icon']
        labels['navigation:back'] = 'Close' if group is None else 'Back'
        icons['navigation:back'] = 'window-close-symbolic' if group is None else 'go-previous-symbolic'
        while True:
            choice = menu.choose(labels, icons=icons, search_items=search_items,
                                 descriptions=descriptions,
                                 height=min(self.config.get('max_height', 570),
                                            max(570, 160 + 48 * len(labels))))
            if choice is None or choice == BACK or choice == 'navigation:back':
                return False
            if choice not in targets:
                continue
            kind, target = targets[choice]
            if (self._level(target) if kind == 'group' else self.invoke(target)):
                return True

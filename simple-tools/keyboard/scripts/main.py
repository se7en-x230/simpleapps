#!/usr/bin/env python3
import os as _path_os, sys as _path_sys
from pathlib import Path as _Path
_roots=[_Path(__file__).resolve().parents[3],_Path(_path_os.environ.get('XDG_DATA_HOME',_Path.home()/'.local/share')),_Path.home()/'.local/src']
if _path_os.environ.get('SIMPLE_SOURCE_ROOT'):_roots.insert(0,_Path(_path_os.environ['SIMPLE_SOURCE_ROOT']))
for _root in reversed(_roots):
    for _name in ('simplepicker/python','simple-common'):
        if (_root/_name).is_dir():_path_sys.path.insert(0,str(_root/_name))
import json
import sys
from pathlib import Path
from exporter import export, watch


def more_keys(app, references):
    items, descriptions = {}, {}
    for row in references:
        parts = row.split(' | ', 2)
        if len(parts) != 3:
            continue
        owner, keys, action = parts
        if owner.lower() not in ('shared', app.lower(), app.lower()+' configured'):
            continue
        # Configuration locations are not keyboard actions.
        if keys in ('Configuration', 'Letter shortcuts'):
            continue
        key_parts, actions = keys.split(' / '), action.split(' / ')
        pairs = zip(key_parts, actions) if len(key_parts) == len(actions) and len(actions) > 1 else [(keys, action)]
        for shortcut, label in pairs:
            for before, after in (('<Control>', 'Ctrl+'), ('<Shift>', 'Shift+'),
                                  ('<Alt>', 'Alt+'), ('Return', 'Enter'), ('Escape', 'Esc')):
                shortcut = shortcut.replace(before, after)
            key = str(len(items))
            items[key] = label[:1].upper()+label[1:]+'  ·  '+shortcut
            descriptions[key] = 'Shared navigation' if owner == 'Shared' else owner
    return items, descriptions


def shortcut_order(shortcuts):
    candidates = []
    for shortcut in shortcuts:
        if shortcut.startswith('No dedicated shortcut'):
            continue
        parts = shortcut.casefold().split('+')
        key, modifiers = parts[-1], set(parts[:-1])
        rank = (1 if 'alt' in modifiers else 0) + (2 if 'ctrl' in modifiers else 0) + (4 if 'shift' in modifiers else 0)
        candidates.append((0, key, 0 if 'super' in modifiers else 1, rank, shortcut.casefold()))
    return min(candidates) if candidates else (1, '', 0, 0, '')


def main():
    if '--watch' in sys.argv:
        watch()
    elif '--export' in sys.argv:
        print(json.dumps(export(), indent=2))
    else:
        from dashboard import App
        App().run([])


if __name__ == '__main__':
    main()

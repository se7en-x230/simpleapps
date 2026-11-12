import sys
from pathlib import Path
root=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(root/'simple-tools/keyboard/scripts'))
from main import more_keys, shortcut_order
from reference import app_rows
from launchers import launch_rows
labels,hints=more_keys('Simpleclip',app_rows())
assert any('Delete selected history' in label for label in labels.values())
assert not any('Compose' in label for label in labels.values())
keys=['Super+b','Super+Shift+a','Super+Ctrl+a','Super+a','Super+Alt+a']
assert sorted(keys,key=lambda key:shortcut_order([key]))==['Super+a','Super+Alt+a','Super+Ctrl+a','Super+Shift+a','Super+b']
assert shortcut_order(['No dedicated shortcut'])>shortcut_order(['Super+z'])
rows=launch_rows()
assert any('Simpleplayer' in name and 'music' in name.casefold() for name in rows)
assert any('Now playing' in name and 'music' in name.casefold() for name in rows)
assert any('Garmin' in name and 'dashboard' in name for name in rows)
assert any('System' in name and 'dashboard' in name for name in rows)
assert rows['Browser']==['Super+w']
print('PASS app controls, grouped key sorting, opening shortcuts and music/dashboard search names')

targets={};launch_rows(targets=targets)
assert targets['Browser'][0]=='dispatch' and 'helium' in targets['Browser'][1]
kind, command = targets['Simplepicker — Now playing music dashboard']
assert kind in ('argv', 'dispatch')
assert 'simplepicker' in command and '--dashboard' in command if kind == 'argv' else 'simplepicker --dashboard' in command
assert targets['Simpleclip — Clipboard history'][0]=='dispatch'
print('PASS real binding targets and direct dashboard launch; no commands executed')

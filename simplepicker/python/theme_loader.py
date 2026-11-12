"""Locate the shared C-backed theme adapter in a checkout or installation."""
import sys
from pathlib import Path
_root = Path(__file__).resolve().parent
for _candidate in (_root.parents[1] / 'simple-common', _root.parent / 'simple-common'):
    if (_candidate / 'simple_ui.py').is_file():
        sys.path.insert(0, str(_candidate))
        break
from simple_ui import load_css

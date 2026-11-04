import sys as _theme_sys
from pathlib import Path as _ThemePath
_theme_sys.path.insert(0,str(_ThemePath(__file__).resolve().parent))
from theme_loader import load_css as _load_simple_css
"""System GTK styling, with optional personal or per-invocation CSS overrides."""
from pathlib import Path
import os


def theme_path(override=None, *, kind='menu'):
    selected = override or os.environ.get('SIMPLEPICKER_THEME')
    if selected:
        path = Path(os.path.expandvars(str(selected))).expanduser()
        if not path.is_file():
            raise ValueError(f'Theme file does not exist: {path}')
        return path
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'simplepicker'
    path = config / ('power/style.css' if kind == 'power' else 'style.css')
    return path if path.is_file() else None


def apply_css(Gtk, Gdk, *, override=None, kind='menu'):
    """Only geometry/overlay transparency are built in; colors/fonts come from GTK."""
    display = Gdk.Display.get_default()
    providers = []
    base = Gtk.CssProvider()
    base.load_from_data(b'''
window.simplepicker-layer { background: transparent; }
.simplepicker .box-wrapper { padding: 20px; }
.simplepicker .item-box { padding: 8px; }
.simplepicker .simplepicker-brand { opacity: 0.5; }
.simplepicker-power button { padding: 12px; }
''')
    Gtk.StyleContext.add_provider_for_display(display, base, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    providers.append(base)
    try:
        path = theme_path(override, kind=kind)
        custom = Gtk.CssProvider()
        _load_simple_css(custom,path)
        Gtk.StyleContext.add_provider_for_display(display, custom, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        providers.append(custom)
    except Exception:
        remove_css(Gtk, Gdk, providers)
        raise
    return providers


def remove_css(Gtk, Gdk, providers):
    display = Gdk.Display.get_default()
    for provider in providers:
        Gtk.StyleContext.remove_provider_for_display(display, provider)

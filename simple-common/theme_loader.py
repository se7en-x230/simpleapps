"""Shared Simple appearance first, optional application CSS second."""
from pathlib import Path
import os
_shared = {}
def load_css(provider, path=None):
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk, Gdk
    display=Gdk.Display.get_default()
    root=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))
    if display not in _shared:
        shared=Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(display,shared,Gtk.STYLE_PROVIDER_PRIORITY_USER-1)
        _shared[display]=shared
    shared=_shared[display]
    base=root/'simple/aliases.css'
    if not base.is_file():base=root/'simple/theme.css'
    if not base.is_file():base=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'simple/aliases.css'
    if base.is_file():shared.load_from_path(str(base))
    else:shared.load_from_data(b'')
    if path and Path(path).is_file():provider.load_from_path(str(path))
    else:provider.load_from_data(b'')

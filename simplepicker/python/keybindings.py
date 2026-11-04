"""Shared Simple navigation: suite -> app -> module -> explicit override."""
from pathlib import Path
import os, sys, configparser
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk
DEFAULTS={'up':'Up,k,<Control>k','down':'Down,j,<Control>j','left':'Left,h,<Control>h','right':'Right,l,<Control>l','activate':'Return,KP_Enter','cancel':'Escape','page_up':'Page_Up,<Control>u','page_down':'Page_Down,<Control>d'}
class KeyBindings:
    def __init__(self, scope=None, override=None, app='simplepicker'):
        root=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))
        if scope is None:
            try:
                relative=Path(sys.argv[0]).resolve().relative_to(root/app)
                scope=relative.parts[0] if len(relative.parts)>1 else None
            except ValueError:pass
        paths=[root/'simple/keys.ini',root/app/'keys.ini']
        if scope:paths.append(root/app/scope/'keys.ini')
        if override:paths.append(Path(os.path.expandvars(str(override))).expanduser())
        self.values=DEFAULTS.copy()
        self.vim_navigation=True
        for path in paths:
            if not path.is_file():
                if override and path==paths[-1]:raise ValueError(f'Key bindings not found: {path}')
                continue
            config=configparser.ConfigParser(interpolation=None)
            config.read(path)
            if config.has_option("interaction","vim_navigation"):
                self.vim_navigation=config.getboolean("interaction","vim_navigation")
            for action,value in config.items('navigation') if config.has_section('navigation') else []:
                if action not in DEFAULTS:raise ValueError(f'Unknown navigation action: {action}')
                for item in value.split(','):
                    if item.strip() and not Gtk.accelerator_parse(item.strip())[0]:raise ValueError(f'Invalid navigation key: {item}')
                self.values[action]=value
    def matches(self, action, key, state, editing=False):
        mods=state & (Gdk.ModifierType.SHIFT_MASK|Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.ALT_MASK|Gdk.ModifierType.SUPER_MASK|Gdk.ModifierType.META_MASK)
        modified=mods & ~Gdk.ModifierType.SHIFT_MASK
        if editing and not modified and (Gdk.keyval_to_unicode(key)>=32 or key in (Gdk.KEY_Left,Gdk.KEY_Right,Gdk.KEY_Home,Gdk.KEY_End)):return False
        for item in self.values[action].split(','):
            if not item.strip():continue
            valid,wanted,mask=Gtk.accelerator_parse(item.strip())
            if valid and Gdk.keyval_to_lower(key)==Gdk.keyval_to_lower(wanted) and mods==mask:return True
        return False

    def label(self, action):
        result='Disabled'
        for item in self.values[action].split(','):
            if item.strip():
                valid,key,mods=Gtk.accelerator_parse(item.strip())
                if valid:result=Gtk.accelerator_get_label(key,mods)
        return result
    def hint(self):
        return f"{self.label('up')}/{self.label('down')} Move · {self.label('left')}/{self.label('right')} Controls · {self.label('activate')} Activate · {self.label('cancel')} Close"

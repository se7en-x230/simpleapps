"""Thin GTK/Python adapter for the authoritative Simple UI C library (ABI 1)."""
import ctypes as C
import os
from pathlib import Path
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk

_root = Path(__file__).resolve().parent
_candidates = (_root / 'libsimple-ui.so',
               _root.parent.parent / 'lib/simple-common/libsimple-ui.so',
               Path.home() / '.local/lib/simple-common/libsimple-ui.so')
_path = Path(os.environ['SIMPLE_UI_LIBRARY']) if os.environ.get('SIMPLE_UI_LIBRARY') else next((path for path in _candidates if path.is_file()), None)
if _path is None:
    raise RuntimeError('Simple UI library missing. Run make -C simple-common install with the same PREFIX as this adapter.')
_lib = C.CDLL(str(_path))
_lib.simple_ui_abi_version.restype = C.c_uint
if _lib.simple_ui_abi_version() != 1:
    raise RuntimeError('Unsupported Simple UI library ABI')
_lib.simple_ui_window.argtypes = [C.c_void_p]
_lib.simple_ui_window.restype = None
_lib.simple_ui_control_key.argtypes = [C.c_void_p, C.c_uint, C.c_uint]
_lib.simple_ui_control_key.restype = C.c_int
_lib.simple_ui_legacy_control_key.argtypes = [C.c_void_p, C.c_uint, C.c_uint]
_lib.simple_ui_legacy_control_key.restype = C.c_int
_lib.simple_ui_theme_load.argtypes = [C.c_void_p, C.c_char_p]
_lib.simple_ui_theme_load.restype = None
_lib.simple_ui_key_matches.argtypes = [C.c_char_p, C.c_char_p, C.c_uint, C.c_uint]
_lib.simple_ui_key_matches.restype = C.c_int
_lib.simple_ui_key_label.argtypes = [C.c_char_p, C.c_char_p]
_lib.simple_ui_key_label.restype = C.c_void_p
_lib.simple_ui_free.argtypes = [C.c_void_p]
_lib.simple_ui_free.restype = None
_capsule_pointer = C.pythonapi.PyCapsule_GetPointer
_capsule_pointer.argtypes = [C.py_object, C.c_char_p]
_capsule_pointer.restype = C.c_void_p


def attach(window):
    """Apply the shared style to a borrowed GTK window on the main thread."""
    _lib.simple_ui_window(_capsule_pointer(window.__gpointer__, None))


def control_key(window, key, state):
    result = _lib.simple_ui_control_key(_capsule_pointer(window.__gpointer__, None), key, int(state))
    return None if result < 0 else bool(result)


class KeyBindings:
    def __init__(self, app):
        self.app = app.encode()

    def matches(self, action, key, state):
        return bool(_lib.simple_ui_key_matches(self.app, action.encode(), key, int(state)))

    def label(self, action):
        pointer = _lib.simple_ui_key_label(self.app, action.encode())
        try:
            return C.string_at(pointer).decode()
        finally:
            _lib.simple_ui_free(pointer)


def dialog_keys(window):
    attach(window)
    def pressed(controller, key, code, state):
        if key == Gdk.KEY_Escape:
            window.close()
            return True
        return bool(control_key(window, key, state))
    keys = Gtk.EventControllerKey()
    keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    keys.connect('key-pressed', pressed)
    window.add_controller(keys)


def legacy_control_key(window, key, state):
    result = _lib.simple_ui_legacy_control_key(_capsule_pointer(window.__gpointer__, None), key, int(state))
    return None if result < 0 else bool(result)


def load_css(provider, path=None):
    windows = Gtk.Window.get_toplevels()
    for index in range(windows.get_n_items()):
        attach(windows.get_item(index))
    _lib.simple_ui_theme_load(_capsule_pointer(provider.__gpointer__, None),
                             str(path).encode() if path else None)


_SearchCallback = C.CFUNCTYPE(None, C.c_int, C.c_void_p)
_lib.simple_ui_bind_search.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_char_p, _SearchCallback, C.c_void_p]
_lib.simple_ui_bind_search.restype = None
_lib.simple_ui_search_start.argtypes = [C.c_void_p, C.c_int]
_lib.simple_ui_search_start.restype = None


def bind_search(window, search, navigation, app, move, activate, navigate=None):
    """Bind domain actions to the shared C search/navigation policy."""
    def action(kind, _):
        if kind in (1, 2): move(1 if kind == 1 else -1)
        elif kind == 3: activate()
        elif kind == 4 and navigate: navigate()
    callback = _SearchCallback(action)
    window._simple_search_callback = callback
    pointer = lambda obj: _capsule_pointer(obj.__gpointer__, None)
    _lib.simple_ui_bind_search(pointer(window), pointer(search), pointer(navigation), app.encode(), callback, None)


def start_search(window, fallback=False):
    _lib.simple_ui_search_start(_capsule_pointer(window.__gpointer__, None), bool(fallback))


_lib.simple_ui_search_set.argtypes = [C.c_void_p, C.c_int]
_lib.simple_ui_search_set.restype = None


def set_search(window, visible):
    """Show search, or clear/hide it and return to result navigation."""
    _lib.simple_ui_search_set(_capsule_pointer(window.__gpointer__, None), bool(visible))

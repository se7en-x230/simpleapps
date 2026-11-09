"""Let focused GTK controls handle keys before application navigation shortcuts."""
def control_key(window, key, state):
    from gi.repository import Gtk, Gdk
    display = window.get_display()
    if not getattr(display, '_simple_keyboard_style', None):
        css = Gtk.CssProvider()
        css.load_from_string('button:focus-visible, checkbutton:focus-visible, switch:focus-visible, dropdown:focus-visible, scale:focus-visible { outline: 2px solid #f3a40a; outline-offset: -2px; }')
        Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 10)
        display._simple_keyboard_style = css
    # Tab must always reach GTK, including after a pending Vim command prefix.
    if key in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
        return False
    if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.SUPER_MASK):
        return None
    navigation = (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space,
                  Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Up, Gdk.KEY_Down,
                  Gdk.KEY_Home, Gdk.KEY_End, Gdk.KEY_Page_Up, Gdk.KEY_Page_Down)
    if key not in navigation:
        return None
    widget = window.get_focus()
    while widget:
        if isinstance(widget, (Gtk.Button, Gtk.CheckButton, Gtk.Switch, Gtk.DropDown,
                               Gtk.Range, Gtk.SpinButton)):
            if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and isinstance(widget, (Gtk.Button, Gtk.CheckButton)):
                widget.activate()
                return True
            return False
        widget = widget.get_parent()
    return None


def dialog_keys(window):
    """Keep modal buttons keyboard reachable without stealing text-entry keys."""
    from gi.repository import Gtk, Gdk
    def pressed(controller, key, code, state):
        if key == Gdk.KEY_Escape:
            window.close()
            return True
        result = control_key(window, key, state)
        return False if result is None else result
    keys = Gtk.EventControllerKey()
    keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    keys.connect('key-pressed', pressed)
    window.add_controller(keys)
    return keys

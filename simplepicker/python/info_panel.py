from keybindings import KeyBindings
import sys as _theme_sys
from pathlib import Path as _ThemePath
_theme_sys.path.insert(0,str(_ThemePath(__file__).resolve().parent))
from theme_loader import load_css as _load_simple_css
"""Shared dashboard information cards; providers run away from the GTK thread."""
from pathlib import Path
import concurrent.futures
import ipaddress
import json
import os
import runpy
import subprocess
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GLib


for _root in [*Path(__file__).resolve().parents, Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))]:
    if (_root/'simple-common/simple_keyboard.py').is_file():
        _theme_sys.path.insert(0,str(_root/'simple-common'));break
from simple_keyboard import control_key
from simple_ui import attach

def cards_for(content, sections=True):
    if isinstance(content, list):
        return content
    if not isinstance(content, str):
        raise ValueError('Information must be text or a list of cards')
    parts = [part.strip() for part in content.split('\n\n' if sections else '\n') if part.strip()]
    cards = []
    for part in parts:
        title, sep, value = part.partition('\n')
        cards.append({'title': title if sep else 'Information', 'value': value if sep else title})
    return cards or [{'title': 'Information', 'value': 'No information available.'}]


def label(text, style):
    widget = Gtk.Label(label=str(text), xalign=0, wrap=True, selectable=False)
    widget.add_css_class(style)
    return widget


class InfoWindow(Gtk.ApplicationWindow):
    def __init__(self, app, title, provider, *, sections=True, terminal=None, fit_contents=False, keys=None, key_scope=None):
        super().__init__(application=app, title=title)
        attach(self)
        self.keybindings = KeyBindings(key_scope, keys)
        self.fleet_vim = True  # Information cards always use Vim navigation; no search field.
        self.provider, self.sections, self.terminal = provider, sections, terminal
        self.fit_contents = fit_contents
        self.closed = self.busy = False
        self.text = ''
        self.card_widgets = []
        self.card_values = []
        self.selected = 0
        self.pending_key = None
        self.pending_at = 0
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.set_decorated(False)
        self.add_css_class('simple-sound')
        if fit_contents: self.add_css_class('info-fit')
        display = Gdk.Display.get_default()
        rect = display.get_monitors().get_item(0).get_geometry()
        self.set_default_size(min(780 if fit_contents else 700, rect.width-64), min(540 if fit_contents else 620, rect.height-80))
        css = Gtk.CssProvider()
        _load_simple_css(css,str(Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'simplepicker/dashboard/info.css'))
        Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_USER+1)
        self.css = css
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.add_css_class('sound-body'); body.add_css_class('root'); self.set_child(body); self.body = body
        header = Gtk.Box(spacing=12)
        title_label = label('Simplepicker · '+title, 'title'); title_label.set_hexpand(True); header.append(title_label)
        header.append(self.button('Close', self.close)); body.append(header)
        bar = Gtk.Box(spacing=8); self.toolbar = bar
        self.copy_button = self.button('Copy all', lambda: self.copy(self.text)); bar.append(self.copy_button)
        self.refresh_button = self.button('Refresh', self.refresh)
        self.refresh_button.set_visible(callable(provider)); bar.append(self.refresh_button)
        if terminal: bar.append(self.button('Open in terminal', terminal))
        body.append(bar)
        self.status = label('Reading information…', 'sound-hint'); body.append(self.status)
        self.cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8 if fit_contents else 12)
        if fit_contents:
            body.append(self.cards)
        else:
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
            scroll.set_child(self.cards); body.append(scroll)
        body.append(label(('j/k Cards · h/l Controls · gg/G Ends · Ctrl+d/u Page · yy Copy · r Refresh · q/Esc Back' if self.fleet_vim else self.keybindings.hint() + ' · yy Copy · r Refresh'), 'sound-hint'))
        keys = Gtk.EventControllerKey(); keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE); keys.connect('key-pressed', self.key); self.add_controller(keys)
        self.connect('close-request', self.on_close)
        self.refresh()

    def button(self, text, callback):
        button = Gtk.Button(label=text)
        button.connect('clicked', lambda *_: callback())
        return button

    def copy(self, value):
        from simplepicker_api import copy_text
        if copy_text(str(value), title=self.get_title()):
            self.status.set_text('Copied to clipboard')
        else:
            self.status.set_text('Copy failed')

    def select_card(self, index, *, focus=True):
        if not self.card_widgets: return
        self.selected = max(0, min(index, len(self.card_widgets)-1))
        for i, card in enumerate(self.card_widgets):
            if i == self.selected: card.add_css_class('info-selected')
            else: card.remove_css_class('info-selected')
        if focus: self.card_widgets[self.selected].grab_focus()

    def focus_header(self):
        self.selected = 0
        self.set_focus_visible(True)
        for card in self.card_widgets: card.remove_css_class('info-selected')
        target = self.copy_button if self.copy_button.get_sensitive() else self.refresh_button
        if target.get_visible() and target.get_sensitive(): target.grab_focus()
        else: self.child_focus(Gtk.DirectionType.TAB_FORWARD)

    def in_cards(self):
        focus = self.get_focus()
        return bool(focus and any(focus == card or focus.is_ancestor(card) for card in self.card_widgets))

    def move_horizontal(self, delta):
        if not self.in_cards():
            buttons=[]
            child=self.toolbar.get_first_child()
            while child:
                if child.get_visible() and child.get_sensitive(): buttons.append(child)
                child=child.get_next_sibling()
            focus=self.get_focus()
            index=next((i for i,b in enumerate(buttons) if focus==b or (focus and focus.is_ancestor(b))),0)
            if buttons:
                self.set_focus_visible(True)
                buttons[max(0,min(index+delta,len(buttons)-1))].grab_focus()
                return
        self.child_focus(Gtk.DirectionType.TAB_FORWARD if delta>0 else Gtk.DirectionType.TAB_BACKWARD)

    def move_vertical(self, delta):
        buttons = []
        child = self.toolbar.get_first_child()
        while child:
            if child.get_visible() and child.get_sensitive(): buttons.append(child)
            child = child.get_next_sibling()
        if self.in_cards():
            if self.selected == 0 and delta < 0 and buttons:
                target = buttons[-1]
            else:
                self.select_card(self.selected+delta)
                return
        else:
            focus = self.get_focus()
            index = next((i for i,b in enumerate(buttons) if focus == b or (focus and focus.is_ancestor(b))), -1)
            next_index = index+delta
            if next_index >= len(buttons) or (index < 0 and delta > 0):
                self.select_card(0)
                return
            if not buttons: return
            target = buttons[max(0, next_index)]
        for card in self.card_widgets: card.remove_css_class('info-selected')
        self.set_focus_visible(True)
        target.grab_focus()

    def key(self, controller, key, code, state):
        handled = control_key(self, key, state)
        if handled is not None: return handled
        if self.keybindings.matches("cancel",key,state):
            self.close(); return True
        for action,move,delta in [('down',self.move_vertical,1),('up',self.move_vertical,-1),('left',self.move_horizontal,-1),('right',self.move_horizontal,1)]:
            if self.keybindings.matches(action,key,state):move(delta);return True
        if self.keybindings.matches("activate",key,state):
            focus=self.get_focus()
            if focus and focus.activate():return True
        if state & Gdk.ModifierType.CONTROL_MASK:
            self.pending_key = None
            if self.fleet_vim and key in (Gdk.KEY_d, Gdk.KEY_u):
                self.select_card(self.selected + (5 if key == Gdk.KEY_d else -5)); return True
            if key == Gdk.KEY_r: self.refresh(); return True
            if key == Gdk.KEY_c: self.copy(self.text); return True
            if key == Gdk.KEY_t and self.terminal: self.terminal(); return True
            return False
        if state & (Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.SUPER_MASK): return False
        now = GLib.get_monotonic_time()
        previous = self.pending_key if now-self.pending_at < 2000000 else None
        self.pending_key = None
        if key == Gdk.KEY_G: self.select_card(len(self.card_widgets)-1 if self.fleet_vim else 0); return True
        if key == Gdk.KEY_g:
            if previous == key:
                if self.fleet_vim: self.select_card(0)
                else: self.focus_header()
            else: self.pending_key, self.pending_at = key, now
            return True
        if key == Gdk.KEY_y:
            if previous == key:
                if self.card_values and self.card_values[self.selected]: self.copy(self.card_values[self.selected])
            else: self.pending_key, self.pending_at = key, now
            return True
        if key == Gdk.KEY_Y: self.copy(self.text); return True
        if key == Gdk.KEY_r: self.refresh(); return True
        if key == Gdk.KEY_q: self.close(); return True
        return False

    def on_close(self, *_):
        self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)
        Gtk.StyleContext.remove_provider_for_display(self.get_display(), self.css)
        return False

    def refresh(self):
        if self.busy or self.closed: return
        self.busy = True; self.refresh_button.set_sensitive(False); self.copy_button.set_sensitive(False)
        self.status.set_text('Reading information…')
        future = self.pool.submit(lambda: cards_for(self.provider() if callable(self.provider) else self.provider, self.sections))
        future.add_done_callback(lambda result: GLib.idle_add(self.received, result))

    def received(self, future):
        if self.closed: return False
        self.busy = False; self.refresh_button.set_sensitive(True)
        try: cards = future.result()
        except Exception as error:
            self.status.set_text('Information unavailable: '+str(error)); return False
        focus_cards = self.in_cards() or self.get_focus() is None
        while self.cards.get_first_child(): self.cards.remove(self.cards.get_first_child())
        self.text = '\n\n'.join(str(c['title'])+'\n'+str(c['value']) for c in cards)
        self.card_widgets = []
        self.card_values = []
        for index, data in enumerate(cards):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); card.add_css_class('sound-card')
            card.add_css_class('card'); card.add_css_class('info-card')
            card.set_focusable(True)
            card.connect('notify::has-focus', lambda card, _, i=index: self.select_card(i, focus=False) if card.has_focus() else None)
            click = Gtk.GestureClick()
            click.connect('pressed', lambda gesture, count, x, y, i=index: self.select_card(i, focus=False))
            card.add_controller(click)
            self.card_widgets.append(card)
            heading = Gtk.Box(spacing=12)
            if data.get('icon'):
                icon = Gtk.Image.new_from_icon_name(data['icon'])
                icon.add_css_class('sound-icon')
                icon.set_pixel_size(24)
                heading.append(icon)
            name = label(data['title'], 'info-key'); name.set_hexpand(not self.fit_contents); heading.append(name)
            if self.fit_contents:
                content = label(data['value'], 'info-value'); content.set_hexpand(True); heading.append(content)
            value = data.get('copy', data['value'])
            self.card_values.append(value)
            if value:
                button = self.button('Copy', lambda value=value: self.copy(value))
                button.connect('notify::has-focus', lambda button, _, i=index: self.select_card(i, focus=False) if button.has_focus() else None)
                heading.append(button)
            card.append(heading)
            if not self.fit_contents: card.append(label(data['value'], 'info-value'))
            self.cards.append(card)
        self.select_card(self.selected, focus=focus_cards)
        self.copy_button.set_sensitive(True); self.status.set_text('Updated just now')
        if not focus_cards:
            for card in self.card_widgets: card.remove_css_class('info-selected')
        if self.fit_contents: GLib.idle_add(self.fit_height)
        return False

    def fit_height(self):
        if self.closed: return False
        monitor = self.get_display().get_monitor_at_surface(self.get_surface())
        rect = monitor.get_geometry()
        width = min(780, rect.width-64)
        _, natural, _, _ = self.body.measure(Gtk.Orientation.VERTICAL, width-2)
        self.set_default_size(width, min(max(480, natural+2), rect.height-80))
        return False


def show_report(title, provider, *, sections=True, terminal=None, fit_contents=False, keys=None, key_scope=None):
    app = Gtk.Application(application_id='com.go7.SimpleInformation', flags=Gio.ApplicationFlags.NON_UNIQUE)
    def activate(app):
        win = InfoWindow(app, title, provider, sections=sections, terminal=terminal, fit_contents=fit_contents, keys=keys, key_scope=key_scope)
        win.present()
    app.connect('activate', activate)
    return app.run([])


def local_addresses():
    try:
        result = subprocess.run(['ip', '-j', 'address', 'show'], capture_output=True, text=True, timeout=4, check=True)
        cards = []
        for interface in json.loads(result.stdout):
            for address in interface.get('addr_info', []):
                if address.get('scope') == 'host': continue
                value = str(ipaddress.ip_address(address['local']))
                cards.append({'title': interface['ifname']+' · '+address['family'], 'value': value, 'copy': value, 'icon': 'network-wireless-symbolic' if interface['ifname'].startswith('wl') else 'network-wired-symbolic'})
        return sorted(cards, key=lambda c: (not c['title'].startswith(('wl', 'wlan')), c['title']))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return [{'title': 'Local addresses', 'value': 'Unavailable', 'copy': '', 'icon': 'network-wired-symbolic'}]


def ip_report():
    helper = Path(__file__).resolve().parents[2]/'simple-tools/network/scripts/internet_status.py'
    if not helper.is_file():helper = Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'simplepicker/network/scripts/internet_status.py'
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        local = pool.submit(local_addresses)
        internet = pool.submit(lambda: runpy.run_path(str(helper))['status']())
        cards, info = local.result(), internet.result()
    public = info.get('ip', 'Unavailable')
    cards.insert(0, {'title': 'Public IP', 'icon': 'network-server-symbolic', 'value': public, 'copy': public if public != 'Unavailable' else ''})
    cards.append({'title': 'Internet', 'icon': 'network-transmit-receive-symbolic', 'value': '\n'.join(str(info.get(k) or 'Unavailable') for k in ('state','location','isp','ping'))})
    return cards

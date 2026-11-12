#!/usr/bin/env python3
"""Simpletag: shared GTK frontend, Picard owns the music and tag settings."""
import os
from pathlib import Path
import subprocess
import sys
import threading
import tomllib

for base in (Path(__file__).resolve().parent.parent/'simple-common',
             Path(__file__).resolve().parents[2]/'lib/simple-common', Path.home()/'.local/lib/simple-common'):
    if (base/'simple_ui.py').is_file():
        sys.path.insert(0, str(base))
        break
from simple_ui import attach, bind_search, start_search, KeyBindings, control_key
from gi.repository import Gtk, Gdk, GLib
from client import Client

CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'simpletag'

def preferences():
    defaults = tomllib.loads(Path(__file__).with_name('config.toml').read_text())
    if (CONFIG/'config.toml').is_file():
        defaults.update(tomllib.loads((CONFIG/'config.toml').read_text()))
    return defaults

def label(value='', css=None):
    widget = Gtk.Label(label=value, xalign=0, wrap=True)
    if css:
        widget.add_css_class(css)
    return widget

def box(vertical=True, spacing=10):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL, spacing=spacing)

class App(Gtk.Application):
    def __init__(self, client=None, autostart=True):
        super().__init__(application_id='org.simpleapps.Simpletag')
        self.client = client or Client()
        self.autostart = autostart
        self.started = False
        self.hide_on_connect = False
        self.working = False
        self.connected = False
        self.snapshot = {'groups': [], 'busy': False}
        self.last_rows = None
        self.closed = False
        self.closing_requested = False
        self.allow_close = False
        self.bindings = KeyBindings('simpletag')
        self.connect('activate', self.activate)

    def activate(self, *_):
        if self.get_active_window():
            self.win.present()
            return
        settings = preferences()
        self.settings = settings
        self.win = Gtk.ApplicationWindow(application=self, title='Simpletag')
        self.win.set_default_size(max(720, min(1600, int(settings['width']))), max(480, min(1000, int(settings['height']))))
        attach(self.win)
        self.win.connect('close-request', self.close)
        root = box();root.add_css_class('root');self.win.set_child(root)
        root.append(label('Simpletag', 'title'))
        root.append(label('Folder tagging · Picard settings', 'muted'))
        toolbar = box(False, 6)
        root.append(toolbar)
        self.buttons = {}
        for action, name in [('load','Folder'),('lookup','Lookup'),('scan','Scan'),('save','Save'),('remove','Remove'),('picard','Picard')]:
            caption = name + ' · ' + self.bindings.label(action)
            button = Gtk.Button(label=caption)
            button.connect('clicked', lambda _, a=action: self.perform(a))
            tips = {
                'load': 'Load a folder using Simplefiles',
                'lookup': 'Look up all unmatched folders currently loaded using existing tags',
                'scan': 'Scan unmatched audio fingerprints',
                'save': 'Save matched tracks and remove successful saves from the list',
                'remove': 'Remove without saving; files stay on disk',
                'picard': 'Open Picard for settings and detailed editing',
            }
            button.set_tooltip_text(tips[action])
            toolbar.append(button);self.buttons[action] = button
        self.search = Gtk.SearchEntry(placeholder_text='Filter albums and folders…')
        self.search.connect('search-changed', lambda *_: self.fill())
        root.append(self.search)
        body = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        body.set_position(340);root.append(body)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class('simple-list')
        self.list.set_activate_on_single_click(False)
        self.list.connect('row-selected', self.selected)
        self.list.connect('row-activated', lambda *_: self.review.grab_focus())
        scroll = Gtk.ScrolledWindow(vexpand=True);scroll.set_child(self.list)
        scroll.set_min_content_width(260);body.set_start_child(scroll)
        self.review = Gtk.Label(xalign=0, yalign=0, wrap=True, selectable=True)
        self.review.set_focusable(True)
        self.review.set_margin_start(0);self.review.set_margin_end(0)
        self.review.set_margin_top(0);self.review.set_margin_bottom(0)
        detail = Gtk.ScrolledWindow(vexpand=True, hexpand=True);detail.set_child(self.review)
        self.detail_card = box()
        self.detail_card.add_css_class('card')
        self.detail_card.set_margin_start(12)
        self.detail_card.append(detail)
        body.set_end_child(self.detail_card)
        self.status = label('Connecting to Picard…', 'muted');root.append(self.status)
        root.append(label('/ search · j/k select · Enter review · Esc leave search / close', 'muted'))
        bind_search(self.win, self.search, self.list, 'simpletag', self.move, lambda: self.review.grab_focus())
        controller = Gtk.EventControllerKey()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect('key-pressed', self.key)
        self.win.add_controller(controller)
        self.win.present();start_search(self.win)
        self.fill();self.update_buttons()
        self.poll()
        self.timer = GLib.timeout_add_seconds(1, self.poll)

    def close(self, *_):
        if not self.allow_close and self.connected and self.settings.get('clear_on_close', True):
            self.closing_requested = True
            self.status.set_text('Closing · waiting for Picard, then clearing without saving…')
            self.update_buttons()
            self.poll()
            return True
        self.closed = True
        if getattr(self, 'timer', None):
            GLib.source_remove(self.timer);self.timer = None
        return False

    def cleared_for_close(self):
        self.allow_close = True
        self.win.close()

    def key(self, _, key, code, state):
        focus = self.win.get_focus()
        editing = isinstance(focus, (Gtk.Editable, Gtk.TextView))
        plain = not (state & Gdk.ModifierType.CONTROL_MASK or state & Gdk.ModifierType.ALT_MASK)
        for action in self.buttons:
            if editing and plain:
                continue
            if self.bindings.matches(action, key, state):
                self.perform(action)
                return True
        # Keep album movement reliable from the list, preview and hidden search.
        # The shared handler owns search policy; this app owns its row selection.
        focus = self.win.get_focus()
        if (focus == self.search or not editing):
            if self.bindings.matches('down', key, state):
                self.move(1)
                if focus == self.search:self.search.grab_focus()
                return True
            if self.bindings.matches('up', key, state):
                self.move(-1)
                if focus == self.search:self.search.grab_focus()
                return True
        return bool(control_key(self.win, key, state))

    def group(self):
        row = self.list.get_selected_row()
        return row.group if row else None

    def move(self, direction):
        row = self.list.get_selected_row()
        index = row.get_index() if row else 0
        target = self.list.get_row_at_index(max(0, index+direction)) or row
        if target:
            self.list.select_row(target);target.grab_focus()

    def fill(self):
        focus = self.win.get_focus()
        restore_focus = focus and (focus == self.list or focus.is_ancestor(self.list))
        chosen = self.group()
        chosen_id = chosen['id'] if chosen else None
        words = self.search.get_text().casefold().split()
        while child := self.list.get_first_child():
            self.list.remove(child)
        target = None
        for group in self.snapshot['groups']:
            if not all(word in (group['title']+' '+group['artist']).casefold() for word in words):
                continue
            row = Gtk.ListBoxRow();row.group = group
            content = box(True, 4)
            for side in ('top','bottom','start','end'):
                getattr(content,'set_margin_'+side)(10)
            content.append(label(group['title'], 'title'))
            content.append(label(group['artist'], 'muted'))
            count = len(group['files'])
            state = (str(group['saveable'])+' ready to save') if group['kind']=='matched' else 'Unmatched'
            if any(f['state']=='error' for f in group['files']):state += ' · Error'
            content.append(label(f'{count} tracks · {state}'))
            row.set_child(content);self.list.append(row)
            if group['id']==chosen_id:target=row
        self.list.select_row(target or self.list.get_row_at_index(0))
        if restore_focus:
            (self.list.get_selected_row() or self.list).grab_focus()
        if not self.group():
            self.review.set_text('Load a folder to begin.\n\nLookup uses existing tags. Scan identifies unmatched audio.\n\nReview the proposed tags before Save & remove. Picard controls artwork, renaming and destination folders.')
        self.update_buttons()

    def selected(self, _, row):
        if not row:
            return
        group = row.group
        lines = [group['title'], group['artist'], '']
        if group['kind']=='matched':
            lines += ['Current tags → Proposed tags', 'Saving uses Picard’s current rename/move and artwork settings.', '']
        for f in group['files']:
            lines.append(Path(f['path']).name + ' · ' + f['state'])
            for field in ('artist','album','title','tracknumber','date'):
                before, after = f['before'][field], f['after'][field]
                if before != after:
                    lines.append(f'  {field.capitalize()}: {before or "—"} → {after or "—"}')
                elif after:
                    lines.append(f'  {field.capitalize()}: {after}')
            if group['kind']=='matched' and not f['saveable']:
                lines.append('  Needs review in Picard; will remain in the list.')
            lines.append('')
        self.review.set_text('\n'.join(lines))
        self.update_buttons()

    def update_buttons(self):
        if not hasattr(self,'buttons'):
            return
        ready = self.connected and not self.working and not self.snapshot['busy'] and not self.closing_requested
        group = self.group()
        self.buttons['load'].set_sensitive(ready)
        self.buttons['lookup'].set_sensitive(bool(ready and any(g['kind']=='unmatched' for g in self.snapshot['groups'])))
        self.buttons['scan'].set_sensitive(bool(ready and group and group['kind']=='unmatched'))
        self.buttons['save'].set_sensitive(bool(ready and group and group['saveable']))
        self.buttons['remove'].set_sensitive(bool(ready and group))

    def request(self, action, callback=None, **arguments):
        if self.working or self.closed:
            return
        self.working = True;self.update_buttons()
        def run():
            try:
                result, error = self.client.request(action, **arguments), None
            except Exception as exc:
                result, error = None, exc
            GLib.idle_add(self.received, action, result, error, callback)
        threading.Thread(target=run, daemon=True).start()

    def received(self, action, result, error, callback):
        self.working = False
        if self.closed:
            return False
        if error:
            if self.closing_requested:
                self.closing_requested = False
                self.status.set_text('Could not clear the work list: '+str(error)+' · close again to retry')
                self.update_buttons()
                return False
            if isinstance(error, OSError):
                self.connected = False
                self.status.set_text('Picard bridge unavailable. Open Picard; enable Simpletag bridge in its plugins.')
                if self.autostart and not self.started:
                    self.open_picard(background=True)
            else:
                self.status.set_text(str(error))
        elif action=='status':
            self.connected = True
            self.snapshot = result
            groups = result['groups']
            if groups != self.last_rows:
                self.last_rows = groups
                self.fill()
            if self.hide_on_connect:
                self.hide_on_connect = False
                self.request('hide', callback=lambda: self.win.present())
            count = sum(len(g['files']) for g in groups)
            self.status.set_text(('Working · ' if result['busy'] else '') + result['message'] + f' · {count} tracks')
            if self.closing_requested:
                self.status.set_text('Closing · waiting for Picard, then clearing without saving…')
                if not result['busy']:
                    self.request('clear', callback=self.cleared_for_close)
        else:
            self.status.set_text('Request accepted · Picard is processing it')
            if callback:callback()
        self.update_buttons()
        return False

    def poll(self):
        self.request('status')
        return not self.closed

    def open_picard(self, background=False):
        if self.connected:
            self.request('show')
            return
        # Launching Picard normally also recovers when its previous process
        # crashed; the command-line SHOW action assumes a live instance.
        command = ['picard']
        if not self.started:self.hide_on_connect = background
        try:
            subprocess.Popen(command, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.started = True
        except OSError:
            self.status.set_text('Picard is not installed. Install Picard 3 and the Simpletag bridge.')

    def perform(self, action):
        if self.closing_requested:
            return
        if action == 'picard':
            self.open_picard();return
        if not self.buttons[action].get_sensitive():
            return
        if action == 'load':
            self.working = True;self.update_buttons()
            def choose():
                try:
                    result = subprocess.run(['simplefiles','--directory',str(Path(self.settings['start_folder']).expanduser())],
                                            capture_output=True,text=True,check=True)
                    folder, error = result.stdout.rstrip('\n'), None
                except (OSError,subprocess.SubprocessError) as exc:
                    folder,error='',str(exc)
                GLib.idle_add(self.chosen,folder,error)
            threading.Thread(target=choose,daemon=True).start()
        elif action == 'lookup':
            self.request(action)
        else:
            group = self.group()
            if group:self.request(action,group=group['id'])

    def chosen(self, folder, error):
        self.working = False
        if self.closed:return False
        if error:self.status.set_text('Could not open Simplefiles: '+error)
        elif folder:self.request('load',folder=folder)
        self.update_buttons()
        return False

if __name__=='__main__':
    if '--setup' in sys.argv:
        bridge = Path(__file__).resolve().parent/'bridge'
        subprocess.run(['picard-cli','--yes','plugins','install','--no-git','--reinstall',str(bridge)],check=True)
        subprocess.run(['picard-cli','plugins','enable','ddfa817f-11b4-44f1-9c61-c365ed103d18'],check=True)
    else:
        App().run(sys.argv)

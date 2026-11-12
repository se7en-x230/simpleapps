#!/usr/bin/env python3
import datetime as dt
from pathlib import Path
import threading
import sys
import os
for shared in (Path(__file__).resolve().parent.parent / 'simple-common',
               Path.home() / '.local/src/simple-common'):
    if (shared / 'simple_ui.py').is_file():
        sys.path.insert(0, str(shared))
        break
from simple_ui import attach, control_key, dialog_keys, KeyBindings
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GLib
from details import details, NOTES
from client import Client, ApiError, CONFIG, CACHE, KEY_URL, read, save, metrics, duration, number


def label(text='', style=None):
    widget = Gtk.Label(label=text, xalign=0)
    if style:
        widget.add_css_class(style)
    return widget


def row(spacing=10):
    return Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)


def column(spacing=10):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)


def button(text, callback):
    widget = Gtk.Button(label=text)
    widget.connect('clicked', lambda *_: callback())
    return widget


class Dashboard(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='com.go7.SimpleGarmin')
        self.bindings = KeyBindings(app="simplegarmin")
        self.day = dt.date.today()
        self.client = Client(read(CONFIG / 'credentials.json').get('key', ''))
        self.busy = False
        self.window = None
        close_action = Gio.SimpleAction.new('close', None)
        close_action.connect('activate', lambda *_: self.close_dashboard())
        self.add_action(close_action)
        self.set_accels_for_action('app.close', ['Escape'])
        self.connect('activate', self.activate)

    def activate(self, *_):
        if self.window:
            self.window.present()
            return
        self.window = Gtk.ApplicationWindow(application=self, title='Garmin Dashboard')
        attach(self.window)
        self.window.add_css_class('simplegarmin')
        self.window.set_default_size(880, 700)
        root = column(16)
        root.add_css_class('root')
        self.window.set_child(root)
        header = row()
        title = column(3)
        title.append(label('Simplegarmin', 'title'))
        self.updated_label = label('Updated — · Garmin sync —', 'status')
        self.updated_label.set_tooltip_text('Dashboard retrieval time and Garmin-reported sync for the selected day. Times are shown in your local timezone.')
        title.append(self.updated_label)
        title.set_hexpand(True)
        header.append(title)
        self.connect_button = button('Connect Garmin · c', self.configure)
        header.append(self.connect_button)
        self.refresh_button = button('Refresh · r', self.refresh)
        header.append(self.refresh_button)
        root.append(header)
        dates = row()
        dates.append(button('‹', lambda: self.move(-1)))
        self.date_label = label()
        self.date_label.set_hexpand(True)
        dates.append(self.date_label)
        self.next_button = button('›', lambda: self.move(1))
        dates.append(self.next_button)
        dates.append(button('Today · t', self.today))
        root.append(dates)
        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.pages = ['Overview', 'Heart', 'Recovery', 'Sleep', 'Stress', 'Breathing']
        switcher = Gtk.StackSwitcher(stack=self.stack)
        switcher.add_css_class('simple-tabs')
        switcher.set_halign(Gtk.Align.CENTER)
        root.append(switcher)
        overview = column(12)
        self.stack.add_titled(overview, 'Overview', 'Overview')
        self.detail_widgets = {}
        for page in self.pages[1:]:
            content = column(14)
            detail_grid = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)
            widgets = []
            for i in range(8):
                card = column(8)
                card.add_css_class('card')
                name = label(style='heading')
                value = label(style='value')
                card.append(name)
                card.append(value)
                detail_grid.attach(card, i % 2, i // 2, 1, 1)
                widgets.append((name, value))
            content.append(detail_grid)
            note = label(NOTES[page], 'status')
            note.set_wrap(True)
            content.append(note)
            self.detail_widgets[page] = widgets
            self.stack.add_titled(content, page, page)
        root.append(self.stack)
        grid = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True, row_homogeneous=True)
        self.cards = []
        for i in range(6):
            card = column(8)
            card.add_css_class('card')
            widgets = [label(style='heading'), label(style='value'), label(style='muted')]
            for widget in widgets:
                card.append(widget)
            self.cards.append(widgets)
            grid.attach(card, i % 3, i // 3, 1, 1)
        overview.append(grid)
        activities = column(8)
        activities.add_css_class('card')
        activities.append(label('ACTIVITIES', 'heading'))
        self.activity_rows = [label(style='muted') for _ in range(3)]
        for widget in self.activity_rows:
            widget.set_ellipsize(3)
            activities.append(widget)
        overview.append(activities)
        self.status = label(style='status')
        self.status.set_wrap(True)
        root.append(self.status)
        footer = row()
        hint = label(f"{self.bindings.label('left')}/{self.bindings.label('right')} Day · {self.bindings.label('up')}/{self.bindings.label('down')} Section · 1–6 Select · r Refresh", 'status')
        hint.set_hexpand(True)
        footer.append(hint)
        footer.append(Gtk.LinkButton(uri='https://connect.garmin.com', label='Garmin Connect ↗'))
        root.append(footer)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.key_pressed)
        self.window.add_controller(keys)
        self.show_day()
        self.window.present()
        self.connect_button.grab_focus()
        self.refresh()

    def close_dashboard(self):
        for window in self.get_windows():
            window.destroy()
        self.window = None
        self.quit()

    def key_pressed(self, controller, key, code, state):
        if key == Gdk.KEY_Escape or self.bindings.matches('cancel', key, state):
            self.close_dashboard()
            return True
        focus = self.window.get_focus()
        while focus:
            if isinstance(focus, (Gtk.Editable, Gtk.TextView)):
                return False
            focus = focus.get_parent()
        if key == Gdk.KEY_q and not state & Gtk.accelerator_get_default_mod_mask():
            self.close_dashboard()
            return True
        result = control_key(self.window, key, state)
        if result is not None:
            return result
        for action, callback in [('left', lambda: self.move(-1)), ('right', lambda: self.move(1)),
                                 ('up', lambda: self.change_section(-1)), ('down', lambda: self.change_section(1))]:
            if self.bindings.matches(action, key, state):
                callback()
                return True
        actions = {**{Gdk.KEY_1 + i: lambda page=page: self.stack.set_visible_child_name(page)
                      for i, page in enumerate(self.pages)},
                   Gdk.KEY_r: self.refresh, Gdk.KEY_c: self.configure, Gdk.KEY_t: self.today,
                   Gdk.KEY_q: self.window.close}
        if key in actions and not state & Gtk.accelerator_get_default_mod_mask():
            actions[key]()
            return True
        return False

    def change_section(self, delta):
        index = self.pages.index(self.stack.get_visible_child_name())
        self.stack.set_visible_child_name(self.pages[(index + delta) % len(self.pages)])

    def move(self, delta):
        self.day = min(self.day + dt.timedelta(days=delta), dt.date.today())
        self.show_day()
        self.refresh()

    def today(self):
        self.day = dt.date.today()
        self.show_day()
        self.refresh()

    def show_day(self):
        self.date_label.set_text(self.day.strftime('%A, %d %B %Y'))
        self.next_button.set_sensitive(self.day < dt.date.today())
        self.render(read(CACHE / (self.day.isoformat() + '.json')), cached=True)

    def render(self, data, cached=False):
        fetched = data.get('fetched')
        updated = dt.datetime.fromtimestamp(fetched).astimezone().strftime('%d %b %H:%M:%S %Z') if fetched else '—'
        summary = data.get('summary')
        sync = summary.get('lastSyncTimestampGMT') if isinstance(summary, dict) else None
        synced = '—'
        if isinstance(sync, str):
            try:
                stamp = dt.datetime.fromisoformat(sync.replace('Z', '+00:00'))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=dt.timezone.utc)
                synced = stamp.astimezone().strftime('%d %b %H:%M %Z')
            except ValueError:
                pass
        prefix = 'Cached update' if cached and fetched else 'Updated'
        self.updated_label.set_text(f'{prefix} {updated} · Garmin sync {synced}')
        for page, values in details(data).items():
            for (name, value), (heading, text) in zip(self.detail_widgets[page], values):
                name.set_text(heading)
                value.set_text(text)
        for widgets, values in zip(self.cards, metrics(data)):
            for widget, value in zip(widgets, values):
                widget.set_text(value)
        activities = data.get('activities', [])
        if not isinstance(activities, list):
            activities = []
        for i, widget in enumerate(self.activity_rows):
            if i < len(activities):
                a = activities[i]
                widget.set_text(f"{a.get('activityName', 'Activity')}   ·   {duration(a.get('duration'))}   ·   {number(a.get('distance') / 1000, ' km') if isinstance(a.get('distance'), (float, int)) else '—'}")
            else:
                widget.set_text(('No activities for this day.' if 'activities' in data else 'Activities appear after connecting and syncing your watch.') if i == 0 else '')
        self.connect_button.set_label('Connection · c' if self.client.key else 'Connect Garmin · c')
        self.refresh_button.set_sensitive(bool(self.client.key) and not self.busy)
        if data.get('fetched'):
            timestamp = dt.datetime.fromtimestamp(data['fetched']).strftime('%d %b, %H:%M')
            status = ('Cached · ' if cached else '') + 'Retrieved ' + timestamp + ' · Values reflect your last watch sync to Garmin Connect.'
            if data.get('errors'):
                status += ' Some data unavailable: ' + ' '.join(data['errors'])
        else:
            status = 'Connect Garmin to see your stats. Sync your watch in the Garmin Connect Android app first.' if not self.client.key else 'No saved data for this day. Refresh to retrieve it from Garmin.'
        self.status.set_text(status)

    def refresh(self):
        if self.busy or not self.client.key:
            return
        self.busy = True
        self.refresh_button.set_sensitive(False)
        self.status.set_text('Retrieving data from Garmin…')
        day, client = self.day.isoformat(), self.client
        def work():
            try:
                data = client.fetch(day)
                save(CACHE / (day + '.json'), data)
                error = None
            except (ApiError, OSError, ValueError, TypeError):
                import sys
                exc = sys.exc_info()[1]
                data, error = None, str(exc) if isinstance(exc, ApiError) else 'Could not read or save Garmin data.'
            GLib.idle_add(done, data, error)
        def done(data, error):
            self.busy = False
            if self.window is None:
                return False
            self.refresh_button.set_sensitive(bool(self.client.key))
            if client is not self.client or day != self.day.isoformat():
                self.refresh()
                return False
            if data:
                self.render(data)
            else:
                self.show_day()
                self.status.set_text(error + ' Showing saved data if available.')
            return False
        threading.Thread(target=work, daemon=True).start()

    def configure(self):
        dialog = Gtk.Window(title='Connect Garmin', transient_for=self.window, modal=True)
        dialog.add_css_class('simplegarmin')
        dialog_keys(dialog)
        dialog.set_default_size(480, 260)
        content = column(14)
        content.add_css_class('root')
        content.append(label('Connect your Garmin account', 'title'))
        explanation = label('Create a Personal API key in Garmin Connect, then paste it below. The key is stored privately on this computer.')
        explanation.set_wrap(True)
        content.append(explanation)
        content.append(Gtk.LinkButton(uri=KEY_URL, label='Create a Garmin Personal API key ↗'))
        entry = Gtk.PasswordEntry(show_peek_icon=True)
        entry.set_hexpand(True)
        content.append(entry)
        message = label(style='status')
        content.append(message)
        actions = row()
        actions.append(button('Cancel', dialog.close))
        def connect():
            key = entry.get_text().strip()
            if not key or any(c.isspace() for c in key):
                message.set_text('Paste the complete API key without spaces.')
                return
            try:
                save(CONFIG / 'credentials.json', {'key': key})
            except OSError:
                message.set_text('Could not save the key locally.')
                return
            self.client = Client(key)
            dialog.close()
            self.show_day()
            self.refresh()
        actions.append(button('Save & connect', connect))
        content.append(actions)
        dialog.set_child(content)
        dialog.present()
        entry.grab_focus()


if __name__ == '__main__':
    Dashboard().run()

"""Keyboard reference tabs, using the shared C search/navigation policy."""
import sys
import subprocess
from gi.repository import Gio
from pathlib import Path
from layout import App as LayoutApp, Gtk, Gdk, box, text
from simple_ui import attach, bind_search, start_search, set_search as shared_search
from simple_keyboard import control_key
from launchers import launch_rows
from wm_config import settings
from reference import app_rows
from main import more_keys, shortcut_order


class App(LayoutApp):
    def activate(self, *args):
        if self.get_active_window():
            self.win.present()
            return
        self.source_error = ''
        try:
            self.layout_enabled = settings()['keyboard']
        except Exception as exc:
            self.layout_enabled = False
            self.source_error = str(exc)
        self.ready = False
        super().activate(*args)
        attach(self.win)
        self.win.add_css_class('keyboard-reference')
        self.readability_css = Gtk.CssProvider()
        self.readability_css.load_from_path(str(Path(__file__).resolve().parent.parent/'dashboard.css'))
        Gtk.StyleContext.add_provider_for_display(self.win.get_display(), self.readability_css, Gtk.STYLE_PROVIDER_PRIORITY_USER+3)
        self.win.set_title('Keyboard & shortcuts')
        old = self.root
        self.win.set_child(None)
        outer = box(True, 10)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(outer, 'set_margin_'+side)(20)
        self.win.set_child(outer)
        self.app_title = text('Keyboard & shortcuts')
        self.app_title.add_css_class('title')
        self.app_title.set_halign(Gtk.Align.START)
        outer.append(self.app_title)
        self.pages = Gtk.Stack(vexpand=True)
        self.pages.add_css_class('reference-content')
        # Keep the layout controls, with one common title above both tabs.
        old.get_first_child().get_first_child().set_visible(False)
        switcher = Gtk.StackSwitcher(stack=self.pages)
        switcher.add_css_class('simple-tabs')
        switcher.set_halign(Gtk.Align.CENTER)
        outer.append(switcher)
        outer.append(self.pages)
        self.keypage = box(True, 12)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(self.keypage, 'set_margin_'+side)(20)
        self.pages.add_titled(self.keypage, 'keys', 'Keybinds')
        if self.layout_enabled:
            self.pages.add_titled(old, 'layout', 'Keyboard layout')
        else:
            switcher.set_visible(False)
        self.keysearch = Gtk.SearchEntry(placeholder_text='Find an app, action or shortcut…')
        self.keypage.append(self.keysearch)
        self.back = Gtk.Button(label='Back to apps')
        self.back.set_halign(Gtk.Align.START)
        self.back.connect('clicked', lambda *_: self.show_overview())
        self.keypage.append(self.back)
        self.sort_mode = 'key'
        self.search_started = False
        self.keylist = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.keylist.add_css_class('shortcut-list')
        self.keylist.set_activate_on_single_click(False)
        self.keylist.connect('row-activated', lambda *_: self.launch_selected())
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.keylist)
        self.keypage.append(scroll)
        self.keyhint = text('Ctrl+J/K select · Enter launch · Ctrl+H/L tabs · Esc close')
        self.keyhint.add_css_class('muted')
        self.keypage.append(self.keyhint)
        self.references = app_rows()
        self.overview = []
        targets = {}
        try:
            launches = launch_rows(targets=targets)
        except Exception as exc:
            self.source_error = str(exc)
            launches = {}
        for name, keys in launches.items():
            app, _, purpose = name.partition(' — ')
            more = more_keys(app, self.references) if app.lower().startswith('simple') else ({}, {})
            label = purpose if app == 'Simplepicker' and purpose else name
            shortcut = ' / '.join(keys)
            title = label+'  ·  '+('No shortcut' if shortcut.startswith('No dedicated shortcut') else shortcut)
            subtitle = name if not shortcut.startswith('No dedicated shortcut') else shortcut.partition(' · ')[2]
            if more[0]:
                subtitle += ' · Ctrl+I: more keys'
            self.overview.append((title[:1].upper()+title[1:], subtitle, keys, more, targets.get(name)))
        self.keysearch.connect('search-changed', lambda *_: self.fill())
        self.keysearch.connect('changed', lambda *_: self.fill())
        self.ready = True
        bind_search(self.win, self.keysearch, self.keylist, 'simplepicker/keyboard', self.move_result, self.launch_selected)
        self.pages.connect('notify::visible-child-name', self.tab_changed)
        self.show_overview()
        self.pages.set_visible_child_name('layout' if '--layout' in sys.argv and self.layout_enabled else 'keys')
        self.tab_changed()

    def focus_layer_tab(self):
        if getattr(self, 'tabbuttons', None):
            super().focus_layer_tab()

    def tab_changed(self, *_):
        if self.pages.get_visible_child_name() == 'keys':
            if not self.search_started:
                start_search(self.win)
                self.search_started = True
            elif self.keysearch.get_visible():
                self.keysearch.grab_focus()
            else:
                self.focus_results()
        else:
            self.focus_layer_tab()

    def show_overview(self):
        self.in_details = False
        self.entries = self.overview
        self.back.set_visible(False)
        self.keysearch.set_text('')
        self.fill()
        self.set_search(False)

    def focus_results(self):
        row = self.keylist.get_selected_row()
        (row or self.keylist).grab_focus()

    def set_search(self, visible):
        shared_search(self.win, visible)

    def sort(self, mode):
        self.sort_mode = mode
        self.fill()

    def fill(self):
        if not self.ready or not hasattr(self, 'entries'):
            return
        focus = self.win.get_focus()
        restore_focus = focus and (focus == self.keylist or focus.is_ancestor(self.keylist))
        old = self.keylist.get_selected_row()
        selected = old.entry if old else None
        while child := self.keylist.get_first_child():
            self.keylist.remove(child)
        entries = list(self.entries)
        if not self.in_details:
            entries.sort(key=lambda row: row[0].casefold() if self.sort_mode == 'name' else (shortcut_order(row[2]), row[0].casefold()))
        words = self.keysearch.get_text().casefold().split()
        selected_row = None
        for entry in entries:
            if not all(word in (entry[0]+' '+entry[1]).casefold() for word in words):
                continue
            row = Gtk.ListBoxRow()
            row.entry = entry
            content = box(True, 3)
            for side in ('top', 'bottom', 'start', 'end'):
                getattr(content, 'set_margin_'+side)(8)
            title = text(entry[0]);title.add_css_class('shortcut-title');content.append(title)
            subtitle = text(entry[1]);subtitle.add_css_class('muted');content.append(subtitle)
            row.set_child(content)
            self.keylist.append(row)
            if entry == selected:
                selected_row = row
        self.keylist.select_row(selected_row or self.keylist.get_row_at_index(0))
        if restore_focus:
            self.focus_results()
        hint = ('Alt+Left back · Ctrl+J/K select · Ctrl+H/L tabs · Esc close' if self.in_details else
                'Sort: '+self.sort_mode+' · Ctrl+N name · Ctrl+S key · Ctrl+H/L tabs · / search · Enter launch · Esc close')
        self.keyhint.set_text(self.source_error or (hint if self.keylist.get_row_at_index(0) else 'No matching apps or shortcuts'))

    def move_result(self, direction):
        row = self.keylist.get_selected_row()
        index = row.get_index() if row else -1
        target = self.keylist.get_row_at_index(max(0, index+direction))
        if target:
            self.keylist.select_row(target)
            target.grab_focus()

    def launch_selected(self):
        row = self.keylist.get_selected_row()
        if self.in_details or not row:
            return
        target = row.entry[4]
        if target:
            self.start_target(target)

    def start_target(self, target):
        kind, command = target
        try:
            if kind == 'argv':
                subprocess.Popen(command, start_new_session=True)
                self.win.close()
            else:
                argv = ['mmsg', 'dispatch', command] if kind == 'dispatch' else command
                process = Gio.Subprocess.new(argv,
                                            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE)
                def finished(proc, result):
                    try:
                        _, _, error = proc.communicate_utf8_finish(result)
                        if proc.get_successful():
                            self.win.close()
                        else:
                            self.keyhint.set_text('Could not open: '+(error.strip() or 'Desktop rejected the action'))
                    except Exception as exc:
                        self.keyhint.set_text('Could not open: '+str(exc))
                process.communicate_utf8_async(None, None, finished)
        except Exception as exc:
            self.keyhint.set_text('Could not open: '+str(exc))

    def open_details(self):
        row = self.keylist.get_selected_row()
        if self.in_details or not row or not row.entry[3][0]:
            return
        labels, descriptions = row.entry[3]
        self.in_details = True
        self.entries = [(label, descriptions[key], [], ({}, {}), None) for key, label in labels.items()]
        self.back.set_visible(True)
        self.keysearch.set_text('')
        self.fill()
        self.set_search(False)

    def key(self, controller, key, code, state):
        if not getattr(self, 'ready', False):
            return super().key(controller, key, code, state)
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if ctrl and key in (Gdk.KEY_h, Gdk.KEY_l) and self.layout_enabled:
            self.pages.set_visible_child_name('keys' if key == Gdk.KEY_h else 'layout')
            return True
        if ctrl and key in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab) and self.layout_enabled:
            self.pages.set_visible_child_name('layout' if self.pages.get_visible_child_name() == 'keys' else 'keys')
            return True
        if self.pages.get_visible_child_name() != 'keys':
            return super().key(controller, key, code, state)
        if state & Gdk.ModifierType.ALT_MASK and key == Gdk.KEY_Left:
            self.show_overview();return True
        if ctrl and key == Gdk.KEY_i:
            self.open_details();return True
        if ctrl and key in (Gdk.KEY_n, Gdk.KEY_s) and not self.in_details:
            self.sort('name' if key == Gdk.KEY_n else 'key');return True
        handled = control_key(self.win, key, state)
        if handled is not None:
            return handled
        return False

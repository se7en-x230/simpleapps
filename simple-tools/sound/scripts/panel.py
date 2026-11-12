#!/usr/bin/env python3
import os as _path_os, sys as _path_sys
from pathlib import Path as _Path
_roots=[_Path(__file__).resolve().parents[3],_Path(_path_os.environ.get('XDG_DATA_HOME',_Path.home()/'.local/share')),_Path.home()/'.local/src']
if _path_os.environ.get('SIMPLE_SOURCE_ROOT'):_roots.insert(0,_Path(_path_os.environ['SIMPLE_SOURCE_ROOT']))
for _root in reversed(_roots):
    for _name in ('simplepicker/python','simple-common'):
        if (_root/_name).is_dir():_path_sys.path.insert(0,str(_root/_name))
import sys as _theme_sys
from pathlib import Path as _ThemePath
from theme_loader import load_css as _load_simple_css
"""Small on-demand GTK sound controls for the existing PipeWire/Pulse server."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib
from navigation import install_navigation, HINT


def pactl(*args):
    result = subprocess.run(['pactl', *map(str, args)], capture_output=True, text=True, timeout=4)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Audio service unavailable')
    return result.stdout.strip()


def snapshot():
    data = {k: json.loads(pactl('-f', 'json', 'list', k)) for k in
            ('sinks', 'sources', 'sink-inputs', 'source-outputs', 'cards')}
    info = json.loads(pactl('-f', 'json', 'info'))
    data['output'] = info.get('default_sink_name', '')
    data['input'] = info.get('default_source_name', '')
    return data


def percent(device):
    values = [v.get('value', 0) for v in device.get('volume', {}).values()]
    return round(sum(values) / len(values) / 65536 * 100) if values else 0


def microphones(data):
    return [d for d in data['sources'] if not d['name'].endswith('.monitor')
            and d.get('properties', {}).get('device.class') != 'monitor']


def use_device(data, kind, name):
    old = data['output' if kind == 'sink' else 'input']
    devices = data['sinks' if kind == 'sink' else 'sources']
    previous = next((d['index'] for d in devices if d['name'] == old), None)
    pactl('set-default-' + kind, name)
    streams = data['sink-inputs' if kind == 'sink' else 'source-outputs']
    errors = []
    for stream in streams:
        if stream.get(kind) == previous:
            try:
                pactl('move-' + ('sink-input' if kind == 'sink' else 'source-output'), stream['index'], name)
            except RuntimeError as error:
                errors.append(str(error))
    if errors:
        raise RuntimeError('Default device changed; some streams could not move: ' + '; '.join(errors))


def box(vertical=True, spacing=10):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL, spacing=spacing)


def label(text, css=None):
    widget = Gtk.Label(label=text, xalign=0, wrap=True)
    if css:
        widget.add_css_class(css)
    return widget


class Sound(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='com.go7.SimpleSound')
        self.connect('activate', self.activate)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.window = None
        self.closed = False
        self.busy = False
        self.jobs = 0
        self.pending = {}
        self.readouts = []
        self.signature = None
        self.timer = 0

    def activate(self, app):
        if self.window:
            self.window.present()
            return
        self.window = Gtk.ApplicationWindow(application=self, title='Sound')
        self.window.add_css_class('simple-sound')
        self.window.set_decorated(False)
        display = Gdk.Display.get_default()
        monitor = display.get_monitors().get_item(0)
        rect = monitor.get_geometry()
        self.window.set_default_size(min(800, rect.width-64), min(640, rect.height-80))
        css = Gtk.CssProvider()
        _load_simple_css(css,str(Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'simplepicker/dashboard/info.css'))
        Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_USER+3)
        body = box(spacing=14); body.add_css_class('sound-body'); self.window.set_child(body)
        heading = box(False); title = label('Sound', 'sound-title'); title.set_hexpand(True); heading.append(title)
        bluetooth = Gtk.Button(label='Bluetooth', tooltip_text='Open Bluetooth devices')
        bluetooth.connect('clicked', self.open_bluetooth); heading.append(bluetooth)
        refresh = Gtk.Button(label='Refresh', tooltip_text='Refresh devices')
        refresh.connect('clicked', lambda *_: self.refresh())
        body.append(heading)
        self.error = label('', 'sound-error'); self.error.set_visible(False); body.append(self.error)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.NONE)
        switch = box(False); body.append(switch)
        body.append(label('Outputs, microphones and application volume', 'sound-hint'))
        first_tab = None
        self.pages = {}
        for key, title in [('outputs','Outputs'),('inputs','Microphones'),('apps','Applications'),('devices','Devices')]:
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
            content = box(spacing=12); scroll.set_child(content); self.pages[key] = content
            self.stack.add_titled(scroll, key, title)
            tab = Gtk.ToggleButton(label=title)
            if first_tab: tab.set_group(first_tab)
            else: first_tab = tab
            tab.connect('toggled', lambda button, page=key: self.stack.set_visible_child_name(page) if button.get_active() else None)
            switch.append(tab)
        switch.append(refresh); first_tab.set_active(True)
        body.append(self.stack); self.stack.set_vexpand(True)
        body.append(label(HINT, 'sound-hint'))
        install_navigation(self.window,self.refresh,header=first_tab)
        keys = Gtk.EventControllerKey(); keys.connect('key-pressed', self.key); self.window.add_controller(keys)
        self.window.connect('close-request', self.close)
        self.window.present(); self.refresh(); self.timer = GLib.timeout_add_seconds(3, self.refresh)

    def key(self, controller, keyval, code, state):
        if self.window._vim_navigation.keys.matches("cancel",keyval,state):
            self.window.close(); return True
        return False

    def open_bluetooth(self, *_):
        helper = 'simple-network'
        try:
            subprocess.Popen([str(helper), 'bt'], start_new_session=True)
        except OSError as error:
            self.error.set_text(str(error)); self.error.set_visible(True)
            return
        self.window.close()

    def close(self, *_):
        self.closed = True
        if self.timer: GLib.source_remove(self.timer)
        for timer in self.pending.values(): GLib.source_remove(timer)
        self.pending.clear(); self.pool.shutdown(wait=False, cancel_futures=True)
        return False

    def submit(self, action=None):
        if self.closed: return
        self.busy = True
        self.jobs += 1
        def work():
            error = None
            try:
                if action: action()
            except Exception as exc: error = str(exc)
            try: data = snapshot()
            except Exception as exc: return None, str(exc)
            return data, error
        future = self.pool.submit(work)
        future.add_done_callback(lambda f: GLib.idle_add(self.received, f.result()) if not f.cancelled() else None)

    def refresh(self):
        if not self.closed and not self.busy and not self.pending: self.submit()
        return not self.closed

    def received(self, result):
        if self.closed: return False
        data, error = result; self.jobs -= 1; self.busy = self.jobs > 0
        if self.busy: return False
        self.error.set_text(error or ''); self.error.set_visible(bool(error))
        if data is None: return False
        self.data = data
        # Rebuild only when devices/routes change; volume refreshes preserve slider focus.
        topology = {k: [{a: v for a, v in d.items() if a not in ('volume','mute','latency','state','buffer_latency_usec','sink_latency_usec','source_latency_usec')} for d in data[k]] for k in ('sinks','sources','sink-inputs','cards')}
        signature = json.dumps([topology, data['output'], data['input']], sort_keys=True)
        if signature != self.signature and not self.pending:
            self.signature = signature; self.render()
        if not self.pending:
            for group, index, scale, handler, caption, mute in self.readouts:
                item = next((d for d in data[group] if d['index'] == index), None)
                if item:
                    scale.handler_block(handler); scale.set_value(min(100,percent(item))); scale.handler_unblock(handler)
                    caption.set_text(str(percent(item))+'%')
                    mute.set_label('Unmute' if item.get('mute') else 'Mute')
        return False

    def change_volume(self, scale, kind, index, caption):
        value = round(scale.get_value()); caption.set_text(str(value)+'%'); key = (kind,index)
        if key in self.pending: GLib.source_remove(self.pending[key])
        def apply():
            self.pending.pop(key,None)
            self.submit(lambda: pactl('set-'+kind+'-volume', index, str(value)+'%'))
            return False
        self.pending[key] = GLib.timeout_add(140,apply)

    def button(self, text, action):
        button = Gtk.Button(label=text); button.connect('clicked', lambda *_: self.submit(action)); return button

    def dropdown(self, choices, selected, action):
        names = [n for n,_ in choices]
        widget = Gtk.DropDown.new_from_strings([title for _,title in choices])
        widget.set_hexpand(True)
        widget.set_selected(names.index(selected) if selected in names else Gtk.INVALID_LIST_POSITION)
        def changed(drop, _):
            index = drop.get_selected()
            if index < len(names): self.submit(lambda: action(names[index]))
        widget.connect('notify::selected', changed)
        return widget

    def device_row(self, page, item, kind, group, default=None):
        card = box(); card.add_css_class('sound-card'); header = box(False)
        icon = Gtk.Image.new_from_icon_name('audio-input-microphone-symbolic' if kind=='source' else 'audio-speakers-symbolic'); icon.add_css_class('sound-icon'); header.append(icon)
        props = item.get('properties', {})
        title = label(item.get('description') or props.get('application.name') or 'Application'); title.set_hexpand(True); header.append(title)
        if default is not None:
            selected = item['name']==default
            button=self.button('Selected' if selected else 'Use device', lambda: use_device(self.data,kind,item['name']))
            button.set_sensitive(not selected); header.append(button)
        card.append(header)
        row = box(False)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,100,1); scale.set_hexpand(True); scale.set_draw_value(False); scale.set_value(min(100,percent(item)))
        caption = label(str(percent(item))+'%'); caption.set_width_chars(4)
        handler=scale.connect('value-changed',self.change_volume,kind,item['index'],caption)
        row.append(scale);row.append(caption)
        mute=self.button('Unmute' if item.get('mute') else 'Mute',lambda:pactl('set-'+kind+'-mute',item['index'],'toggle'));row.append(mute);card.append(row)
        self.readouts.append((group,item['index'],scale,handler,caption,mute))
        if kind=='sink-input':
            choices=[(str(d['index']),d['description']) for d in self.data['sinks']]
            if choices: card.append(self.dropdown(choices,str(item['sink']),lambda target:pactl('move-sink-input',item['index'],target)))
        else:
            ports=item.get('ports',[])
            choices=[(p['name'],p.get('description',p['name'])) for p in ports if p.get('availability')!='not available']
            if len(choices)>1: card.append(self.dropdown(choices,item.get('active_port'),lambda port:pactl('set-'+kind+'-port',item['name'],port)))
        self.pages[page].append(card)

    def render(self):
        self.readouts=[]
        for page in self.pages.values():
            while page.get_first_child(): page.remove(page.get_first_child())
        for item in self.data['sinks']: self.device_row('outputs',item,'sink','sinks',self.data['output'])
        for item in microphones(self.data): self.device_row('inputs',item,'source','sources',self.data['input'])
        for item in self.data['sink-inputs']: self.device_row('apps',item,'sink-input','sink-inputs')
        for item in self.data['cards']:
            card=box();card.add_css_class('sound-card')
            card.append(label(item.get('properties',{}).get('device.description',item['name'])))
            choices=[(name,p.get('description',name)) for name,p in item.get('profiles',{}).items() if p.get('available') not in (False,'no') or name==item.get('active_profile')]
            if choices: card.append(self.dropdown(choices,item.get('active_profile'),lambda profile,index=item['index']:pactl('set-card-profile',index,profile)))
            self.pages['devices'].append(card)
        for page in self.pages.values():
            if not page.get_first_child():page.append(label('No devices or active audio streams.', 'sound-hint'))

if __name__ == '__main__':
    if '--check' in sys.argv:
        d=snapshot();print(f"Audio ready: {len(d['sinks'])} outputs, {len(microphones(d))} microphones, {len(d['sink-inputs'])} playback streams")
    else:
        raise SystemExit(Sound().run(sys.argv))

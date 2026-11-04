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
"""On-demand disk cards, using the existing bounded disk-free backend."""
import concurrent.futures
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'sound/scripts'))
from panel import box, label, install_navigation, HINT
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,GLib
from backend import mounted_storage,usage

def collect(all_storage=False):
    mounts=mounted_storage('All mounted storage' if all_storage else 'Local disks')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        return list(zip(mounts,pool.map(usage,mounts)))

class Disk(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='com.go7.SimpleDisk')
        self.connect('activate',self.activate);self.window=None;self.closed=False;self.busy=False
        self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=1)
    def activate(self,app):
        if self.window:self.window.present();return
        self.window=Gtk.ApplicationWindow(application=self,title='Disk space');self.window.set_decorated(False);self.window.add_css_class('simple-sound')
        display=Gdk.Display.get_default();rect=display.get_monitors().get_item(0).get_geometry()
        self.window.set_default_size(min(780,rect.width-64),min(610,rect.height-80))
        provider=Gtk.CssProvider();_load_simple_css(provider,str(Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'simplepicker/dashboard/info.css'))
        Gtk.StyleContext.add_provider_for_display(display,provider,Gtk.STYLE_PROVIDER_PRIORITY_USER+3)
        body=box(spacing=14);body.add_css_class('sound-body');self.window.set_child(body)
        head=box(False);title=label('Disk space','sound-title');title.set_hexpand(True);head.append(title)
        self.scope=Gtk.DropDown.new_from_strings(['Local disks','All mounted storage']);self.scope.connect('notify::selected',lambda *_:self.refresh());head.append(self.scope)
        self.refresh_button=Gtk.Button(icon_name='view-refresh-symbolic',tooltip_text='Refresh');self.refresh_button.connect('clicked',lambda *_:self.refresh());head.append(self.refresh_button)
        close=Gtk.Button(icon_name='window-close-symbolic');close.connect('clicked',lambda *_:self.window.close());head.append(close);body.append(head)
        self.status=label('Reading storage…','sound-hint');body.append(self.status)
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,vexpand=True);self.cards=box(spacing=12);scroll.set_child(self.cards);body.append(scroll)
        body.append(label(HINT,'sound-hint'))
        install_navigation(self.window,self.refresh,header=self.scope)
        keys=Gtk.EventControllerKey();keys.connect('key-pressed',self.key);self.window.add_controller(keys)
        self.window.connect('close-request',self.close);self.window.present();self.refresh()
    def key(self,controller,keyval,code,state):
        if self.window._vim_navigation.keys.matches("cancel",keyval,state):self.window.close();return True
        return False
    def close(self,*_):
        self.closed=True;self.pool.shutdown(wait=False,cancel_futures=True);return False
    def refresh(self):
        if self.busy:return
        self.busy=True;self.refresh_button.set_sensitive(False);self.scope.set_sensitive(False);self.status.set_text('Reading storage…')
        f=self.pool.submit(collect,self.scope.get_selected()==1)
        f.add_done_callback(lambda future:GLib.idle_add(self.received,future) if not future.cancelled() else None)
    def received(self,future):
        if self.closed:return False
        self.busy=False;self.refresh_button.set_sensitive(True);self.scope.set_sensitive(True)
        try:results=future.result()
        except Exception as error:self.status.set_text(str(error));return False
        while self.cards.get_first_child():self.cards.remove(self.cards.get_first_child())
        self.status.set_text(f'{len(results)} mounted filesystems · refreshed just now')
        for mount,(percent,summary,error,details) in results:
            card=box();card.add_css_class('sound-card');head=box(False)
            icon=Gtk.Image.new_from_icon_name('drive-harddisk-symbolic');icon.add_css_class('sound-icon');head.append(icon)
            name=label(mount['target']);name.set_hexpand(True);head.append(name)
            open_button=Gtk.Button(label='Open');open_button.connect('clicked',self.open_folder,mount['target']);head.append(open_button)
            copy=Gtk.Button(label='Copy details');copy.connect('clicked',self.copy_details,'\n'.join(details));head.append(copy);card.append(head)
            if percent>=0:
                bar=Gtk.ProgressBar(fraction=min(1,percent/100),show_text=True,text=f'{percent}% used');card.append(bar)
            card.append(label(summary.split('  |  ',1)[-1],'sound-info'))
            card.append(label(mount['source']+' · '+mount['fstype'],'sound-hint'))
            if error:card.append(label(error,'sound-error'))
            card.set_tooltip_text('\n'.join(details));self.cards.append(card)
        if not results:self.cards.append(label('No mounted storage found.','sound-hint'))
        return False
    def open_folder(self,button,path):
        try:subprocess.Popen(['simple-open','file_manager',path],start_new_session=True)
        except OSError as error:self.status.set_text(str(error))
    def copy_details(self,button,text):
        try:subprocess.run(['wl-copy'],input=text,text=True,check=True,timeout=3);self.status.set_text('Disk details copied')
        except (OSError,subprocess.SubprocessError) as error:self.status.set_text(str(error))

if __name__=='__main__':
    if '--report' in sys.argv:
        print('\n\n'.join('\n'.join(result[3]) for _,result in collect(True)))
    elif '--check' in sys.argv:
        data=collect();assert data;print(f'Disk backend ready: {len(data)} local filesystems')
    else:raise SystemExit(Disk().run(sys.argv))

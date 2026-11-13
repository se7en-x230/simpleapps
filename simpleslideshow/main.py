#!/usr/bin/env python3
"""Small keyboard-driven front end for FFmpeg. GPL-3.0-or-later."""
from pathlib import Path
from dataclasses import asdict
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
for shared in (Path(__file__).resolve().parent.parent/'simple-common',
               Path(__file__).resolve().parents[2]/'lib/simple-common', Path.home()/'.local/lib/simple-common',
               Path.home()/'.local/share/simple-common'):
    if (shared/'simple_ui.py').is_file():sys.path.insert(0,str(shared));break
from simple_ui import attach, control_key, KeyBindings
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio,GLib
from render import Media,probe,plan,Renderer,Cancelled

CONFIG=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'simpleslideshow'
STATE=Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'simpleslideshow'

def box(vertical=True,spacing=10):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,spacing=spacing)
def label(text='',style=None):
    w=Gtk.Label(label=text,xalign=0,wrap=True)
    if style:w.add_css_class(style)
    return w

class App(Gtk.Application):
    def __init__(self,paths=()):
        super().__init__(application_id='space.go7.Simpleslideshow',flags=Gio.ApplicationFlags.NON_UNIQUE)
        CONFIG.mkdir(parents=True,exist_ok=True)
        if not (CONFIG/'keys.ini').exists():
            try:
                with (CONFIG/'keys.ini').open('x') as f:f.write(Path(__file__).with_name('keys.ini').read_text())
            except FileExistsError:pass
        self.keys=KeyBindings('simpleslideshow');self.items=[];self.music=None;self.busy=False;self.renderer=None;self.external=None;self.initial=paths;self.last_exports=();self.cancel_worker=False;self.close_pending=False
        self.connect('activate',self.activate)

    def activate(self,*_):
        if self.get_active_window():self.get_active_window().present();return
        self.win=Gtk.ApplicationWindow(application=self,title='Simpleslideshow');attach(self.win);self.win.set_default_size(1060,760)
        root=box(spacing=14);root.add_css_class('root');self.win.set_child(root)
        root.append(label('Simpleslideshow','title'))
        root.append(label('Images + short clips + music · One soft crossfade · High quality + web MP4','muted'))
        bar=box(False,8);root.append(bar);self.controls=[]
        for name,action,callback in [('Add media','add',self.add),('Music','music',self.choose_music),('Title capture','title',self.capture_title),('Preview item','preview',self.preview),('Export both','export',self.export)]:
            b=Gtk.Button(label=f'{name} · {self.keys.label(action)}');b.connect('clicked',lambda _,fn=callback:fn());bar.append(b);self.controls.append(b)
        self.cancel_button=Gtk.Button(label='Cancel');self.cancel_button.connect('clicked',lambda *_:self.cancel());self.cancel_button.set_visible(False);bar.append(self.cancel_button)
        content=Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL);content.set_vexpand(True);content.set_position(450);root.append(content)
        left=box();left.add_css_class('card');content.set_start_child(left);left.append(label('ORDER · j/k move · Shift+j/k reorder','heading'))
        self.list=Gtk.ListBox();self.list.set_selection_mode(Gtk.SelectionMode.SINGLE);self.list.add_css_class('simple-list');self.list.connect('row-selected',self.selected);self.list.connect('row-activated',lambda *_:self.preview())
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);scroll.set_child(self.list);scroll.set_vexpand(True);left.append(scroll)
        actions=box(False,8);left.append(actions)
        for text,fn in [('↑ Earlier',lambda:self.reorder(-1)),('↓ Later',lambda:self.reorder(1)),('Remove',self.remove)]:
            b=Gtk.Button(label=text);b.connect('clicked',lambda _,f=fn:f());actions.append(b);self.controls.append(b)
        right=box();right.add_css_class('card');content.set_end_child(right)
        self.picture=Gtk.Picture();self.picture.set_can_shrink(True);self.picture.set_content_fit(Gtk.ContentFit.CONTAIN);self.picture.set_vexpand(True);self.picture.set_size_request(240,180);right.append(self.picture)
        self.caption=label('Add photos or video clips to begin.','muted');right.append(self.caption)
        settings=box();root.append(settings)
        musicrow=box(False,10);self.music_label=label('Music · none (silent export)','muted');self.music_label.set_hexpand(True);musicrow.append(self.music_label)
        clear=Gtk.Button(label='Clear music');clear.connect('clicked',lambda *_:self.clear_music());musicrow.append(clear);self.controls.append(clear);settings.append(musicrow)
        timing=box(False,14);settings.append(timing)
        timing.append(label('Seconds / photo'));self.seconds=Gtk.SpinButton.new_with_range(1,60,.5);self.seconds.set_value(4);timing.append(self.seconds)
        self.fit=Gtk.CheckButton(label='Fit images to music · f');timing.append(self.fit)
        self.orientation=Gtk.DropDown.new_from_strings(['Landscape · 16:9','Portrait · 9:16']);timing.append(self.orientation)
        self.summary=label('','status');settings.append(self.summary)
        settings.append(label('Clips keep their length; clip audio is muted. Fixed timing loops/trims music and fades it out.','muted'))
        self.progress=Gtk.ProgressBar();self.progress.set_visible(False);root.append(self.progress)
        self.status=label('Ready. Your draft is saved automatically.','status');root.append(self.status)
        root.append(label('a add · m music · t capture title · j/k select · J/K reorder · x remove · f timing · p preview · e export · Esc cancel/close','muted'))
        for widget,signal in [(self.seconds,'value-changed'),(self.fit,'toggled'),(self.orientation,'notify::selected')]:widget.connect(signal,self.changed)
        controller=Gtk.EventControllerKey();controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE);controller.connect('key-pressed',self.key);self.win.add_controller(controller)
        self.win.connect('close-request',self.close)
        self.load();self.refresh();self.win.present();self.list.grab_focus()
        if self.initial:self.add_paths(self.initial)

    def load(self):
        try:
            data=json.loads((STATE/'draft.json').read_text())
            self.items=[Media(**item) for item in data.get('items',[]) if item.get('kind') in ('image','video')]
            if data.get('music'):self.music=Media(**data['music'])
            self.seconds.set_value(float(data.get('seconds',4)));self.fit.set_active(bool(data.get('fit',False)));self.orientation.set_selected(int(bool(data.get('portrait',False))))
        except (OSError,ValueError,TypeError):pass

    def save(self):
        STATE.mkdir(parents=True,exist_ok=True)
        data={'items':[asdict(i) for i in self.items],'music':asdict(self.music) if self.music else None,'seconds':self.seconds.get_value(),'fit':self.fit.get_active(),'portrait':self.orientation.get_selected()==1}
        with tempfile.NamedTemporaryFile(mode='w',dir=STATE,delete=False) as f:json.dump(data,f,indent=2);temp=Path(f.name)
        temp.replace(STATE/'draft.json')

    def changed(self,*_):
        try:
            p=plan(self.items,self.music,self.fit.get_active(),self.seconds.get_value())
            photo=next((p.frames[i]/30 for i,item in enumerate(self.items) if item.kind=='image'),0)
            self.summary.set_text(f'{len(self.items)} items · {p.seconds:.1f}s total · {photo:.1f}s / photo · {p.fade/30:.1f}s crossfade')
        except ValueError as e:self.summary.set_text(str(e))
        self.seconds.set_sensitive(not self.busy and not self.fit.get_active())
        self.music_label.set_text('Music · '+(Path(self.music.path).name+f' · {self.music.duration:.1f}s' if self.music else 'none (silent export)'))
        try:self.save()
        except OSError as e:self.status.set_text('Could not save draft: '+str(e))

    def index(self):
        row=self.list.get_selected_row();return row.get_index() if row else -1

    def refresh(self,index=0):
        child=self.list.get_first_child()
        while child:
            after=child.get_next_sibling();self.list.remove(child);child=after
        for n,item in enumerate(self.items):
            b=box(spacing=3);b.set_margin_top(8);b.set_margin_bottom(8);b.set_margin_start(8);b.set_margin_end(8)
            name=label(f'{n+1:02}  {Path(item.path).name}');name.set_ellipsize(3);name.set_wrap(False);b.append(name)
            b.append(label(('Image' if item.kind=='image' else f'Video · {item.duration:.1f}s')+(' · missing' if not Path(item.path).exists() else ''),'muted'));self.list.append(b)
        if self.items:self.list.select_row(self.list.get_row_at_index(max(0,min(index,len(self.items)-1))))
        else:self.picture.set_filename(None);self.caption.set_text('Add photos or video clips to begin.')
        self.changed()

    def selected(self,_,row):
        if row is None:return
        item=self.items[row.get_index()];self.picture.set_filename(item.path if item.kind=='image' else None)
        self.caption.set_text(Path(item.path).name+(' · p to play clip' if item.kind=='video' else ''))

    def set_busy(self,value):
        self.busy=value
        for b in self.controls:b.set_sensitive(not value)
        self.fit.set_sensitive(not value);self.orientation.set_sensitive(not value);self.list.set_sensitive(not value)
        self.progress.set_visible(value);self.cancel_button.set_visible(value);self.changed()

    def work(self,fn,done):
        if self.busy:return
        self.cancel_worker=False;self.set_busy(True)
        def worker():
            try:value=fn();error=None
            except Exception as e:value=None;error=e
            GLib.idle_add(finish,value,error)
        def finish(value,error):
            self.renderer=None;self.set_busy(False)
            if error:self.status.set_text(str(error))
            elif not self.cancel_worker:done(value)
            else:self.status.set_text('Cancelled.')
            if self.close_pending:self.win.destroy()
            return False
        threading.Thread(target=worker,daemon=True).start()

    def dialog(self,title,callback,multiple=False,audio=False,save=False):
        if self.busy:return
        dialog=Gtk.FileDialog(title=title)
        if save:
            dialog.set_initial_name('Slideshow-'+datetime.now().strftime('%Y%m%d-%H%M')+'.mp4')
            path=Path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS) or Path.home()/'Videos')
            if path.is_dir():dialog.set_initial_folder(Gio.File.new_for_path(str(path)))
        else:
            f=Gtk.FileFilter();f.set_name('Music' if audio else 'Images and video')
            for mime in (['audio/*'] if audio else ['image/*','video/*']):f.add_mime_type(mime)
            filters=Gio.ListStore.new(Gtk.FileFilter);filters.append(f);dialog.set_filters(filters)
        def finished(obj,result):
            try:
                if save:paths=[obj.save_finish(result).get_path()]
                elif multiple:
                    files=obj.open_multiple_finish(result);paths=[files.get_item(i).get_path() for i in range(files.get_n_items())]
                else:paths=[obj.open_finish(result).get_path()]
                if any(p is None for p in paths):raise ValueError('Choose local files or files on a mounted drive.')
                callback(paths)
            except GLib.Error:pass
            except Exception as e:self.status.set_text(str(e))
        if save:dialog.save(self.win,None,finished)
        elif multiple:dialog.open_multiple(self.win,None,finished)
        else:dialog.open(self.win,None,finished)

    def add(self):self.dialog('Add images or short clips',self.add_paths,True)
    def add_paths(self,paths,intro=False):
        def read():
            found=[];errors=[]
            for p in paths:
                if self.cancel_worker:break
                try:found.append(probe(p))
                except Exception as e:errors.append(str(e))
            return found,errors
        def done(value):
            items,errors=value
            if intro:self.items[0:0]=items
            else:self.items.extend(items)
            self.refresh(0 if intro else max(0,len(self.items)-len(items)));self.status.set_text('; '.join(errors) if errors else f'Added {len(items)} item(s).')
        self.work(read,done)

    def choose_music(self):
        self.dialog('Choose one music track',lambda paths:self.work(lambda:probe(paths[0],True),self.music_loaded),audio=True)
    def music_loaded(self,music):self.music=music;self.changed();self.status.set_text('Music loaded.')
    def clear_music(self):
        if self.busy:return
        self.music=None;self.fit.set_active(False);self.changed()
    def remove(self):
        if self.busy:return
        i=self.index()
        if i>=0:self.items.pop(i);self.refresh(i)
    def reorder(self,step):
        if self.busy:return
        i=self.index();j=i+step
        if i>=0 and 0<=j<len(self.items):self.items[i],self.items[j]=self.items[j],self.items[i];self.refresh(j);self.list.grab_focus()
    def move(self,step):
        if self.items:self.list.select_row(self.list.get_row_at_index((max(0,self.index())+step)%len(self.items)));self.list.grab_focus()
    def preview(self):
        if self.busy:return
        i=self.index()
        if i>=0:
            try:subprocess.Popen(['mpv','--',self.items[i].path] if self.items[i].kind=='video' and shutil.which('mpv') else ['xdg-open',self.items[i].path],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            except OSError as e:self.status.set_text(str(e))
    def capture_title(self):
        if self.busy:return
        if not shutil.which('simplecapture'):self.status.set_text('Install Simplecapture for grim/slurp + Swappy title capture. You can also add any title image.');return
        self.win.set_visible(False)
        def capture():
            process=subprocess.Popen(['simplecapture','--region','--edit','--save','--no-copy','--print-path'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
            self.external=process
            try:
                if self.cancel_worker:os.killpg(process.pid,signal.SIGTERM)
                stdout,stderr=process.communicate()
            finally:self.external=None
            if self.cancel_worker:return None
            if process.returncode:raise ValueError(stderr.strip() or 'Title capture failed.')
            path=stdout.strip()
            return probe(path) if path else None
        def done(item):
            self.win.present()
            if item:self.items.insert(0,item);self.refresh();self.status.set_text('Title image added first. Use Shift+j/k to reorder.')
            else:self.status.set_text('Title capture cancelled.')
        # Always restore the window, including when the external tool fails.
        def wrapped():
            try:return capture()
            finally:GLib.idle_add(self.win.present)
        self.work(wrapped,done)
    def export(self):
        if self.busy:return
        try:plan(self.items,self.music,self.fit.get_active(),self.seconds.get_value())
        except ValueError as e:self.status.set_text(str(e));return
        self.dialog('Export high-quality and web MP4s',self.export_to,save=True)
    def export_to(self,paths):
        try:p=plan(self.items,self.music,self.fit.get_active(),self.seconds.get_value())
        except ValueError as e:self.status.set_text(str(e));return
        portrait=self.orientation.get_selected()==1;renderer=Renderer()
        def progress(fraction,message):
            def update():self.progress.set_fraction(fraction);self.status.set_text(message);return False
            GLib.idle_add(update)
        def run():
            self.renderer=renderer
            if self.cancel_worker:renderer.cancel();raise Cancelled('Export cancelled.')
            # Refresh duration information in case source files changed since import.
            items=[probe(item.path) for item in p.items];music=probe(p.music.path,True) if p.music else None
            fresh=plan(items,music,p.fit,self.seconds_value)
            return renderer.export_pair(fresh,paths[0],progress,portrait)
        def done(exports):self.last_exports=exports;self.status.set_text('Saved: '+exports[0].name+' + '+exports[1].name)
        self.seconds_value=self.seconds.get_value();self.work(run,done)
    def cancel(self):
        self.cancel_worker=True
        if self.renderer:self.renderer.cancel()
        if self.external and self.external.poll() is None:
            try:os.killpg(self.external.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        self.status.set_text('Cancelling…')
    def close(self,*_):
        if self.busy:
            self.close_pending=True;self.cancel();return True
        self.save();return False
    def key(self,_,key,code,state):
        focus=self.win.get_focus()
        editing=isinstance(focus,(Gtk.Editable,Gtk.TextView))
        if self.keys.matches('cancel',key,state):
            if self.busy:self.cancel()
            elif editing:self.list.grab_focus()
            else:self.win.close()
            return True
        if self.busy:return False
        if editing and not state&Gdk.ModifierType.CONTROL_MASK:return False
        for action,callback in [('add',self.add),('music',self.choose_music),('clear_music',self.clear_music),('title',self.capture_title),('export',self.export),('remove',self.remove),('move_up',lambda:self.reorder(-1)),('move_down',lambda:self.reorder(1)),('fit',lambda:self.fit.set_active(not self.fit.get_active())),('quit',self.win.close)]:
            if self.keys.matches(action,key,state):callback();return True
        if self.keys.matches('preview',key,state) and (key not in (Gdk.KEY_Return,Gdk.KEY_KP_Enter) or self.list.has_focus() or isinstance(focus,Gtk.ListBoxRow)):
            self.preview();return True
        if self.keys.matches('down',key,state):self.move(1);return True
        if self.keys.matches('up',key,state):self.move(-1);return True
        return bool(control_key(self.win,key,state))

if __name__=='__main__':
    app=App(sys.argv[1:]);raise SystemExit(app.run([sys.argv[0]]))

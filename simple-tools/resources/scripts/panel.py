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
"""Small on-demand CPU and memory views. Read-only Linux procfs sampling."""
import os,sys,time,concurrent.futures
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'sound/scripts'))
from panel import box,label,install_navigation,HINT
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,GLib

def read_sample():
    cpus={}
    for line in Path('/proc/stat').read_text().splitlines():
        parts=line.split()
        if parts and parts[0].startswith('cpu'):
            v=list(map(int,parts[1:9]));cpus[parts[0]]=(sum(v),v[3]+v[4])
    mem={k:int(v.split()[0])*1024 for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
    processes={};page=os.sysconf('SC_PAGE_SIZE')
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            raw=(path/'stat').read_text();end=raw.rfind(')');v=raw[end+2:].split()
            processes[int(path.name)]=(raw[raw.find('(')+1:end],int(v[11])+int(v[12]),int(v[21])*page)
        except (OSError,ValueError,IndexError):continue
    return time.monotonic(),cpus,mem,processes

def human(n):return f'{n/1024**3:.1f} GiB' if n>=1024**3 else f'{n/1024**2:.0f} MiB'
def cpu_usage(now,old):
    total=now[0]-old[0];return max(0,min(100,100*(total-(now[1]-old[1]))/total)) if total>0 else 0

class Resources(Gtk.Application):
    def __init__(self,kind):
        super().__init__(application_id='com.go7.Simple'+kind.title());self.kind=kind;self.window=None;self.closed=False;self.busy=False;self.previous=None;self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=1);self.connect('activate',self.activate)
    def activate(self,*_):
        if self.window:self.window.present();return
        title='CPU' if self.kind=='cpu' else 'Memory'
        self.window=Gtk.ApplicationWindow(application=self,title=title);self.window.set_decorated(False);self.window.add_css_class('simple-sound')
        display=Gdk.Display.get_default();rect=display.get_monitors().get_item(0).get_geometry();self.window.set_default_size(min(780,rect.width-64),min(660,rect.height-80))
        css=Gtk.CssProvider();_load_simple_css(css,str(_Path(_path_os.environ.get('XDG_CONFIG_HOME',_Path.home()/'.config'))/'simplepicker/dashboard/info.css'));Gtk.StyleContext.add_provider_for_display(display,css,Gtk.STYLE_PROVIDER_PRIORITY_USER+3)
        body=box(spacing=14);body.add_css_class('sound-body');self.window.set_child(body)
        head=box(False);name=label(title,'sound-title');name.set_hexpand(True);head.append(name)
        close=Gtk.Button(icon_name='window-close-symbolic');close.connect('clicked',lambda *_:self.window.close());head.append(close);body.append(head)
        self.status=label('Reading usage…','sound-hint');body.append(self.status)
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,vexpand=True);self.content=box(spacing=12);scroll.set_child(self.content);body.append(scroll)
        self.summary=box();self.summary.add_css_class('sound-card');self.content.append(self.summary)
        self.main=label('Reading…');self.summary.append(self.main);self.bar=Gtk.ProgressBar();self.summary.append(self.bar)
        self.details=label('','sound-hint');self.summary.append(self.details)
        self.cores={}
        if self.kind=='cpu':
            model=next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),'Processor');self.details.set_text(model)
            grid=Gtk.Grid(column_spacing=18,row_spacing=8);grid.add_css_class('sound-card');self.content.append(grid)
            for i in range(os.cpu_count() or 1):
                row=box(False);row.append(label(str(i+1),'sound-hint'));bar=Gtk.ProgressBar(show_text=True,text='…',hexpand=True);row.append(bar);grid.attach(row,i%2,i//2,1,1);self.cores['cpu'+str(i)]=bar
        self.process=box();self.process.add_css_class('sound-card');self.content.append(self.process)
        self.process.append(label('Top processes · CPU' if self.kind=='cpu' else 'Top processes · resident memory','sound-hint'))
        self.rows=[]
        for _ in range(8):
            row=box(False);name=label('');name.set_hexpand(True);value=label('');row.append(name);row.append(value);self.process.append(row);self.rows.append((row,name,value))
        body.append(label(HINT,'sound-hint'))
        install_navigation(self.window,self.refresh)
        key=Gtk.EventControllerKey();key.connect('key-pressed',self.key);self.window.add_controller(key);self.window.connect('close-request',self.close)
        self.window.present();self.refresh();self.timer=GLib.timeout_add_seconds(2,self.refresh)
    def key(self,controller,key,code,state):
        if self.window._vim_navigation.keys.matches("cancel",key,state):self.window.close();return True
        return False
    def close(self,*_):
        self.closed=True;GLib.source_remove(self.timer);self.pool.shutdown(wait=False,cancel_futures=True);return False
    def refresh(self):
        if not self.busy and not self.closed:
            self.busy=True;f=self.pool.submit(read_sample);f.add_done_callback(lambda f:GLib.idle_add(self.received,f) if not f.cancelled() else None)
        return not self.closed
    def received(self,f):
        if self.closed:return False
        self.busy=False
        try:sample=f.result()
        except Exception as e:self.status.set_text(str(e));return False
        now,cpus,mem,processes=sample;old=self.previous;self.previous=sample
        if self.kind=='cpu':
            usage=cpu_usage(cpus['cpu'],old[1]['cpu']) if old else 0;self.main.set_text(f'{usage:.0f}% CPU used' if old else 'Sampling CPU…');self.bar.set_fraction(usage/100)
            for key,bar in self.cores.items():
                value=cpu_usage(cpus[key],old[1].get(key,cpus[key])) if old and key in cpus else 0;bar.set_fraction(value/100);bar.set_text(f'{value:.0f}%')
            elapsed=now-old[0] if old else 1;hz=os.sysconf('SC_CLK_TCK');previous=old[3] if old else {}
            ranked=sorted([(max(0,(v[1]-previous[pid][1])/hz/elapsed*100) if pid in previous else 0,pid,v[0]) for pid,v in processes.items()],reverse=True)
        else:
            total=mem['MemTotal'];available=mem.get('MemAvailable',mem['MemFree']);used=total-available;self.main.set_text(f'{human(used)} used / {human(total)}');self.bar.set_fraction(used/total)
            self.details.set_text(f'Available {human(available)} · Cache {human(mem.get("Cached",0)+mem.get("SReclaimable",0))}\nSwap {human(mem["SwapTotal"]-mem["SwapFree"])} used / {human(mem["SwapTotal"])}')
            ranked=sorted([(v[2],pid,v[0]) for pid,v in processes.items()],reverse=True)
        for i,(row,name,value) in enumerate(self.rows):
            row.set_visible(i<len(ranked))
            if i<len(ranked):
                amount,pid,title=ranked[i];name.set_text(f'{title} · {pid}');value.set_text(f'{amount:.0f}%' if self.kind=='cpu' else human(amount))
        self.status.set_text('Updates every 2 seconds · process CPU: 100% = one core' if self.kind=='cpu' else 'Updates every 2 seconds · process memory is RSS; shared pages can overlap')
        return False

if __name__=='__main__':
    kind=sys.argv[1] if len(sys.argv)>1 else 'cpu'
    if '--check' in sys.argv:
        sample=read_sample();assert sample[1] and sample[2]['MemTotal'];print('CPU and memory procfs sampling ready')
    else:raise SystemExit(Resources(kind).run([]))

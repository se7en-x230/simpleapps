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
import sys,subprocess,json
from pathlib import Path
from model import load,label,CONFIG
from exporter import export,watch,shortcuts,STATE
if '--watch' in sys.argv:watch();sys.exit()
if '--export' in sys.argv:print(json.dumps(export(),indent=2));sys.exit()
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,GLib,Pango

def box(vertical=False,spacing=8):return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,spacing=spacing)
def text(s):return Gtk.Label(label=s,xalign=0,wrap=True)
def clear(widget):
    while widget.get_first_child():widget.remove(widget.get_first_child())
class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='com.go7.KeyboardLayout');self.connect('activate',self.activate);self.layer=0;self.desktop=False
    def activate(self,*args):
        if self.get_active_window():self.get_active_window().present();return
        self.win=Gtk.ApplicationWindow(application=self,title='Keyboard layout');self.win.set_default_size(1100,720);self.win.add_css_class('simplekeyboard')
        css=Gtk.CssProvider();_load_simple_css(css,str(_Path(_path_os.environ.get('XDG_CONFIG_HOME',_Path.home()/'.config'))/'simplepicker/keyboard/style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_USER+2)
        self.root=box(True,12);self.root.set_margin_top(20);self.root.set_margin_bottom(20);self.root.set_margin_start(20);self.root.set_margin_end(20);self.win.set_child(self.root)
        header=box();self.root.append(header);title=text('Keyboard & shortcuts');title.add_css_class('title');title.set_hexpand(True);header.append(title)
        for name,fn in [('Open PDF',self.open_pdf),('Update PDF',self.update_pdf)]:
            b=Gtk.Button(label=name);b.connect('clicked',fn);header.append(b)
        self.search=Gtk.SearchEntry(placeholder_text='Find a key, action or shortcut across all layers…');self.search.connect('changed',lambda *_:self.draw());self.root.append(self.search);self.search.set_visible(False)
        self.tabs=box();self.root.append(self.tabs);self.hint=text('');self.root.append(self.hint)
        scroll=Gtk.ScrolledWindow(vexpand=True);self.scroll=scroll;self.root.append(scroll);self.content=box(True,12);scroll.set_child(self.content)
        self.detail=text('h/j/k/l move · k at top: layers · Enter select · [ / ] layers · / search · Esc leave search / close');self.root.append(self.detail)
        self.status=text('');self.status.add_css_class('muted');self.root.append(self.status)
        controller=Gtk.EventControllerKey();controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE);controller.connect('key-pressed',self.key);self.win.add_controller(controller)
        self.reload();GLib.timeout_add_seconds(3,self.reload);self.win.present();self.win.set_focus_visible(True);self.focus_layer_tab()
    def reload(self):
        try:
            layout=load();rows=shortcuts();changed=not hasattr(self,'layout') or layout.digest!=self.layout.digest or layout.path!=self.layout.path or rows!=self.rows
            self.layout=layout;self.rows=rows;self.layer=min(self.layer,len(layout.layers)-1)
            if changed:
                clear(self.tabs);self.tabbuttons=[]
                for n in range(len(layout.layers)):
                    b=Gtk.Button(label=f'{n} · {layout.name(n)}');b.connect('clicked',lambda _,n=n:self.select(n));self.tabs.append(b);self.tabbuttons.append(b)
                b=Gtk.Button(label='Desktop shortcuts');b.connect('clicked',lambda *_:self.select(None));self.tabs.append(b);self.tabbuttons.append(b);self.draw()
            message='Saved layout: '+layout.path.name+' · Reference only; active hardware layer is not tracked.'
            if (STATE/'error.json').exists():message+='\nPDF: '+json.loads((STATE/'error.json').read_text())['error']
            elif (STATE/'status.json').exists():message+='\nPDF: '+json.loads((STATE/'status.json').read_text()).get('cloud','Ready')
            self.status.set_text(message)
        except Exception as exc:self.status.set_text('Unable to read layout: '+str(exc))
        return True
    def select(self,n):
        self.desktop=n is None
        if n is not None:self.layer=n
        self.search.set_text('');self.draw()
    def draw(self):
        if not hasattr(self,'layout'):return
        previous_focus=self.win.get_focus()
        previous_key=next((pos for pos,b in getattr(self,'keybuttons',{}).items() if b==previous_focus),None)
        previous_results=getattr(self,'resultbuttons',[])
        previous_result=previous_results.index(previous_focus) if previous_focus in previous_results else None
        clear(self.content);self.keybuttons={};self.resultbuttons=[];q=self.search.get_text().strip().casefold();l=self.layout
        if q:
            self.hint.set_text('Search results · Down or Enter: focus results · j/k: move · Enter: select · /: edit search')
            for n,r,c,name in l.keys(q):
                b=Gtk.Button(label=f'L{n} {l.name(n)} · {l.position(r,c)} · {name}');b.connect('clicked',lambda _,n=n,r=r,c=c:self.result(n,r,c));self.content.append(b);self.resultbuttons.append(b)
            for row in l.extras()+self.rows:
                if q in row.casefold():self.shortcut_row(row)
            if not self.content.get_first_child():self.content.append(text('No matching keys or shortcuts.'))
        elif self.desktop:
            self.hint.set_text('Same definitions used by Super+/ · search above to filter')
            for row in l.extras()+self.rows:self.shortcut_row(row)
        else:
            self.hint.set_text(f'L{self.layer} · {l.name(self.layer)} — '+ '; '.join(l.access(self.layer)))
            halves=box(False,16);halves.set_homogeneous(True);self.content.append(halves)
            for side in range(2):
                grid=Gtk.Grid(column_spacing=5,row_spacing=6,column_homogeneous=True);grid.set_hexpand(True);halves.append(grid)
                for r in range(l.half):
                    rr=r+side*l.half
                    for c,code in enumerate(l.layers[self.layer][rr]):
                        if code==-1:continue
                        b=Gtk.Button();v=box(True,4);p=text(l.position(rr,c));p.add_css_class('muted');p.set_max_width_chars(7);p.set_wrap_mode(Pango.WrapMode.CHAR);v.append(p);k=text(label(code));k.set_max_width_chars(8);k.set_wrap_mode(Pango.WrapMode.WORD_CHAR);v.append(k);b.set_child(v);b.add_css_class('keycap');b.set_size_request(48,76);b.connect('clicked',lambda _,r=rr,c=c:self.inspect(r,c));grid.attach(b,c,r,1,1);self.keybuttons[(c+side*(l.cols+1),r)]=b
            self.content.append(text('Transparent = inherit from the next active layer. Thumb positions count left to right on each half.'))
        # Rebuilding a layer must not let GTK choose an arbitrary new focus.
        if previous_key is not None:
            target=self.keybuttons.get(previous_key) or next(iter(self.keybuttons.values()),None)
            if target:target.grab_focus()
        elif previous_result is not None and self.resultbuttons:
            self.resultbuttons[min(previous_result,len(self.resultbuttons)-1)].grab_focus()
    def shortcut_row(self,row):
        b=Gtk.Button();b.set_child(text(row));b.connect('clicked',lambda *_:self.detail.set_text(row));self.content.append(b);self.resultbuttons.append(b)
    def inspect(self,r,c):self.detail.set_text(self.layout.position(r,c)+' → '+'  |  '.join(f'L{n}: {self.layout.describe(m[r][c])}' for n,m in enumerate(self.layout.layers)))
    def result(self,n,r,c):
        self.select(n);self.inspect(r,c)
        pos=(c+(self.layout.cols+1 if r>=self.layout.half else 0),r%self.layout.half)
        self.keybuttons[pos].grab_focus()
    def open_pdf(self,*_):
        if hasattr(self,'layout'):
            p=Path(self.layout.config['source_dir']).expanduser()/self.layout.config['pdf_name']
            if p.exists():subprocess.Popen(['xdg-open',str(p)])
            else:self.status.set_text('PDF not created yet. Use Update PDF.')
    def update_pdf(self,*_):
        subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--export']);self.status.set_text('PDF update requested…')
    def focus_layer_tab(self):
        self.tabbuttons[-1 if self.desktop else self.layer].grab_focus()
    def key(self,controller,key,keycode,state):
        focus=self.win.get_focus()
        editing=focus and (isinstance(focus,Gtk.Text) or focus==self.search)
        if key==Gdk.KEY_Escape:
            if self.search.get_visible():
                self.search.set_text('')
                self.search.set_visible(False)
                self.draw()
                buttons=list(self.keybuttons.values()) or self.resultbuttons
                if buttons:buttons[0].grab_focus()
                else:self.tabs.get_first_child().grab_focus()
            else:self.win.close()
            return True
        ctrl=bool(state&Gdk.ModifierType.CONTROL_MASK)
        if editing:
            if key in (Gdk.KEY_Down,Gdk.KEY_Up,Gdk.KEY_Return,Gdk.KEY_KP_Enter) or (ctrl and key in (Gdk.KEY_j,Gdk.KEY_k)):
                if self.resultbuttons:
                    self.win.set_focus_visible(True)
                    self.resultbuttons[-1 if key in (Gdk.KEY_Up,Gdk.KEY_k) else 0].grab_focus()
                return True
            return False
        key={Gdk.KEY_Down:Gdk.KEY_j,Gdk.KEY_Up:Gdk.KEY_k,Gdk.KEY_Left:Gdk.KEY_h,Gdk.KEY_Right:Gdk.KEY_l}.get(key,key)
        if key==Gdk.KEY_slash:
            self.search.set_visible(True);self.search.grab_focus();return True
        if key in (Gdk.KEY_bracketleft,Gdk.KEY_bracketright):
            self.select((self.layer+(-1 if key==Gdk.KEY_bracketleft else 1))%len(self.layout.layers));return True
        if Gdk.KEY_0<=key<=Gdk.KEY_9 and key-Gdk.KEY_0<len(self.layout.layers):self.select(key-Gdk.KEY_0);return True
        if key in (Gdk.KEY_h,Gdk.KEY_j,Gdk.KEY_k,Gdk.KEY_l):
            self.win.set_focus_visible(True)
            if focus in self.tabbuttons:
                index=self.tabbuttons.index(focus)
                if key in (Gdk.KEY_h,Gdk.KEY_l):
                    target=max(0,min(len(self.tabbuttons)-1,index+(-1 if key==Gdk.KEY_h else 1)))
                    self.tabbuttons[target].grab_focus()
                    if target!=index:self.select(None if target==len(self.tabbuttons)-1 else target)
                elif key==Gdk.KEY_j:
                    buttons=list(self.keybuttons.values()) or self.resultbuttons
                    if buttons:buttons[0].grab_focus()
                elif key==Gdk.KEY_k and self.search.get_visible():self.search.grab_focus()
                return True
            if self.resultbuttons:
                if focus==self.resultbuttons[0] and key==Gdk.KEY_k:
                    self.focus_layer_tab();return True
                index=self.resultbuttons.index(focus) if focus in self.resultbuttons else (-1 if key in (Gdk.KEY_j,Gdk.KEY_l) else len(self.resultbuttons))
                index=max(0,min(len(self.resultbuttons)-1,index+(1 if key in (Gdk.KEY_j,Gdk.KEY_l) else -1)))
                self.resultbuttons[index].grab_focus()
            elif self.keybuttons:
                current=next((pos for pos,b in self.keybuttons.items() if b==focus),None)
                if current is None:next(iter(self.keybuttons.values())).grab_focus()
                else:
                    x,y=current;dx,dy={Gdk.KEY_h:(-1,0),Gdk.KEY_l:(1,0),Gdk.KEY_j:(0,1),Gdk.KEY_k:(0,-1)}[key]
                    candidates=[p for p in self.keybuttons if (p[0]-x)*dx>0 and p[1]==y] if dx else [p for p in self.keybuttons if (p[1]-y)*dy>0]
                    if candidates:
                        pos=min(candidates,key=lambda p:abs(p[0]-x)+abs(p[1]-y)*(self.layout.cols*3));self.keybuttons[pos].grab_focus()
                    elif key==Gdk.KEY_k:self.focus_layer_tab()
            else:
                adj=self.scroll.get_vadjustment();adj.set_value(max(adj.get_lower(),min(adj.get_upper()-adj.get_page_size(),adj.get_value()+(60 if key in (Gdk.KEY_j,Gdk.KEY_l) else -60))))
            return True
        if key in (Gdk.KEY_Return,Gdk.KEY_KP_Enter) and isinstance(focus,Gtk.Button):focus.emit('clicked');return True
        return False

if __name__=='__main__':App().run([])

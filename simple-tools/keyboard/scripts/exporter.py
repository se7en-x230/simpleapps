"""Atomic PDF export and a small dependency-free polling watcher."""
import os as _path_os, sys as _path_sys
from pathlib import Path as _Path
_roots=[_Path(__file__).resolve().parents[3],_Path(_path_os.environ.get('XDG_DATA_HOME',_Path.home()/'.local/share')),_Path.home()/'.local/src']
if _path_os.environ.get('SIMPLE_SOURCE_ROOT'):_roots.insert(0,_Path(_path_os.environ['SIMPLE_SOURCE_ROOT']))
for _root in reversed(_roots):
    for _name in ('simplepicker/python','simple-common'):
        if (_root/_name).is_dir():_path_sys.path.insert(0,str(_root/_name))
import hashlib,json,os,runpy,tempfile,time,fcntl,shutil
from pathlib import Path
from model import load,label,CONFIG
VERSION='2'
STATE=Path(os.environ.get('KEYBOARD_LAYOUT_STATE',_Path(_path_os.environ.get('XDG_STATE_HOME',_Path.home()/'.local/state'))/'keyboard-layout'))
def shortcuts():
    path=_Path(_path_os.environ.get('XDG_CONFIG_HOME',_Path.home()/'.config'))/'mango/scripts/shortcut-reference'
    if not path.exists():return []
    return list(runpy.run_path(str(path))['entries'](_Path(_path_os.environ.get('XDG_CONFIG_HOME',_Path.home()/'.config'))))
def signature(layout,rows):
    return hashlib.sha256((VERSION+str(layout.path)+layout.digest+json.dumps(layout.config,sort_keys=True)+'\n'.join(rows)).encode()).hexdigest()
def render(layout,rows,destination):
    import cairo,gi
    gi.require_version('Pango','1.0');gi.require_version('PangoCairo','1.0')
    from gi.repository import Pango,PangoCairo
    surface=cairo.PDFSurface(str(destination),842,595);cr=cairo.Context(surface)
    def text(s,x,y,w,size=11,maxheight=None):
        cr.set_source_rgb(.13,.15,.13);p=PangoCairo.create_layout(cr);p.set_font_description(Pango.FontDescription('Sans '+str(size)));p.set_width(int(w*Pango.SCALE));p.set_wrap(Pango.WrapMode.WORD_CHAR);p.set_text(str(s),-1)
        while maxheight and p.get_pixel_size()[1]>maxheight and size>5:
            size-=.5;p.set_font_description(Pango.FontDescription('Sans '+str(size)))
        cr.move_to(x,y);PangoCairo.show_layout(cr,p);return p.get_pixel_size()[1]
    def page(title):
        cr.set_source_rgb(.97,.97,.94);cr.paint();text(title,28,22,786,21)
        text('Saved layout reference · '+layout.path.name,28,558,786,9)
    for n,matrix in enumerate(layout.layers):
        page(f'L{n} · {layout.name(n)}')
        text('Reach: '+'; '.join(layout.access(n)),28,57,786,10)
        active=[r for r in range(layout.half) if any(k!=-1 for side in (0,layout.half) for k in matrix[r+side])]
        cw=370/layout.cols;ch=min(76,340/max(1,len(active)))
        for side in range(2):
            for ri,r in enumerate(active):
                rr=r+side*layout.half
                for c,code in enumerate(matrix[rr]):
                    if code==-1:continue
                    x=28+side*408+c*cw;y=112+ri*ch
                    cr.set_source_rgb(.86,.89,.83);cr.rectangle(x,y,cw-4,ch-5);cr.fill()
                    text(layout.position(rr,c),x+4,y+4,cw-12,8,15)
                    text(label(code),x+4,y+24,cw-12,9,ch-33)
        text('Transparent keys inherit from the next active layer. Thumb positions L1–L6 / R1–R6 run left to right.',28,465,786,10)
        enc=layout.data.get('encoder_layout',layout.data.get('encoders',[]))
        if n<len(enc):text('Encoders: '+str([[label(k) for k in pair] for pair in enc[n]]),28,493,786,10)
        surface.show_page()
    page('Tap dances, combos & desktop shortcuts');y=65
    for row in layout.extras()+['Desktop shortcuts · Super+/ reference']+rows:
        # Allocate wrapped height before drawing so entries never cross a page boundary.
        p=PangoCairo.create_layout(cr);p.set_font_description(Pango.FontDescription('Sans 10'));p.set_width(786*Pango.SCALE);p.set_text(row,-1);h=p.get_pixel_size()[1]+10
        if y+h>540:surface.show_page();page('Desktop shortcuts · continued');y=65
        if int(y)%2:cr.set_source_rgb(.91,.93,.89);cr.rectangle(25,y-2,792,h);cr.fill()
        text(row,28,y,786,10);y+=h
    surface.show_page();surface.finish()
def atomic_json(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2));temp.replace(path)
def export(config=CONFIG):
    STATE.mkdir(parents=True,exist_ok=True)
    with (STATE/'lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        layout=load(config);rows=shortcuts();sig=signature(layout,rows)
        dest=Path(layout.config['source_dir']).expanduser()/layout.config.get('pdf_name','Keyboard-Layout.pdf')
        dest.parent.mkdir(parents=True,exist_ok=True)
        previous=json.loads((STATE/'status.json').read_text()) if (STATE/'status.json').exists() else {}
        if previous.get('signature')!=sig or not dest.exists():
            fd,tmp=tempfile.mkstemp(prefix='.keyboard-',suffix='.pdf',dir=dest.parent);os.close(fd)
            try:render(layout,rows,tmp);os.replace(tmp,dest)
            finally:
                if os.path.exists(tmp):os.unlink(tmp)
        cloud=Path(layout.config.get('cloud_dir','')).expanduser();mirror='Not configured'
        if layout.config.get('cloud_dir'):
            mirror='Waiting for pCloud mount'
            if layout.config.get('cloud_mount') and os.path.ismount(Path(layout.config['cloud_mount']).expanduser()) and cloud.is_dir():
                target=cloud/dest.name
                if not target.exists() or hashlib.sha256(target.read_bytes()).digest()!=hashlib.sha256(dest.read_bytes()).digest():
                    tmp=cloud/('.'+dest.name+'.tmp');shutil.copyfile(dest,tmp);tmp.replace(target)
                mirror='Copied to pCloud mount (upload status is shown in pCloud)'
        status={'signature':sig,'source':str(layout.path),'pdf':str(dest),'cloud':mirror,'updated':time.strftime('%Y-%m-%d %H:%M:%S')}
        atomic_json(STATE/'status.json',status);return status
def watch(config=CONFIG):
    last=None;exported=None;last_export=0
    while True:
        try:
            layout=load(config);sig=signature(layout,shortcuts())
            if sig==last and (sig!=exported or time.monotonic()-last_export>60):
                export(config);exported=sig;last_export=time.monotonic()
            last=sig
        except Exception as exc:
            STATE.mkdir(parents=True,exist_ok=True)
            atomic_json(STATE/'error.json',{'error':str(exc),'time':time.strftime('%Y-%m-%d %H:%M:%S')})
            last=None
        else:
            (STATE/'error.json').unlink(missing_ok=True)
        time.sleep(3)

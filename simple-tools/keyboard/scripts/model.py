"""Read saved Vial layouts without exposing macro contents or touching hardware."""
import os as _path_os, sys as _path_sys
from pathlib import Path as _Path
_roots=[_Path(__file__).resolve().parents[3],_Path(_path_os.environ.get('XDG_DATA_HOME',_Path.home()/'.local/share')),_Path.home()/'.local/src']
if _path_os.environ.get('SIMPLE_SOURCE_ROOT'):_roots.insert(0,_Path(_path_os.environ['SIMPLE_SOURCE_ROOT']))
for _root in reversed(_roots):
    for _name in ('simplepicker/python','simple-common'):
        if (_root/_name).is_dir():_path_sys.path.insert(0,str(_root/_name))
import hashlib,json,re,os
from pathlib import Path
HOME=Path.home()
CONFIG=Path(os.environ.get('KEYBOARD_LAYOUT_CONFIG',_Path(_path_os.environ.get('XDG_CONFIG_HOME',_Path.home()/'.config'))/'simplepicker/keyboard/config.json'))
DEFAULT_NAMES=['Typing','Mouse','Symbols','Numbers','Desktop','Typing / move tags']
NAMES={'KC_ENTER':'Enter','KC_ESCAPE':'Esc','KC_BSPACE':'Backspace','KC_SPACE':'Space','KC_DELETE':'Delete','KC_TRNS':'Transparent','KC_NO':'Disabled','KC_TAB':'Tab','KC_DOT':'.','KC_COMMA':',','KC_SLASH':'/','KC_BSLASH':'\\','KC_QUOTE':"'",'KC_SCOLON':';','KC_MINUS':'-','KC_EQUAL':'=','KC_GRAVE':'`','KC_LBRACKET':'[','KC_RBRACKET':']','KC_LGUI':'Super','KC_LALT':'Alt','KC_LCTRL':'Ctrl','KC_LSHIFT':'Shift','KC_VOLD':'Volume down','KC_VOLU':'Volume up','KC_MUTE':'Mute','KC_BTN1':'Left click','KC_BTN2':'Right click','KC_BTN3':'Middle click','KC_MS_U':'Mouse up','KC_MS_D':'Mouse down','KC_MS_L':'Mouse left','KC_MS_R':'Mouse right','KC_WH_U':'Scroll up','KC_WH_D':'Scroll down','KC_PGUP':'Page Up','KC_PGDOWN':'Page Down'}
MODS={'LGUI':'Super','RGUI':'Super','LALT':'Alt','RALT':'AltGr','LCTL':'Ctrl','RCTL':'Ctrl','LSFT':'Shift','RSFT':'Shift','SGUI':'Super+Shift'}
SHIFT=dict(zip('1234567890','!@#$%^&*()'));SHIFT.update({'BSLASH':'|','LBRACKET':'{','RBRACKET':'}'})
def label(code):
    code=str(code)
    if code=='-1':return ''
    if code in NAMES:return NAMES[code]
    if re.fullmatch(r'M\d+',code):return 'Macro '+code[1:]
    m=re.fullmatch(r'LT(\d+)\((.+)\)',code)
    if m:return label(m[2])+' / hold L'+m[1]
    m=re.fullmatch(r'(\w+)_T\((.+)\)',code)
    if m:return label(m[2])+' / hold '+MODS.get(m[1],m[1])
    m=re.fullmatch(r'(\w+)\((.+)\)',code)
    if m:
        op,arg=m.groups()
        if op=='LSFT' and arg.removeprefix('KC_') in SHIFT:return SHIFT[arg.removeprefix('KC_')]
        if op in MODS:return MODS[op]+'+'+label(arg)
        return {'TG':'Toggle L','MO':'Hold L','OSL':'Once L','TD':'Tap dance '}.get(op,op+' ')+arg
    if code.startswith('RGB_'):return 'RGB '+code[4:].lower()
    return code.removeprefix('KC_').replace('KP_','Keypad ').replace('_',' ').title() if len(code)>4 else code.removeprefix('KC_')
def target(code):
    m=re.fullmatch(r'(TG|MO|OSL)\((\d+)\)',str(code))
    if m:return int(m[2]),{'TG':'toggle','MO':'hold','OSL':'one-shot'}[m[1]]
    m=re.fullmatch(r'LT(\d+)\(.+\)',str(code))
    return (int(m[1]),'hold') if m else None

def load(config_path=CONFIG):
    cfg=json.loads(Path(config_path).read_text())
    directory=Path(cfg['source_dir']).expanduser()
    directories=[directory]
    cloud=Path(cfg.get('cloud_dir','')).expanduser()
    mount=Path(cfg['cloud_mount']).expanduser() if cfg.get('cloud_mount') else None
    if cfg.get('cloud_dir') and mount and os.path.ismount(mount) and cloud.is_dir():directories.append(cloud)
    candidates=sorted((p for folder in directories for p in folder.glob('*.vil') if not p.name.startswith('.')),key=lambda p:(p.stat().st_mtime_ns,p.name),reverse=True)
    for path in candidates:
        if path.name.startswith('.'):continue
        raw=path.read_bytes();data=json.loads(raw)
        if str(data.get('uid'))!=str(cfg['keyboard_uid']):continue
        layers=data.get('layout')
        if not isinstance(layers,list) or not layers or len(layers)>32:raise ValueError('Invalid layer list')
        rows=len(layers[0]);cols=len(layers[0][0])
        if not rows or rows%2 or not cols or cols>20:raise ValueError('Unsupported split matrix dimensions')
        for layer in layers:
            if len(layer)!=rows or any(len(row)!=cols for row in layer):raise ValueError('Inconsistent layer matrix')
            for row in layer:
                if any(not (x==-1 or isinstance(x,str)) for x in row):raise ValueError('Invalid key code')
        return Layout(path,data,cfg,hashlib.sha256(raw).hexdigest())
    raise FileNotFoundError('No saved layout for this keyboard in '+str(directory))

class Layout:
    def __init__(self,path,data,config,digest):
        self.path=path;self.data=data;self.config=config;self.digest=digest;self.layers=data['layout'];self.rows=len(self.layers[0]);self.cols=len(self.layers[0][0]);self.half=self.rows//2
    def name(self,layer):return self.config.get('layer_names',{}).get(str(layer),'Layer '+str(layer))
    def position(self,row,col):
        side='L' if row<self.half else 'R'
        if row%self.half==self.half-1:
            occupied=[c for c,k in enumerate(self.layers[0][row]) if k!=-1]
            if col in occupied:return side+str(occupied.index(col)+1)
        return side+' '+label(self.layers[0][row][col]).split(' / ')[0]
    def describe(self,code):
        match=re.fullmatch(r'TD\((\d+)\)',str(code))
        dances=self.data.get('tap_dance',[])
        if match and int(match[1])<len(dances):
            values=dances[int(match[1])]
            return ' / '.join(name+': '+label(value) for name,value in zip(('Tap','Hold','Double tap','Tap + hold'),values) if value not in ('KC_NO',-1))
        return label(code)
    def extras(self):
        out=[]
        for n,dance in enumerate(self.data.get('tap_dance',[])):
            if any(x not in ('KC_NO',-1) for x in dance[:4]):out.append('Tap dance '+str(n)+' · '+self.describe('TD('+str(n)+')'))
        for combo in self.data.get('combo',[]):
            if combo and combo[-1] not in ('KC_NO',-1):out.append('Combo · '+' + '.join(label(x) for x in combo[:-1] if x not in ('KC_NO',-1))+' → '+label(combo[-1]))
        return out
    def resolve(self,layer,row,col):
        # Preview transparent keys against base; actual inheritance depends on active layers.
        code=self.layers[layer][row][col]
        return self.layers[0][row][col] if code=='KC_TRNS' else code
    def access(self,layer):
        out=[]
        if layer==0:return ['Base typing layer']
        for n,matrix in enumerate(self.layers):
            for r,row in enumerate(matrix):
                for c,code in enumerate(row):
                    options=[('',code)]
                    m=re.fullmatch(r'TD\((\d+)\)',str(code))
                    if m and int(m[1])<len(self.data.get('tap_dance',[])):
                        options=list(zip(('tap: ','hold: ','double tap: ','tap + hold: '),self.data['tap_dance'][int(m[1])][:4]))
                    for action,value in options:
                        t=target(value)
                        if t and t[0]==layer:out.append(f'L{n} {self.position(r,c)}: {action}{t[1]}')
        return out or ['No direct layer key found in this saved layout']
    def keys(self,query=''):
        q=query.casefold().strip();out=[]
        for n,matrix in enumerate(self.layers):
            for r,row in enumerate(matrix):
                for c,code in enumerate(row):
                    if code==-1 or code in ('KC_NO','KC_TRNS'):continue
                    text=f'{self.describe(code)} {code} {self.name(n)} {self.position(r,c)}'
                    if q and q in text.casefold():out.append((n,r,c,label(code)))
        return out

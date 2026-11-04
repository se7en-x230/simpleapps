"""Optional artwork integration. Wallpaper software is never imported or launched."""
import configparser,json,os
from pathlib import Path

def settings():
    root=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'simple'
    config=configparser.ConfigParser(interpolation=None)
    try:config.read(root/'images.ini')
    except (OSError,configparser.Error):return root,{}
    return root,dict(config['images']) if config.has_section('images') else {}

def bundled(kind):
    name='default-avatar.png' if kind=='profile' else 'default-idle.png'
    roots=[]
    if os.environ.get('SIMPLE_IMAGES_DIR'):roots.append(Path(os.environ['SIMPLE_IMAGES_DIR']))
    roots.append(Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'simple/images')
    roots.extend(Path(p)/'simple/images' for p in os.environ.get('XDG_DATA_DIRS','/usr/local/share:/usr/share').split(':') if p)
    roots.append(Path(__file__).resolve().parent/'assets/images')
    return next((p/name for p in roots if (p/name).is_file()),None)

def resolve(kind='idle'):
    if kind not in ('idle','profile'):raise ValueError('Unknown image role')
    root,config=settings();candidates=[]
    if config.get(kind):
        path=Path(config[kind]).expanduser();candidates.append(path if path.is_absolute() else root/path)
    if kind=='idle' and config.get('use_wallpaper','true').lower() not in ('false','no','0','off'):
        data=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))
        candidates.append(data/'simplewallpaper/current')
        try:legacy=json.loads((root.parent/'wallpaper/config.json').read_text())
        except (OSError,ValueError):legacy={}
        names=['daylight-current.png','current.png'] if legacy.get('mode')=='daylight' else ['current.png','daylight-current.png']
        candidates.extend(data/'wallpaper'/name for name in names)
    fallback=bundled(kind)
    if fallback:candidates.append(fallback)
    for path in candidates:
        try:
            resolved=path.resolve(strict=True)
            if resolved.is_file():return resolved
        except OSError:pass
    return None

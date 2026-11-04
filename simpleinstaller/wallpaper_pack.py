"""Separate, lazily loaded daylight artwork for the portable installer."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile

FILENAME = 'simpleinstaller-wallpapers.tar.gz'
METADATA = 'wallpaper-pack.json'

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

@contextmanager
def legacy_prepare(here, names, options, override=None):
    if 'simplewallpaper' not in names or 'daylight' not in options:
        yield None
        return
    metadata = here / METADATA
    # Maintained source checkouts may still keep their original artwork directory.
    if not metadata.exists() and override is None and (here / 'wallpaper-packs').is_dir():
        yield here / 'wallpaper-packs'
        return
    if not metadata.is_file():
        raise ValueError('Missing wallpaper-pack.json; use a complete Simpleinstaller app bundle.')
    expected = json.loads(metadata.read_text())['sha256']
    candidates = [Path(override).expanduser()] if override else [here.parent / FILENAME, here / FILENAME]
    archive = next((path for path in candidates if path.is_file()), None)
    if archive is None:
        raise ValueError('Daylight themes need ' + FILENAME + '. Copy it beside the extracted simpleinstaller folder, or use --wallpaper-pack FILE. You can also deselect daylight themes.')
    if digest(archive) != expected:
        raise ValueError('Wallpaper pack verification failed. Use the matching wallpaper archive supplied with this app bundle.')
    with tempfile.TemporaryDirectory(prefix='simpleinstaller-wallpapers-') as td:
        destination = Path(td)
        with tarfile.open(archive, 'r:gz') as source:
            members = source.getmembers()
            for member in members:
                path = Path(member.name)
                if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'wallpaper-packs' or not (member.isfile() or member.isdir()):
                    raise ValueError('Invalid wallpaper archive entry: ' + member.name)
            source.extractall(destination, members=members, filter='data')
        themes = destination / 'wallpaper-packs'
        if not themes.is_dir() or not any(p.is_file() for p in themes.rglob('*')):
            raise ValueError('Wallpaper archive contains no themes')
        yield themes

def catalog(here):
    metadata=here/METADATA
    if metadata.exists():
        data=json.loads(metadata.read_text())
        if 'themes' in data:return data['themes']
    return {p.name:{'label':p.name.replace('-',' ').title()} for p in sorted((here/'wallpaper-packs').glob('*')) if p.is_dir()}

def extract(archive, expected, destination, key):
    if digest(archive)!=expected:raise ValueError('Wallpaper pack verification failed: '+archive.name)
    with tarfile.open(archive,'r:gz') as source:
        members=source.getmembers()
        for member in members:
            path=Path(member.name)
            if path.is_absolute() or '..' in path.parts or path.parts[:2]!=('wallpaper-packs',key) or not (member.isfile() or member.isdir()):
                raise ValueError('Invalid wallpaper archive entry: '+member.name)
        source.extractall(destination,members=members,filter='data')
    required=['night.png',*[f'{hour:02}.png' for hour in range(6,18)]]
    if any(not (destination/'wallpaper-packs'/key/name).is_file() for name in required):
        raise ValueError('Incomplete daylight theme: '+key)

@contextmanager
def prepare(here,names,options,override=None,selected=None):
    if 'simplewallpaper' not in names or 'daylight' not in options:
        yield None;return
    metadata=json.loads((here/METADATA).read_text()) if (here/METADATA).exists() else {}
    available=catalog(here)
    selected=list(available) if selected is None or 'all' in selected else list(dict.fromkeys(selected))
    if any(key not in available or '/' in key or key in ('.','..') for key in selected):
        raise ValueError('Unknown wallpaper theme; use --list-wallpapers')
    if 'themes' not in metadata:
        with legacy_prepare(here,names,options,override) as themes:
            if not available or set(selected)==set(available):yield themes;return
            with tempfile.TemporaryDirectory(prefix='simpleinstaller-selected-') as td:
                result=Path(td)
                for key in selected:shutil.copytree(themes/key,result/key)
                yield result
        return
    if not selected:raise ValueError('Select at least one daylight theme')
    with tempfile.TemporaryDirectory(prefix='simpleinstaller-wallpapers-') as td:
        destination=Path(td)
        for key in selected:
            info=available[key];filename=info['filename']
            if Path(filename).name!=filename:raise ValueError('Invalid wallpaper archive filename')
            candidates=[here.parent/filename,here/filename]
            if override:
                explicit=Path(override).expanduser()
                candidates=[explicit/filename if explicit.is_dir() else explicit]
            archive=next((p for p in candidates if p.is_file()),None)
            if archive is None:raise ValueError('Missing '+filename+'. Copy it beside the extracted simpleinstaller folder, or use --wallpaper-pack DIRECTORY.')
            extract(archive,info['sha256'],destination,key)
        yield destination/'wallpaper-packs'

def bundle(here,out,destination):
    themes=catalog(here)
    if not themes:raise ValueError('No wallpaper themes available for bundling')
    metadata={'schema':2,'themes':{}}
    for key,info in themes.items():
        filename='simpleinstaller-wallpaper-'+key+'.tar.gz'
        target=destination/filename
        local=here/'wallpaper-packs'/key
        if local.is_dir():
            if target.exists():raise ValueError('Wallpaper bundle destination already exists: '+str(target))
            with tarfile.open(target,'w:gz') as archive:archive.add(local,arcname='wallpaper-packs/'+key)
        else:
            candidates=[here.parent/filename,here/filename,target]
            source=next((p for p in candidates if p.is_file() and digest(p)==info['sha256']),None)
            if source is None:raise ValueError('Rebundling requires '+filename)
            if target.exists() and digest(target)!=info['sha256']:raise ValueError('Different wallpaper pack exists: '+str(target))
            if not target.exists():shutil.copy2(source,target)
        metadata['themes'][key]={'label':info['label'],'filename':filename,'sha256':digest(target),'bytes':target.stat().st_size}
        print('Optional wallpaper theme:',target)
    (out/METADATA).write_text(json.dumps(metadata,indent=2)+'\n')

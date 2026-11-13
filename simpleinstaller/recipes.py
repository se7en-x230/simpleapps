"""App-only staging recipes. Never invoke Newinit, setup-runtime or live services."""
import os
import hashlib
import json
import platform
import shlex
from pathlib import Path
import shutil
import subprocess
import sys

TOOLS=('network','sound','disk','resources','displays','services','passwords')

def source_ignore(directory,names):
    result=[]
    for name in names:
        p=Path(directory)/name
        if name in ('.git','__pycache__','.venv','venv') or p.suffix in ('.o','.pyc') or name.endswith(('-native','-test')):
            result.append(name);continue
        if p.is_symlink():raise ValueError('Source symlink needs review before bundling: '+str(p))
        if p.is_file():
            with p.open('rb') as f:
                if f.read(4)==b'\x7fELF':result.append(name)
    return result

def roots_for(names):return list(dict.fromkeys([*names,'simple-common',*(['simplepicker'] if set(names)&{'simple-tools','simpleclip'} else []),*(['simplefiles'] if 'simpletag' in names else [])]))

def put(source,target,mode=None):
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    if mode is not None:target.chmod(mode)

def write(target,text,mode=0o644):
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text);target.chmod(mode)

def shell_launcher(source,target):
    text=source.read_text()
    if 'bindir=' in text:
        lines=text.splitlines();index=next(i for i,line in enumerate(lines) if line.startswith('bindir='));lines.insert(index+1,'export PATH="$bindir:$PATH"');text='\n'.join(lines)+'\n'
    write(target,text,0o755)

def desktop(path,name,command,icon='applications-utilities',category='Utility',terminal=False):
    write(path,f'[Desktop Entry]\nType=Application\nName={name}\nExec={command}\nIcon={icon}\nTerminal={str(terminal).lower()}\nCategories={category};\n')

def framework_identity(common):
    """Version the native base by its source, ABI environment and build options."""
    digest=hashlib.sha256()
    for name in ('simple-ui.c','simple-ui.h','Makefile'):
        digest.update(name.encode());digest.update((common/name).read_bytes())
    for command in ([*shlex.split(os.environ.get('CC','cc')),'--version'],['pkg-config','--modversion','gtk4']):
        digest.update(subprocess.check_output(command).splitlines()[0])
    digest.update(platform.machine().encode())
    for name in ('CC','CFLAGS','CPPFLAGS','LDFLAGS','LDLIBS'):
        digest.update((name+'='+os.environ.get(name,'')).encode())
    return digest.hexdigest()


def prepare_framework(common, stage, names, env):
    identity=framework_identity(common)
    installed=Path.home()/'.local/lib/simple-common'
    library=installed/'libsimple-ui.so'
    reusable=False
    try:
        record=json.loads((installed/'build.json').read_text())
        reusable=isinstance(record,dict) and record.get('identity')==identity and record.get('sha256')==hashlib.sha256(library.read_bytes()).hexdigest()
    except (OSError,ValueError):pass
    if reusable:
        put(library,common/'libsimple-ui.so')
        # Source bundles preserve timestamps. A reused build is already current.
        os.utime(common/'libsimple-ui.so',None)
        print('Reusing installed Simple UI base.',flush=True)
    else:
        print('Building shared Simple UI base.',flush=True)
        subprocess.run(['make','-C',str(common)],env=env,check=True)
    target=stage/'.local/lib/simple-common'
    owners={}
    for filename in ('libsimple-ui.so','framework.css','palette.css','simple_ui.py'):
        put(common/filename,target/filename)
        owners[target/filename]=set(names)-{'simplewallpaper'}
    write(target/'build.json',json.dumps({'identity':identity,'sha256':hashlib.sha256((target/'libsimple-ui.so').read_bytes()).hexdigest()},indent=2)+'\n')
    owners[target/'build.json']=set(names)-{'simplewallpaper'}
    header=stage/'.local/include/simple-ui.h'
    put(common/'simple-ui.h',header)
    owners[header]=set(names)-{'simplewallpaper'}
    return owners


def stage_apps(here,catalog,root,names,options,stage,work,wallpapers=None):
    for name in roots_for(names):shutil.copytree(root/name,work/name,ignore=source_ignore)
    share=stage/'.local/share';bins=stage/'.local/bin'
    env=dict(os.environ,HOME=str(stage),XDG_CONFIG_HOME=str(stage/'.config'),XDG_DATA_HOME=str(share),XDG_CACHE_HOME=str(stage/'.cache'),XDG_STATE_HOME=str(stage/'.local/state'))
    # Current recipes only need the compiler here. Dependencies were checked earlier.
    owners={}
    if set(names)-{'simplewallpaper'}:
        owners.update(prepare_framework(work/'simple-common',stage,names,env))
    for name in names:
        before={p for p in stage.rglob('*') if p.is_file()}
        src=work/name;recipe=catalog[name]['recipe'];target=share/name
        if recipe not in ('wallpaper','tools','photo','files','notes','clip','capture','timer','pdf','image','bookmarks','garmin','tag','slideshow'):
            print('\nBuilding '+catalog[name]['name']+'…',flush=True)
            subprocess.run(['make','-C',str(src),'-j2'],env=env,check=True)
        if recipe=='player':
            subprocess.run([sys.executable,str(src/'install.py'),'--standalone','--home',str(stage)],env=env,check=True)
            shutil.move(bins/'simpleplayer-native',bins/'simpleplayer')
        elif recipe=='picker':
            write(src/'assets/wtype','#!/bin/sh\nexec /usr/bin/wtype "$@"\n',0o755)
            subprocess.run(['make','-C',str(src),'install',f'PREFIX={stage}/.local',f'HELPERDIR={share}/simplepicker/helpers'],env=env,check=True)
            write(bins/'simplepicker','#!/bin/sh\nbindir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexport PATH="$bindir:$PATH"\nif [ "$#" -eq 0 ]; then set -- --apps; fi\nexec "$bindir/simplepicker-native" "$@"\n',0o755)
            for filename in ('style.css','status-colors.css'):put(here/'defaults'/('picker-'+filename),target/filename)
        elif recipe in ('organizer','mail'):
            for p in src.iterdir():
                if p.suffix in ('.py','.css') and not p.name.startswith('setup-'):put(p,target/p.name)
            for folder in ('assets','defaults'):
                if (src/folder).exists():shutil.copytree(src/folder,target/folder,ignore=source_ignore)
            put(src/(name+'-native'),bins/(name+'-native'),0o755)
            launcher={'simplecalendar':'simple-calendar-launcher','simplecontacts':'simplecontacts-launcher','simplemail':'simplemail-launcher'}[name]
            shell_launcher(src/launcher,bins/name)
            if name=='simplecalendar':put(bins/name,bins/'simple-calendar',0o755)
            if name=='simplecontacts':put(bins/name,bins/'simplecontact',0o755)
        elif recipe in ('panel','lock','torrent'):
            put(src/name,bins/name,0o755)
            if recipe=='panel':
                shutil.copytree(src/'examples',target/'examples')
                put(src/'README.txt',target/'README.txt')
                put(src/'simplepanel-session-launcher',bins/'simplepanel-session',0o755)
                write(bins/'simplepanel-dashboard','#!/bin/sh\nbindir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexport PATH="$bindir:$PATH"\nexec "$bindir/simplepanel" --system-dashboard "$@"\n',0o755)
            if recipe=='lock':put(src/'lock.toml',target/'lock.toml')
            if recipe=='torrent':shutil.copytree(src/'defaults',target/'defaults')
        elif recipe=='clip':
            picker=work/'simplepicker'
            subprocess.run(['make','-C',str(picker),'-j2'],env=env,check=True)
            put(picker/'simplepicker-native',bins/'simpleclip-native',0o755)
            put(src/'simpleclip',bins/'simpleclip',0o755)
            for filename in ('defaults.json',):put(picker/'assets'/filename,target/filename)
            for filename in ('config.toml','keys.ini'):put(src/filename,target/filename)
            for filename in ('style.css','status-colors.css'):put(here/'defaults'/('picker-'+filename),target/filename)
            write(target/'wtype','#!/bin/sh\nexec wtype "$@"\n',0o755)
        elif recipe=='capture':
            put(src/'simplecapture',bins/'simplecapture',0o755)
            put(src/'record.sh',target/'record.sh',0o755)
        elif recipe=='tag':
            for filename in ('main.py','client.py','config.toml','keys.ini','README.md'):
                put(src/filename,target/filename)
            shutil.copytree(src/'bridge',target/'bridge',ignore=source_ignore)
            for filename in ('config.toml','keys.ini'):put(src/filename,target/'defaults'/filename)
            shell_launcher(src/'launcher',bins/name)
            put(work/'simplefiles/simplefiles',bins/'simplefiles',0o755)
        elif recipe=='slideshow':
            for filename in ('main.py','render.py','timeline.py','keys.ini','README.md'):
                put(src/filename,target/filename)
            put(src/'keys.ini',target/'defaults/keys.ini')
            shell_launcher(src/'launcher',bins/name)
        elif recipe=='garmin':
            for filename in ('main.py','client.py','details.py','README.md'):
                put(src/filename,target/filename)
            write(bins/name,'#!/bin/sh\nbindir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec python3 "$bindir/../share/simplegarmin/main.py" "$@"\n',0o755)
        elif recipe=='image':
            put(src/'simpleimage',bins/'simpleimage',0o755)
        elif recipe=='pdf':
            put(src/'simplepdf',bins/'simplepdf',0o755)
            put(src/'pdf_tools.py',target/'pdf_tools.py')
        elif recipe=='timer':
            put(src/'simpletimer',bins/'simpletimer',0o755)
        elif recipe=='bookmarks':
            put(src/'simplebookmarks',bins/'simplebookmarks',0o755)
        elif recipe=='notes':
            put(src/'simplenotes',bins/'simplenotes',0o755)
        elif recipe=='files':
            for filename in ('simplefiles','simplefiles-portal'):put(src/filename,bins/filename,0o755)
        elif recipe=='photo':
            put(src/'simplephoto',bins/'simplephoto',0o755)
        elif recipe=='wallpaper':
            for filename in ('main.py','README.md'):put(src/filename,target/filename)
            shell_launcher(src/'launcher',bins/name)
            if 'daylight' in options:shutil.copytree(wallpapers if wallpapers is not None else here/'wallpaper-packs',target/'themes')
        elif recipe=='tools':
            if 'simplepicker' not in names:
                picker=work/'simplepicker'
                write(picker/'assets/wtype','#!/bin/sh\nexec /usr/bin/wtype "$@"\n',0o755)
                subprocess.run(['make','-C',str(picker),'-j2'],env=env,check=True)
                subprocess.run(['make','-C',str(picker),'install',f'PREFIX={stage}/.local',f'HELPERDIR={share}/simplepicker/helpers'],env=env,check=True)
                for filename in ('style.css','status-colors.css'):put(here/'defaults'/('picker-'+filename),share/'simplepicker'/filename)
            for command,label in [('simple-sound','Sound'),('simple-network','Network'),('simple-network bt','Bluetooth'),('simple-disk','Disk usage'),('simple-cpu','CPU'),('simple-memory','Memory'),('simple-displays','Displays'),('simple-services','Services')]:
                desktop(share/'applications'/(command.replace(' ','-')+'.desktop'),'Simple '+label,command)
            for folder in TOOLS:shutil.copytree(src/folder,target/folder,ignore=source_ignore)
            for launcher in (src/'launchers').iterdir():shell_launcher(launcher,bins/launcher.name)
            # Shared Python menu helpers, without requiring the Picker application.
            shutil.copytree(work/'simplepicker/python',share/'simplepicker/python',dirs_exist_ok=True,ignore=source_ignore)
        else:raise ValueError('Unknown install recipe: '+recipe)
        command={'simplepanel':'simplepanel-dashboard','simple-tools':'simple-sound','simplecapture':'simplecapture --menu'}.get(name,name)
        desktop(share/'applications'/(name+'.desktop'),catalog[name]['name'],command+' %F' if recipe in ('photo','pdf','image','slideshow') else command,category='Graphics;Photography' if recipe in ('photo','image') else 'Office' if recipe=='pdf' else 'AudioVideo' if recipe=='slideshow' else 'Utility')
        for p in stage.rglob('*'):
            if p.is_file() and p not in before:owners[p]={name}
    keyboard_helper=share/'simple-common/simple_keyboard.py'
    put(root/'simple-common/simple_keyboard.py',keyboard_helper)
    owners[keyboard_helper]=set(names)
    before={p for p in stage.rglob('*') if p.is_file()}
    for p in (root/'simple-common').glob('*.py'):put(p,share/'simple-common'/p.name)
    for p in (root/'simple-common/assets/images').glob('*.png'):put(p,share/'simple/images'/p.name)
    for name in ('theme.css','aliases.css'):put(here/'defaults'/name,share/'simple'/name)
    put(here/'runtime/simple-open.py',bins/'simple-open',0o755)

    for p in stage.rglob('*'):
        if not p.is_file():continue
        if p not in before:owners[p]=set(names)
        rel=p.relative_to(stage).parts
        if rel[:3]==('.local','lib','simple-common') or rel[:2]==('.local','include'):owners[p]=set(names)-{'simplewallpaper'}
        if (rel[:3] in (('.local','share','simplepicker'),('.local','lib','simplepicker')) or p==bins/'simplepicker-native'):
            owners[p]=set(names)&{'simplepicker','simple-tools'}
    if 'simpletag' in names:owners[bins/'simplefiles']=set(names)&{'simpletag','simplefiles'}
    return owners

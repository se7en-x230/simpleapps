"""App-only staging recipes. Never invoke Newinit, setup-runtime or live services."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

TOOLS=('network','sound','disk','resources','displays','services')

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

def roots_for(names):return list(dict.fromkeys([*names,'simple-common',*(['simplepicker'] if 'simple-tools' in names else [])]))

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

def stage_apps(here,catalog,root,names,options,stage,work,wallpapers=None):
    for name in roots_for(names):shutil.copytree(root/name,work/name,ignore=source_ignore)
    share=stage/'.local/share';bins=stage/'.local/bin'
    env=dict(os.environ,HOME=str(stage),XDG_CONFIG_HOME=str(stage/'.config'),XDG_DATA_HOME=str(share),XDG_CACHE_HOME=str(stage/'.cache'),XDG_STATE_HOME=str(stage/'.local/state'))
    # Current recipes only need the compiler here. Dependencies were checked earlier.
    owners={}
    for name in names:
        before={p for p in stage.rglob('*') if p.is_file()}
        src=work/name;recipe=catalog[name]['recipe'];target=share/name
        if recipe not in ('wallpaper','tools','photo'):
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
                put(src/'simplepanel-session-launcher',bins/'simplepanel-session',0o755)
                write(bins/'simplepanel-dashboard','#!/bin/sh\nbindir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexport PATH="$bindir:$PATH"\nexec "$bindir/simplepanel" --system-dashboard "$@"\n',0o755)
            if recipe=='lock':put(src/'lock.toml',target/'lock.toml')
            if recipe=='torrent':shutil.copytree(src/'defaults',target/'defaults')
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
        command={'simplepanel':'simplepanel-dashboard','simple-tools':'simple-sound'}.get(name,name)
        desktop(share/'applications'/(name+'.desktop'),catalog[name]['name'],command+' %F' if recipe=='photo' else command,category='Graphics;Photography' if recipe=='photo' else 'Utility')
        for p in stage.rglob('*'):
            if p.is_file() and p not in before:owners[p]={name}
    if set(names)=={'simplephoto'}:return owners
    before={p for p in stage.rglob('*') if p.is_file()}
    for p in (root/'simple-common').glob('*.py'):put(p,share/'simple-common'/p.name)
    for p in (root/'simple-common/assets/images').glob('*.png'):put(p,share/'simple/images'/p.name)
    for name in ('theme.css','aliases.css'):put(here/'defaults'/name,share/'simple'/name)
    put(here/'runtime/simple-open.py',bins/'simple-open',0o755)

    for p in stage.rglob('*'):
        if not p.is_file():continue
        if p not in before:owners[p]=set(names)-{'simplephoto'}
        rel=p.relative_to(stage).parts
        if (rel[:3] in (('.local','share','simplepicker'),('.local','lib','simplepicker')) or p==bins/'simplepicker-native'):
            owners[p]=set(names)&{'simplepicker','simple-tools'}
    return owners

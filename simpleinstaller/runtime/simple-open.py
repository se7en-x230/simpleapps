#!/usr/bin/env python3
"""Small desktop-independent application resolver; commands are argv, not shell."""
import json
import os
from pathlib import Path
import shutil
import sys
import tomllib

KEYS={'terminal','browser','file_manager','media_player','mail'}
def preferences():
    path=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'simple/preferences.toml'
    try:
        with path.open('rb') as f: values=tomllib.load(f)
    except FileNotFoundError: return {}
    if set(values)-{'applications'}: raise ValueError('Unknown shared preference section')
    apps=values.get('applications',{})
    if not isinstance(apps,dict) or set(apps)-KEYS:raise ValueError('Unknown application preference')
    for key,value in apps.items():
        if not isinstance(value,list) or any(not isinstance(v,str) or not v or '\0' in v for v in value):
            raise ValueError(f'applications.{key} must be an argument array')
    return apps

def command(kind,args,prefs=None):
    if kind not in KEYS:raise ValueError('Choose terminal, browser, file_manager, media_player or mail')
    selected=(preferences() if prefs is None else prefs).get(kind,[])
    if selected:return selected+args
    if kind!='terminal':
        if len(args)!=1:raise ValueError('Pass one file, directory or URL')
        return ['xdg-open',*args]
    # Prefer the session's terminal without depending on a window manager.
    desktop=os.environ.get('XDG_CURRENT_DESKTOP','').lower()
    candidates=[]
    if 'kde' in desktop:candidates.append(['konsole','-e'])
    if 'gnome' in desktop:candidates.append(['gnome-terminal','--'])
    candidates += [['xdg-terminal-exec'],['konsole','-e'],['kitty','--'],['foot','--'],
                   ['alacritty','-e'],['gnome-terminal','--'],['xfce4-terminal','-x'],['xterm','-e']]
    for argv in candidates:
        if shutil.which(argv[0]):return argv+args if args else argv[:1]
    raise ValueError('No terminal found. Set applications.terminal in simple/preferences.toml.')

def main():
    if len(sys.argv)<2:raise ValueError('Usage: simple-open terminal|browser|file_manager|media_player|mail [arguments]')
    if sys.argv[1]=='--command':
        print(json.dumps(command(sys.argv[2],sys.argv[3:])));return
    argv=command(sys.argv[1],sys.argv[2:])
    os.execvp(argv[0],argv)
if __name__=='__main__':
    try:main()
    except (OSError,ValueError) as e:print('Simple applications: '+str(e),file=sys.stderr);sys.exit(1)

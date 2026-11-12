#!/usr/bin/env python3
"""Music folder picker: category priority is preserved for every search."""
import argparse
import os
from pathlib import Path
import unicodedata

REFRESH = '↻ Refresh library'
SUBGENRE_ROOTS = {'Classical', 'Electronic', 'Goth', 'Jazz', 'Metal', 'Rock', 'World'}

def normalize(text):
    if text.isascii(): return text.lower()
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold())
                   if not unicodedata.combining(c))

def is_genre(parts):
    return (len(parts) == 1 or
            (len(parts) == 2 and parts[0] in SUBGENRE_ROOTS) or
            (len(parts) == 3 and parts[:2] == ['Electronic', 'Industrial & EBM']) or
            (len(parts) == 3 and parts[:2] == ['Rock', 'Psychedelic & Classic Rock']
             and parts[2] in {'Krautrock Plus', 'Tickle My Brain'}))

def tier(path):
    parts = path.split('/')
    return 0 if is_genre(parts) else 1 if is_genre(parts[:-1]) else 2

class Library:
    def __init__(self, paths):
        self.groups = [[], [], []]
        self.children = {}
        for path in paths:
            if not path: continue
            if path.count('/') == 1:
                parent, child = path.split('/', 1)
                self.children.setdefault(parent, []).append(child)
            normal = normalize(path)
            entry = (path, normal, normal.rsplit('/', 1)[-1], path.count('/'))
            self.groups[tier(path)].append(entry)
        for group in self.groups:
            group.sort(key=lambda e: (e[3], e[2], e[1]))
        self.paths = [entry[0] for group in self.groups for entry in group]

    def search(self, query, limit=None):
        words = normalize(query).split()
        if not words: return self.paths[:] if limit is None else self.paths[:limit]
        phrase=' '.join(words)
        ranked=[]
        for group in self.groups:
            for path,normal,leaf,depth in group:
                if not all(word in normal for word in words):continue
                rank=(0 if leaf==phrase else 1 if leaf.startswith(phrase) else
                      2 if all(word in leaf for word in words) else 3)
                ranked.append(((rank,tier(path),depth,len(leaf),leaf,normal),path))
        ranked.sort(key=lambda item:item[0])
        result=[path for _,path in ranked]
        return result if limit is None else result[:limit]



def presentation(path):
    parts = path.split('/')
    kind = ('Genre', 'Artist / collection', 'Album / folder')[min(tier(path), 2)]
    return parts[-1], kind + ('  ·  ' + ' › '.join(parts[:-1]) if len(parts) > 1 else '  ·  Music library')


def menu(search, **kwargs):
    import sys
    import importlib.util
    for root in (Path(__file__).resolve().parents[2],Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share')),Path.home()/'.local/src'):
        library=root/'simplepicker/python'
        if library.is_dir():sys.path.insert(0,str(library));break
    from ui import show_menu
    spec = importlib.util.spec_from_file_location('simpleplayer_config', Path(__file__).with_name('simpleplayer-config.py'))
    config = importlib.util.module_from_spec(spec); spec.loader.exec_module(config)
    config_path, _, prefs = config.configuration()
    css = config_path.parent/'style.css'
    if css.is_file(): prefs['theme'] = os.environ.get('SIMPLEPICKER_THEME') or str(css)
    prefs.update(kwargs)
    # Music uses an ordinary floating window, rather than the full-screen overlay.
    # Keep the global configuration and override only the window mode per launch.
    import re
    import tempfile
    import settings
    previous_path = os.environ.get('SIMPLEPICKER_CONFIG')
    original = settings.path()
    text = original.read_text() if original.is_file() else ''
    match = re.search(r'(?ms)^\[ui\]\s*\n(.*?)(?=^\[|\Z)', text)
    if match:
        section = match.group(1)
        section = re.sub(r'(?m)^layer_shell\s*=.*$', 'layer_shell = "off"', section) if re.search(r'(?m)^layer_shell\s*=', section) else 'layer_shell = "off"\n' + section
        text = text[:match.start(1)] + section + text[match.end(1):]
    else:
        text += '\n[ui]\nlayer_shell = "off"\n'
    with tempfile.NamedTemporaryFile(mode='w', prefix='.simpleplayer-window-', suffix='.toml', dir=original.parent) as temporary:
        temporary.write(text)
        temporary.flush()
        snapshot = Path(temporary.name)
        # settings.path may have an explicit override; temporarily select the snapshot.
        previous_settings_path = settings._path
        settings._path = snapshot
        try:
            return show_menu(search, title='Simpleplayer', default_icon='folder-music-symbolic', **prefs)
        finally:
            settings._path = previous_settings_path


def show_picker(library):
    # Format only visible results, then reuse their captions while typing.
    cache = {}
    class Texts(dict):
        def __init__(self, column): self.column = column
        def get(self, value, default=None):
            if value == REFRESH:
                return ('Refresh music library', 'Scan for new artists and albums')[self.column]
            if '/' not in value:
                if self.column == 0:
                    return {'Plalists': 'Playlists'}.get(value, value)
                children = library.children.get(value, [])
                if value in SUBGENRE_ROOTS:
                    return ' · '.join(sorted(children, key=normalize)[:3]) or 'Explore this collection'
                return f'{len(children)} collections' if children else 'Explore this collection'
            if value not in cache: cache[value] = presentation(value)
            return cache[value][self.column]
    from gi.repository import Gio
    icon_dir = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'simplepicker/music/icons'
    genre_names = {'AI Music':'ai', 'Blues':'blues', 'Classical':'classical',
                   'Electronic':'electronic', 'Goth':'goth', 'Jazz':'jazz', 'Metal':'metal',
                   'Mixes & Playlists':'mixes', 'Mixes':'mixes', 'Plalists':'mixes', 'Playlists':'mixes', 'Rock':'rock', 'Soul & Funk':'soul',
                   'Vocals & Songwriters':'vocals', 'World':'world'}
    genre_icons = {name:Gio.FileIcon.new(Gio.File.new_for_path(str(icon_dir/(icon+'-symbolic.svg'))))
                   for name,icon in genre_names.items() if (icon_dir/(icon+'-symbolic.svg')).is_file()}
    roots = [path for path in library.paths if '/' not in path]
    return menu(lambda query: library.search(query, limit=200) if query.strip() else roots, prompt='Your music · search genres, artists, albums…',
                labels=Texts(0), subtitles=Texts(1), icons=genre_icons,
                shortcuts=[('r', 'Refresh library', REFRESH)])


def folder_menu(folder, library, browse=False):
    folder = folder.resolve()
    try: relative = folder.relative_to(library.resolve())
    except ValueError: raise ValueError('Folder is outside the music library')
    crumb = ' › '.join(relative.parts) or 'Music library'
    if browse:
        paths = sorted((p for p in folder.iterdir() if p.is_dir() and not p.name.startswith('.')
                        and not p.name.lower().startswith('convert') and p.name != 'Backups'),
                       key=lambda p: normalize(p.name))
        rows = [str(p) for p in paths]
        labels = {str(p):p.name for p in paths}
        subtitles = {str(p):crumb for p in paths}
        labels['back'] = 'Back'; subtitles['back'] = 'Return to folder actions'
        return menu(lambda q:[p for p in rows if all(w in normalize(labels[p]) for w in normalize(q).split())],
                    prompt=crumb, actions=['back'], labels=labels, subtitles=subtitles,
                    shortcuts=[('h','Back','back')])
    rows = ['shuffle','ordered','browse','library']
    labels = {'shuffle':'Shuffle and play','ordered':'Play in order',
              'browse':'Browse subfolders','library':'Back to your music'}
    subtitles = {'shuffle':'All music in this folder and its subfolders · repeat playlist',
                 'ordered':'Play files in sorted order · repeat playlist',
                 'browse':'Choose an artist or album inside this folder',
                 'library':'Back to the full music library'}
    icons = {'shuffle':'media-playlist-shuffle-symbolic','ordered':'media-playback-start-symbolic',
             'browse':'folder-music-symbolic','library':'go-previous-symbolic'}
    def actions(query):
        query = normalize(query).strip()
        # Prefer action-name prefixes so s/o/b/l each identify exactly one action.
        prefixes = [r for r in rows if query and r.startswith(query)]
        return prefixes or [r for r in rows if all(w in normalize(labels[r]) for w in query.split())]
    return menu(actions, auto_accept=False,
                prompt=crumb, labels=labels, subtitles=subtitles, icons=icons, height=360,
                shortcuts=[('h','Back','back')])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('index', nargs='?', type=Path)
    parser.add_argument('--search', help='Print ranked paths without opening the window')
    parser.add_argument('--folder', type=Path)
    parser.add_argument('--library', type=Path)
    parser.add_argument('--subfolders', action='store_true')
    args = parser.parse_args()
    if args.folder:
        if not args.library: parser.error('--folder requires --library')
        selected = folder_menu(args.folder, args.library, args.subfolders)
    else:
        if not args.index: parser.error('Provide a folder index')
        library = Library(args.index.read_text(errors='replace').splitlines())
        if args.search is not None:
            print('\n'.join(library.search(args.search))); return
        selected = show_picker(library)
    if selected is None: raise SystemExit(1)
    print(selected)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile

ROOT=Path(__file__).resolve().parent
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result

picker=module('picker',ROOT/'scripts/simpleplayer-picker.py')
paths=['Jazz','Jazz/Modern','Jazz/Modern/Björk','Jazz/Modern/Björk/Debut','Rock','Rock/Artist/Album','Plalists']
library=picker.Library(paths)
assert library.search('bjork')==['Jazz/Modern/Björk','Jazz/Modern/Björk/Debut']
assert library.children['Jazz']==['Modern']
assert library.search('rock album')==['Rock/Artist/Album']
assert len(library.search('',limit=2))==2
installer=module('installer',ROOT/'install.py')
with tempfile.TemporaryDirectory() as tmp:
    home=Path(tmp)
    config=home/'.config/simplepicker/music/config.toml'
    config.parent.mkdir(parents=True);config.write_text('music_dir = "/my/music"\n')
    installer.install(home)
    assert config.read_text()=='music_dir = "/my/music"\n'
    launcher=home/'.local/bin/simpleplayer'
    assert launcher.stat().st_mode&0o111
    before=launcher.stat().st_mtime_ns
    installer.install(home)
    assert launcher.stat().st_mtime_ns==before
    assert (config.parent/'scripts/simpleplayer-session.py').read_bytes()==(ROOT/'scripts/simpleplayer-session.py').read_bytes()
print('Simpleplayer PASS: cached search, Unicode search, preserved settings and session helper, repeatable install')

# Exercise artwork and IPC without changing the desktop's playback session.
from unittest.mock import patch
bridge=module('bridge',ROOT/'bridge.py')
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);(root/'Artist/Album').mkdir(parents=True)
    song=root/'Artist/Album/song.mp3';song.write_bytes(b'fixture')
    cover=song.parent/'cover.jpg';cover.write_bytes(b'cover fixture')
    with patch.object(bridge.config,'music_directory',return_value=str(root)), patch.dict('os.environ',{'XDG_CACHE_HOME':str(root/'cache')}):
        backend=bridge.Bridge();events=[];backend.send=lambda **data:events.append(data)
        try:
            backend.library.folder('../outside')
            raise AssertionError('Traversal accepted')
        except ValueError:pass
        backend.artwork(str(song));backend.art_worker.shutdown(wait=True)
        assert events[-1]==dict(event='art',path=str(song),file=str(cover))
        with patch.object(bridge,'ipc') as ipc:
            backend.handle({'action':'control','command':'next'})
            ipc.assert_called_once_with(['playlist-next','force'])
        with patch.object(bridge,'ipc',side_effect=OSError('No session')):
            backend.handle({'action':'status'})
            assert events[-1]['playing'] is False
print('Simpleplayer PASS: artwork lookup, folder containment, controls and idle state')

with patch.object(bridge,'Library'):
    backend=bridge.Bridge();events=[];backend.send=lambda **data:events.append(data)
    with patch.object(bridge,'ipc',side_effect=[{'TITLE':'Song','ARTIST':'Artist','ALBUM':'Album','DATE':'1986-01-01'},True,'/fixture/song.mp3',False,102,275]), patch.object(backend,'artwork'):
        backend.handle({'action':'status'})
    assert events[-1]['title']=='Song' and events[-1]['artist']=='Artist'
    assert events[-1]['album']=='Album' and events[-1]['year']=='1986'
    assert events[-1]['order']=='ordered'
    assert events[-1]['position']==102 and events[-1]['duration']==275
    backend.art_worker.shutdown(wait=True)
print('Simpleplayer PASS: metadata casing and album year')

ranked=picker.Library(['Rock/Queen Tribute','Rock/Queensryche','Rock/Queen/Album','Rock/Queen'])
assert ranked.search('queen')[0]=='Rock/Queen'
assert ranked.search('QUEEN',1)==['Rock/Queen']
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);cfg=root/'config/wallpaper';cfg.mkdir(parents=True)
    data=root/'data/wallpaper';data.mkdir(parents=True)
    (data/'current.png').write_bytes(b'static');(data/'scheduled.png').write_bytes(b'daylight')
    (data/'daylight-current.png').symlink_to(data/'scheduled.png')
    with patch.dict('os.environ',{'XDG_CONFIG_HOME':str(root/'config'),'XDG_DATA_HOME':str(root/'data')}):
        for mode,expected in [('daylight','scheduled.png'),('static','current.png')]:
            (cfg/'config.json').write_text(bridge.json.dumps({'mode':mode}))
            backend.wallpaper()
            assert events[-1]['file']==str(data/expected)
print('Simpleplayer PASS: best-match ranking and current wallpaper selection')

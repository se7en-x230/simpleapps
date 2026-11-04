#!/usr/bin/env python3
"""Serialize and replace only Simpleplayer-owned mpv processes."""
from contextlib import ExitStack
import tempfile
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HOME=Path.home()
ROOT=Path(os.environ.get('XDG_RUNTIME_DIR', Path(os.environ.get('XDG_CACHE_HOME',HOME/'.cache'))))/'simpleplayer'
MARKER='--input-ipc-server='+str(ROOT/'mpv.sock')
LAUNCHER=str(Path(os.environ.get('XDG_CONFIG_HOME',HOME/'.config'))/'mango/scripts/simpleplayer')


def argv(pid):
    return (Path('/proc')/str(pid)/'cmdline').read_bytes().decode(errors='replace').rstrip('\0').split('\0')


def owned(pid):
    proc=Path('/proc')/str(pid)
    if proc.stat().st_uid != os.getuid() or (proc/'comm').read_text().strip() != 'mpv': return False
    args=argv(pid)
    if MARKER in args: return True
    # Adopt playback started by the older launcher before this update.
    if not all(flag in args for flag in ('--no-video','--vo=null','--audio-display=no','--loop-playlist')): return False
    stat=(proc/'stat').read_text().rsplit(')',1)[1].split()
    parent=argv(int(stat[1]))
    return len(parent)>1 and Path(parent[0]).name in ('bash','sh') and parent[1]==LAUNCHER


def stop():
    handles=[]
    try:
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit(): continue
            fd=None
            try:
                fd=os.pidfd_open(int(proc.name))
                if not owned(int(proc.name)):
                    os.close(fd);continue
                signal.pidfd_send_signal(fd,signal.SIGTERM)
                handles.append(fd)
            except (OSError,ValueError):
                if fd is not None: os.close(fd)
        # pidfds cannot target a reused PID; wait for old playback before starting new.
        import select
        poll=select.poll()
        for fd in handles: poll.register(fd,select.POLLIN)
        pending=set(handles);deadline=time.monotonic()+3
        while pending and time.monotonic()<deadline:
            for fd,_ in poll.poll(100):
                pending.discard(fd);poll.unregister(fd)
        for fd in pending:
            try: signal.pidfd_send_signal(fd,signal.SIGKILL)
            except ProcessLookupError: pass
        if pending:
            deadline=time.monotonic()+2
            while pending and time.monotonic()<deadline:
                for fd,_ in poll.poll(100): pending.discard(fd);poll.unregister(fd)
            if pending: raise RuntimeError('Previous Simpleplayer playback did not stop')
    finally:
        for fd in handles: os.close(fd)


def playlist_files(path):
    """Resolve a local M3U before replacing playback; relative paths stay portable."""
    from urllib.parse import urlsplit, unquote
    path=Path(path).absolute()
    files=[]
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip() or line.startswith('#'):continue
        if line.startswith('file://'):
            uri=urlsplit(line)
            if uri.netloc not in ('','localhost'):raise ValueError('Playlist references a non-local file host')
            item=Path(unquote(uri.path))
        elif '://' in line:
            raise ValueError('Folder playlists must reference local music files')
        else:item=Path(line)
        if not item.is_absolute():item=path.parent/item
        item=item.resolve()
        if not item.is_file() or not os.access(item,os.R_OK):raise ValueError('Playlist track missing or unreadable: '+str(item))
        files.append(os.fsencode(item))
    if not files:raise ValueError('Folder playlist is empty: '+str(path))
    return files


def main():
    if len(sys.argv)<2 or sys.argv[1] not in ('stop','play'): raise SystemExit('Usage: simpleplayer-session.py stop|play [mpv options]')
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    options = sys.argv[2:]
    with ExitStack() as cleanup:
        streamed = '--files-from-stdin' in options
        saved = '--playlist-file' in options
        if streamed and saved:raise ValueError('Choose one playlist input')
        files=None
        if saved:
            if sys.argv[1] != 'play':raise ValueError('Playlist input requires play')
            index=options.index('--playlist-file')
            if index+1>=len(options):raise ValueError('Missing playlist filename')
            files=playlist_files(options[index+1])
            del options[index:index+2]
        if streamed:
            if sys.argv[1] != 'play': raise ValueError('File input requires play')
            options.remove('--files-from-stdin')
            data = sys.stdin.buffer.read()
            if not data or not data.endswith(b'\0'):
                raise ValueError('Expected NUL-separated music filenames')
            files = data[:-1].split(b'\0')
            if not all(files): raise ValueError('Empty music filename')
        if files is not None:
            playlist = cleanup.enter_context(tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', prefix='playlist-', suffix='.m3u', dir=ROOT))
            playlist.write('#EXTM3U\n')
            for filename in files:
                # File URIs preserve spaces, #, Unicode and even embedded newlines.
                playlist.write(Path(os.fsdecode(filename)).absolute().as_uri() + '\n')
            playlist.flush()
            options.append('--playlist=' + playlist.name)
        with (ROOT/'session.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            stop()
            if sys.argv[1]=='stop': return 0
            child=subprocess.Popen(['mpv',MARKER,*options],close_fds=True,
                                   stdin=subprocess.DEVNULL if streamed or saved else None)
        # Browsing does not touch this session; another play selection may replace it.
        # The playlist belongs to this child and is removed when playback ends.
        return child.wait()

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as error:
        print('Simpleplayer: '+str(error),file=sys.stderr);raise SystemExit(1)

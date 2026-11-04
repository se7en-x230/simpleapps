#!/usr/bin/env python3
"""Native Simpleplayer data bridge. Cached browsing; explicit playback and refresh."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor

HERE=Path(__file__).resolve().parent
for common in (HERE.parent/'simple-common',Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'simple-common'):
    if (common/'simple_images.py').is_file():sys.path.insert(0,str(common));break
from simple_images import resolve as resolve_idle_image, bundled as bundled_image
SCRIPTS=HERE/'scripts' if (HERE/'scripts').is_dir() else Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'simplepicker/music/scripts'
def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,SCRIPTS/filename)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
picker=load('music_index','simpleplayer-picker.py')
config=load('music_config','simpleplayer-config.py')
streams=load('music_streams','simpleplayer-streams.py')
ICONS={'AI Music':'ai','Blues':'blues','Classical':'classical','Electronic':'electronic','Goth':'goth',
       'Jazz':'jazz','Metal':'metal','Mixes':'mixes','Plalists':'mixes','Playlists':'mixes',
       'Rock':'rock','Soul & Funk':'soul','Vocals & Songwriters':'vocals','World':'world'}

def ipc(command):
    runtime=Path(os.environ.get('XDG_RUNTIME_DIR',Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))))/'simpleplayer'
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(.2);client.connect(str(runtime/'mpv.sock'))
        client.sendall((json.dumps({'command':command,'request_id':1})+'\n').encode())
        with client.makefile() as stream:
            for line in stream:
                result=json.loads(line)
                if result.get('request_id')==1:
                    if result.get('error')!='success':raise ValueError(result.get('error'))
                    return result.get('data')

class Library:
    def __init__(self):
        self.root=Path(config.music_directory()).resolve()
        self.cache=Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'simpleplayer'
        self.paths=[];self.reload()
    def reload(self):
        index=self.cache/'folders.index';saved=self.cache/'folders.root'
        self.paths=index.read_text(errors='replace').splitlines() if index.exists() and saved.exists() and saved.read_text().strip()==str(self.root) else []
        self.index=picker.Library(self.paths)
        self.children={}
        for path in self.index.paths:
            parent,_,leaf=path.rpartition('/')
            self.children.setdefault(parent,[]).append(path)
    def folder(self,path):
        folder=(self.root/path).resolve()
        if not folder.is_relative_to(self.root) or not folder.is_dir():raise ValueError('Music folder is missing or outside your library.')
        return folder
    def rows(self,path,query):
        self.folder(path)
        paths=self.index.search(query,200) if query.strip() else self.children.get(path,[])[:200]
        result=[]
        for value in paths:
            leaf=value.rsplit('/',1)[-1]
            count=len(self.children.get(value,[]))
            subtitle=(' › '.join(value.split('/')[:-1]) if query.strip() and '/' in value else
                      f'{count} folder'+('s' if count!=1 else '') if count else 'Play this collection')
            result.append({'path':value,'title':'Playlists' if leaf=='Plalists' else leaf,
                           'subtitle':subtitle,'icon':ICONS.get(value,'')})
        return result

class Bridge:
    def __init__(self):
        self.library=Library();self.lock=threading.Lock();self.busy=False
        self.track_path=None;self.art_retry_at=float("inf");self.art_worker=ThreadPoolExecutor(max_workers=1)
        self.streams=streams.Streams();self.search_worker=ThreadPoolExecutor(max_workers=2);self.search_future=None;self.browse_id=0
    def artwork(self,path):
        if path==self.track_path and time.monotonic()<self.art_retry_at:return
        self.track_path=path;self.art_retry_at=float("inf")
        def find():
            if path!=self.track_path:return
            result=''
            try:
                track=Path(path)
                if '://' in path:
                    item=self.streams.current(path)
                    result=self.streams.artwork(item)
                    return
                if not track.is_file():return
                for name in ('cover.jpg','folder.jpg','front.jpg','cover.png','folder.png','cover.webp','Cover.jpg','Folder.jpg'):
                    image=track.parent/name
                    if image.is_file():result=str(image);break
                if not result:
                    stat=track.stat();key=hashlib.sha256(f'{path}:{stat.st_mtime_ns}:{stat.st_size}'.encode()).hexdigest()
                    cache=self.library.cache/'covers/native';cache.mkdir(parents=True,exist_ok=True)
                    image=cache/(key+'.jpg');missing=cache/(key+'.none')
                    if not image.exists() and not missing.exists():
                        temp=cache/(key+'.tmp.jpg')
                        try:
                            done=subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-i',str(track),
                                '-map','0:v:0','-frames:v','1','-vf','scale=600:600:force_original_aspect_ratio=decrease',
                                '-y',str(temp)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=6)
                            if done.returncode==0 and temp.exists():temp.replace(image)
                            else:missing.touch()
                        finally:temp.unlink(missing_ok=True)
                    if image.is_file():result=str(image)
            except (OSError,ValueError,subprocess.TimeoutExpired):pass
            finally:
                if path==self.track_path:
                    self.art_retry_at=time.monotonic()+30 if not result and '://' in path else float('inf')
                    self.send(event='art',path=path,file=result)
        self.art_worker.submit(find)
    def send(self,**data):
        with self.lock:
            try:print(json.dumps(data,ensure_ascii=False),flush=True)
            except BrokenPipeError:pass
    def task(self,kind,path='',order='shuffle',source='local'):
        if self.busy:return
        self.busy=True;self.send(event='busy',busy=True,message='Refreshing library…' if kind=='refresh' else 'Preparing your music…')
        def run():
            try:
                engine=HERE/'playback.sh'
                if kind=='refresh':
                    done=subprocess.run(['bash',str(engine),'--refresh-library'],capture_output=True,text=True)
                    if done.returncode:raise ValueError(done.stderr.strip() or 'Library refresh failed.')
                    self.library.reload();self.send(event='refreshed')
                else:
                    folder=self.library.folder(path) if source=='local' else None
                    if order not in ('shuffle','ordered'):raise ValueError('Unknown playback order')
                    runtime=Path(os.environ.get('XDG_RUNTIME_DIR',Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))))/'simpleplayer'
                    runtime.mkdir(parents=True,exist_ok=True)
                    command=['bash',str(engine),'--play-folder',str(folder),order]
                    if source!='local':
                        item,args=self.streams.play_args(source,path)
                        streams.atomic_json(self.streams.state,item)
                        command=[sys.executable,str(SCRIPTS/'simpleplayer-session.py'),'play',*args]
                    with (runtime/'last-play.log').open('w') as log:
                        process=subprocess.Popen(command,
                            stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
                    # Playback owns its lifetime; closing the app does not stop it.
                    try:
                        code=process.wait(timeout=.5)
                        if code:raise ValueError((runtime/'last-play.log').read_text()[-1000:] or 'Playback failed.')
                    except subprocess.TimeoutExpired:
                        def watch():
                            code=process.wait()
                            if code not in (0,130,143,-15):self.send(event='error',message=(runtime/'last-play.log').read_text()[-1000:])
                        threading.Thread(target=watch,daemon=True).start()
                    self.send(event='notice',message='Playing '+(folder.name if folder else item['title']),order=order if folder else 'ordered')
            except Exception as error:self.send(event='error',message=str(error))
            finally:self.busy=False;self.send(event='busy',busy=False)
        threading.Thread(target=run,daemon=True).start()
    def wallpaper(self):
        image=resolve_idle_image('idle')
        try:
            stat=image.stat() if image else None
            self.send(event='wallpaper',file=str(image) if image else '',fallback=str(bundled_image('idle') or ''),stamp=f'{image}:{stat.st_mtime_ns}' if stat else '')
        except OSError:self.send(event='wallpaper',file='',fallback=str(bundled_image('idle') or ''),stamp='')
    def handle(self,data):
        action=data.get('action')
        if action=='browse':
            self.browse_id=data.get('id',0)
            if self.search_future:self.search_future.cancel()
            source=data.get('source','local')
            if source!='local':
                request_id=self.browse_id;query=data.get('query','')
                self.send(event='searching',id=request_id,message='Searching…' if query.strip() else 'Saved favourites · / to search')
                def search():
                    try:
                        if request_id!=self.browse_id:return
                        rows=self.streams.search(source,query)
                        if request_id==self.browse_id:self.send(event='rows',id=request_id,rows=rows,message='No results. Try another search.' if query.strip() else 'No favourites yet. Press / to search or paste a link.',source=source)
                    except Exception as error:
                        if request_id==self.browse_id:self.send(event='rows',id=request_id,rows=[],message=str(error),source=source)
                self.search_future=self.search_worker.submit(search)
                return
            path=data.get('path','');query=data.get('query','')
            self.send(event='rows',id=data.get('id',0),path=path,rows=self.library.rows(path,query),
                      title=path.rsplit('/',1)[-1] if path else 'Your music',
                      message='No folders here. Play this collection or go back.' if path else 'Refresh the library to index new music.')
        elif action=='refresh':self.task('refresh')
        elif action=='play':self.task('play',data.get('path',''),data.get('order','shuffle'),data.get('source','local'))
        elif action=='favourite':
            saved=self.streams.favourite(data.get('source'),data.get('path'))
            self.send(event='saved',message='Saved to favourites' if saved else 'Removed from favourites')
        elif action=='control':
            commands={'previous':['playlist-prev','force'],'next':['playlist-next','force'],
                      'pause':['cycle','pause'],'stop':['quit']}
            try:ipc(commands[data['command']])
            except (OSError,ValueError):pass
        elif action=='status':
            self.wallpaper()
            try:
                meta={str(k).lower():v for k,v in (ipc(['get_property','metadata']) or {}).items()};pause=ipc(['get_property','pause'])
                path=ipc(['get_property','path']) or ''
                try:order='shuffle' if ipc(['get_property','options/shuffle']) else 'ordered'
                except (OSError,ValueError):order=''
                try:position=ipc(['get_property','time-pos']);duration=ipc(['get_property','duration'])
                except (OSError,ValueError):position=duration=None
                online=self.streams.current(path) if '://' in path else {}
                try:media_title=ipc(['get_property','media-title']) if online else ''
                except (OSError,ValueError):media_title=''
                self.send(event='status',live=online.get('source')=='radio',playing=True,paused=pause,order=order,position=position,duration=duration,title=meta.get('title') or media_title or online.get('title') or Path(path).stem,
                          artist=meta.get('artist') or (online.get('title') if online.get('source')=='radio' else online.get('subtitle')) or 'Simpleplayer',
                          album=meta.get('album') or '',year=str(meta.get('date') or meta.get('year') or meta.get('originaldate') or '')[:4],path=path)
                self.artwork(path)
            except (OSError,ValueError):
                self.track_path=None
                self.send(event='status',playing=False,title='Ready when you are',artist='Choose a collection, then play or shuffle.',path='',album='')

def main():
    bridge=Bridge()
    for line in sys.stdin:
        try:bridge.handle(json.loads(line))
        except Exception as error:bridge.send(event='error',message=str(error))

if __name__=='__main__':main()

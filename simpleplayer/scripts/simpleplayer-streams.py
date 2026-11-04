#!/usr/bin/env python3
"""Optional public streams. No account integration; no requests until asked."""
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import socket
import subprocess
import tempfile
import threading
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, urlopen

SOURCES=('radio','youtube')

def http_url(value):
    if not isinstance(value,str) or len(value)>8192 or any(ord(c)<32 for c in value):raise ValueError('Enter a valid HTTP or HTTPS stream link.')
    parsed=urlsplit(value)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:raise ValueError('Only public HTTP or HTTPS links are supported.')
    return value

def youtube_url(value):
    http_url(value)
    if urlsplit(value).hostname.lower() not in ('youtube.com','www.youtube.com','m.youtube.com','music.youtube.com','youtu.be'):raise ValueError('Use a YouTube link in the YouTube source.')
    return value

def youtube_thumbnail(url):
    try:youtube_url(url)
    except ValueError:return ''
    parsed=urlsplit(url);parts=parsed.path.strip('/').split('/')
    video=(parts[0] if parsed.hostname=='youtu.be' else parts[1] if len(parts)>1 and parts[0] in ('shorts','live','embed') else parse_qs(parsed.query).get('v',[''])[0])
    return 'https://i.ytimg.com/vi/'+video+'/hqdefault.jpg' if re.fullmatch(r'[A-Za-z0-9_-]{11}',video) else ''

def get_bytes(url,limit=2_000_000):
    request=Request(http_url(url),headers={'User-Agent':'Simpleplayer/1.0','Accept':'application/json,image/*;q=0.8,*/*;q=0.5'})
    with urlopen(request,timeout=8) as response:
        http_url(response.url)
        result=response.read(limit+1)
    if len(result)>limit:raise ValueError('Server response is too large.')
    return result

def atomic_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
        os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)

class Streams:
    def __init__(self):
        home=Path.home()
        self.file=Path(os.environ.get('XDG_CONFIG_HOME',home/'.config'))/'simpleplayer/streams.json'
        self.cache=Path(os.environ.get('XDG_CACHE_HOME',home/'.cache'))/'simpleplayer/stream-art'
        self.state=Path(os.environ.get('XDG_RUNTIME_DIR',Path(os.environ.get('XDG_CACHE_HOME',home/'.cache'))))/'simpleplayer/stream.json'
        self.lock=threading.Lock();self.items={};self.mirrors=None
    def saved(self):
        if not self.file.exists():return []
        data=json.loads(self.file.read_text())
        if not isinstance(data,list):raise ValueError('streams.json must contain a list of favourites.')
        return [self.normalise(x) for x in data]
    def normalise(self,item):
        source=item.get('source');url=item.get('path',item.get('url',''))
        if source not in SOURCES:raise ValueError('Unknown stream source')
        (youtube_url if source=='youtube' else http_url)(url)
        return dict(source=source,path=url,title=str(item.get('title') or urlsplit(url).hostname),subtitle=str(item.get('subtitle') or source.title()),thumbnail=str(item.get('thumbnail') or ''),icon='')
    def remember(self,rows):
        with self.lock:
            for row in rows:self.items[(row['source'],row['path'])]=row
        return rows
    def item(self,source,url):
        with self.lock:found=self.items.get((source,url))
        return found or next((x for x in self.saved() if x['source']==source and x['path']==url),None) or self.normalise(dict(source=source,path=url))
    def favourite(self,source,url):
        row=self.item(source,url);saved=self.saved()
        exists=any(x['source']==source and x['path']==url for x in saved)
        saved=[x for x in saved if (x['source'],x['path'])!=(source,url)]
        if not exists:saved.append(row)
        atomic_json(self.file,saved)
        return not exists
    def radio(self,query):
        # Discover the directory's mirrors; keep a short fallback if DNS discovery fails.
        if self.mirrors is None:
            try:
                addresses=socket.getaddrinfo('all.api.radio-browser.info',443,type=socket.SOCK_STREAM)
                hosts={socket.gethostbyaddr(x[4][0])[0] for x in addresses}
                self.mirrors=['https://'+h for h in hosts if h.endswith('.api.radio-browser.info')]
            except OSError:self.mirrors=[]
            random.shuffle(self.mirrors)
            self.mirrors=(self.mirrors+['https://de1.api.radio-browser.info','https://nl1.api.radio-browser.info'])[:3]
        parameters={'name':query,'hidebroken':'true','limit':40,'order':'clickcount','reverse':'true'}
        error=None
        for host in self.mirrors:
            try:
                data=json.loads(get_bytes(host+'/json/stations/search?'+urlencode(parameters)))
                result=[]
                for station in data:
                    try:
                        result.append(self.normalise(dict(source='radio',path=station.get('url_resolved') or station['url'],title=station['name'].strip(),subtitle=' · '.join(str(x) for x in (station.get('country'),station.get('codec'),str(station.get('bitrate'))+' kbps' if station.get('bitrate') else '') if x),thumbnail=station.get('favicon',''))))
                    except (KeyError,ValueError):continue
                return result
            except (OSError,ValueError) as exc:error=exc
        raise ValueError('Radio directory unavailable. Saved stations and direct links still work.') from error
    def youtube(self,query):
        if not shutil.which('yt-dlp'):raise ValueError('YouTube needs the optional yt-dlp package. Local music and radio work without it.')
        target=youtube_url(query) if '://' in query else 'ytsearch25:'+query
        try:
            result=subprocess.run(['yt-dlp','--ignore-config','--flat-playlist','--dump-single-json','--playlist-end','25','--socket-timeout','8','--retries','1','--',target],capture_output=True,text=True,timeout=35)
        except subprocess.TimeoutExpired:raise ValueError('YouTube search timed out. Try again or use a direct link.')
        if result.returncode:raise ValueError('YouTube could not load this search or link. Try another public video, or update yt-dlp.')
        data=json.loads(result.stdout);entries=data.get('entries') or [data];rows=[]
        if '://' in query and data.get('entries'):
            rows.append(self.normalise(dict(source='youtube',path=query,title=data.get('title') or 'YouTube playlist',subtitle='Play entire playlist')))
        for entry in entries:
            if not entry:continue
            url=entry.get('webpage_url') or entry.get('url') or 'https://www.youtube.com/watch?v='+entry.get('id','')
            thumbs=entry.get('thumbnails') or []
            try:rows.append(self.normalise(dict(source='youtube',path=url,title=entry.get('title'),subtitle=entry.get('channel') or entry.get('uploader') or 'YouTube',thumbnail=entry.get('thumbnail') or (thumbs[-1].get('url','') if thumbs else ''))))
            except ValueError:continue
        return rows
    def search(self,source,query):
        if source not in SOURCES:raise ValueError('Unknown source')
        query=query.strip()
        saved=[x for x in self.saved() if x['source']==source]
        if not query:return self.remember(saved)
        if source=='radio' and '://' in query:rows=[self.normalise(dict(source=source,path=http_url(query),title='Radio stream'))]
        else:rows=self.radio(query) if source=='radio' else self.youtube(query)
        favourites={x['path'] for x in saved}
        rows=self.remember(rows)
        return [dict(row,subtitle=('★ · ' if row['path'] in favourites else '')+row['subtitle']) for row in rows]
    def artwork(self,item):
        url=item.get('thumbnail') or youtube_thumbnail(item.get('path',''))
        if not url:return ''
        key=hashlib.sha256(url.encode()).hexdigest();image=self.cache/(key+'.img')
        if not image.exists():
            data=get_bytes(url,5_000_000)
            if not (data.startswith((b'\x89PNG',b'\xff\xd8\xff',b'GIF8')) or data.startswith(b'RIFF') and data[8:12]==b'WEBP'):return ''
            self.cache.mkdir(parents=True,exist_ok=True)
            fd,tmp=tempfile.mkstemp(dir=self.cache)
            try:
                with os.fdopen(fd,'wb') as f:f.write(data)
                os.replace(tmp,image)
            finally:Path(tmp).unlink(missing_ok=True)
        return str(image)
    def current(self,path):
        try:
            item=json.loads(self.state.read_text())
            if item.get('path')==path:return item
        except (OSError,ValueError):pass
        with self.lock:
            item=next((item for (_,url),item in self.items.items() if url==path),{})
        if not item and youtube_thumbnail(path):item=self.normalise(dict(source='youtube',path=path))
        return item
    def play_args(self,source,url):
        row=self.item(source,url)
        if source=='youtube' and not shutil.which('yt-dlp'):raise ValueError('Install optional yt-dlp to play YouTube.')
        options=['--no-video','--vo=null','--audio-display=no','--force-window=no','--no-terminal','--shuffle=no','--loop-playlist=no','--network-timeout=15']
        if source=='youtube':options+=['--ytdl=yes','--ytdl-format=bestaudio/best']
        else:options+=['--ytdl=no']
        return row,[*options,'--',row['path']]

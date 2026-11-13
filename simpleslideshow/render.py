"""Small FFmpeg slideshow renderer. SPDX-License-Identifier: GPL-3.0-or-later"""
from dataclasses import dataclass
from pathlib import Path
import json
import math
import re
import os
import subprocess
import tempfile
import threading

FPS = 30
IMAGES = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff', '.avif'}


def folder_images(path):
    def natural(p):
        return tuple((1,int(part)) if part.isdigit() else (0,part.casefold()) for part in re.split(r'(\d+)',p.name)),p.name
    return sorted((p for p in Path(path).iterdir() if p.is_file() and p.suffix.lower() in IMAGES),key=natural)


@dataclass(frozen=True)
class Media:
    path: str
    kind: str
    duration: float = 0


def probe(path, audio=False):
    path = Path(path).expanduser().resolve(strict=True)
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                             '-of', 'json', str(path)], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError(f'Cannot read {path.name}: {result.stderr.strip()[:200]}')
    data = json.loads(result.stdout)
    stream = next((s for s in data.get('streams', []) if s.get('codec_type') == ('audio' if audio else 'video')
                   and (audio or not s.get('disposition', {}).get('attached_pic'))), None)
    if stream is None:
        raise ValueError(f'{path.name}: no {"audio" if audio else "image/video"} stream')
    if not audio and path.suffix.lower() in IMAGES:
        return Media(str(path), 'image')
    try:
        duration = float(stream.get('duration') or data.get('format', {}).get('duration') or 0)
    except (TypeError, ValueError):
        duration = 0
    if not math.isfinite(duration) or duration < .1:
        raise ValueError(f'{path.name}: cannot determine a usable duration')
    return Media(str(path), 'audio' if audio else 'video', duration)


@dataclass(frozen=True)
class Plan:
    items: tuple
    frames: tuple
    fade: int
    total: int
    music: object
    fit: bool
    music_in: float = 0
    music_out: float | None = None

    @property
    def seconds(self):
        return self.total / FPS


def audio_range(music, start=0, end=None):
    end = music.duration if end is None else end
    if not all(math.isfinite(v) for v in (start, end, music.duration)) or start < 0 or end > music.duration + .001 or end - start < .1:
        raise ValueError('Music Out must be after In (at least 0.1s), within the track.')
    return start, min(end, music.duration)


def plan(items, music=None, fit=False, photo_seconds=4, music_in=0, music_out=None):
    items = tuple(items)
    if not items:
        raise ValueError('Add at least one image or video.')
    if not math.isfinite(photo_seconds) or not 1 <= photo_seconds <= 60:
        raise ValueError('Photo time must be between 1 and 60 seconds.')
    if music:music_in,music_out=audio_range(music,music_in,music_out)
    still = round(photo_seconds * FPS)
    frames = [still if item.kind == 'image' else round(item.duration * FPS) for item in items]
    if any(item.kind not in ('image', 'video') for item in items) or min(frames) < 3:
        raise ValueError('Use images or video clips at least 0.1 seconds long.')
    fade = min(18, min(frames) // 3) if len(items) > 1 else 0
    if fit:
        if music is None:
            raise ValueError('Choose a music track to fit the slideshow to it.')
        indices = [i for i, item in enumerate(items) if item.kind == 'image']
        if not indices:
            raise ValueError('Fit music needs at least one image; video lengths stay unchanged.')
        budget = round((music_out-music_in) * FPS) + fade * (len(items)-1) - sum(frames[i] for i, item in enumerate(items) if item.kind == 'video')
        base, remainder = divmod(budget, len(indices))
        if base < max(3, 2*fade+1):
            raise ValueError('Music is too short for these clips and crossfades. Use a longer track or fewer clips.')
        for n, i in enumerate(indices):
            frames[i] = base + (n < remainder)
    total = sum(frames) - fade * (len(items)-1)
    return Plan(items, tuple(frames), fade, total, music, fit, music_in, music_out)


class Cancelled(Exception):
    pass


class Renderer:
    def __init__(self):
        self.cancelled = threading.Event()
        self.process = None
        self.lock = threading.Lock()

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()

    def run(self, args):
        if self.cancelled.is_set():
            raise Cancelled('Export cancelled.')
        with tempfile.TemporaryFile() as log:
            with self.lock:
                if self.cancelled.is_set():
                    raise Cancelled('Export cancelled.')
                self.process = subprocess.Popen(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                    '-filter_complex_threads', '1', '-filter_threads', '1', *map(str, args)],
                    stdout=subprocess.DEVNULL, stderr=log)
                process = self.process
            try:
                while True:
                    try:
                        result = process.wait(timeout=.3)
                        break
                    except subprocess.TimeoutExpired:
                        if self.cancelled.is_set():
                            process.terminate()
                            try: process.wait(timeout=2)
                            except subprocess.TimeoutExpired: process.kill(); process.wait()
                            raise Cancelled('Export cancelled.')
            finally:
                with self.lock: self.process = None
            if self.cancelled.is_set():
                raise Cancelled('Export cancelled.')
            if result:
                log.seek(0, 2); size = log.tell(); log.seek(max(0, size-3000))
                raise RuntimeError(log.read().decode(errors='replace').strip() or 'FFmpeg failed.')

    def export(self, project, destination, progress=lambda fraction, message: None, size=(1920,1080)):
        destination = Path(destination).expanduser().absolute()
        if destination.exists() or destination.is_symlink():
            raise ValueError('That output already exists. Choose a new filename.')
        if destination.suffix.lower() != '.mp4':
            raise ValueError('Choose an .mp4 output filename.')
        if not destination.parent.is_dir():
            raise ValueError('The output folder does not exist.')
        for item in (*project.items, *((project.music,) if project.music else ())):
            if not Path(item.path).is_file(): raise ValueError('Missing source: '+item.path)
        width, height = size
        if width < 2 or height < 2 or width%2 or height%2:raise ValueError('Output dimensions must be positive and even.')
        normal = f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={FPS},format=yuv420p,settb=1/{FPS},setpts=PTS-STARTPTS'
        encode = ['-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-r',str(FPS),'-threads','2','-video_track_timescale','15360']
        def input_args(item, start, frames):
            if item.kind == 'image':return ['-loop','1','-framerate',str(FPS),'-i',item.path]
            return ['-ss',f'{start/FPS:.9f}','-i',item.path]
        # Render independent bodies and transitions, keeping memory bounded to two inputs.
        with tempfile.TemporaryDirectory(prefix='simpleslideshow-') as folder:
            folder = Path(folder);segments=[];fade=project.fade;steps=len(project.items)*2
            for i, item in enumerate(project.items):
                start = fade if i else 0
                length = project.frames[i] - start - (fade if i < len(project.items)-1 else 0)
                target=folder/f'{len(segments):05}.mp4'
                progress((2*i)/steps, f'Rendering {i+1}/{len(project.items)} · {Path(item.path).name}')
                self.run([*input_args(item,start,length),'-vf',normal+',tpad=stop_mode=clone:stop_duration=1',
                    '-frames:v',length,*encode,target])
                segments.append(target)
                if i < len(project.items)-1:
                    other=project.items[i+1];target=folder/f'{len(segments):05}.mp4'
                    filters=f'[0:v]{normal},tpad=stop_mode=clone:stop_duration=1,trim=end_frame={fade},setpts=PTS-STARTPTS[a];[1:v]{normal},tpad=stop_mode=clone:stop_duration=1,trim=end_frame={fade},setpts=PTS-STARTPTS[b];[a][b]xfade=transition=fade:duration={fade/FPS:.9f}:offset=0,format=yuv420p[v]'
                    self.run([*input_args(item,project.frames[i]-fade,fade),*input_args(other,0,fade),
                        '-filter_complex',filters,'-map','[v]','-frames:v',fade,*encode,target])
                    segments.append(target)
            manifest=folder/'segments.txt'
            manifest.write_text(''.join(f"file '{p.name}'\n" for p in segments))
            result=folder/'slideshow.mp4'
            args=['-f','concat','-safe','1','-i',manifest]
            if project.music:
                music_path=project.music.path
                music_in,music_out=audio_range(project.music,project.music_in,project.music_out)
                if music_in or music_out < project.music.duration:
                    progress(.9, 'Cutting selected music range…')
                    music_path=folder/'music.wav'
                    self.run(['-i',project.music.path,'-ss',music_in,'-t',music_out-music_in,
                        '-map','0:a:0','-vn','-c:a','pcm_s16le','-ar','48000','-ac','2',music_path])
                if not project.fit:args+=['-stream_loop','-1']
                args+=['-i',music_path,'-map','0:v:0','-map','1:a:0','-c:a','aac','-b:a','192k','-ar','48000','-ac','2']
                fade_time=min(2.0,project.seconds/2)
                args+=['-af',f'apad,atrim=duration={project.seconds:.9f},afade=t=out:st={project.seconds-fade_time:.9f}:d={fade_time:.9f}']
            else:args+=['-map','0:v:0','-an']
            progress(.94, 'Finishing MP4…')
            self.run([*args,'-c:v','copy','-t',f'{project.seconds:.9f}','-movflags','+faststart',result])
            # Exclusive publication works on cloud mounts and never overwrites another export.
            if self.cancelled.is_set():raise Cancelled('Export cancelled.')
            output=destination.open('xb')
            try:
                with output, result.open('rb') as source:
                    while chunk:=source.read(1024*1024):
                        if self.cancelled.is_set():raise Cancelled('Export cancelled.')
                        output.write(chunk)
            except BaseException:
                destination.unlink(missing_ok=True)
                raise
        progress(1, 'Saved '+str(destination))
        return destination

    def export_pair(self, project, destination, progress=lambda fraction, message: None, portrait=False, sizes=None):
        base = Path(destination).expanduser().absolute()
        if base.suffix.lower() != '.mp4':raise ValueError('Choose an .mp4 filename.')
        if not base.parent.is_dir():raise ValueError('The output folder does not exist.')
        targets = (base.with_name(base.stem+'-high.mp4'), base.with_name(base.stem+'-web.mp4'))
        if any(p.exists() or p.is_symlink() for p in targets):
            raise ValueError('An export with this name already exists. Choose a new filename.')
        high_size, web_size = sizes or (((1080,1920),(720,1280)) if portrait else ((1920,1080),(1280,720)))
        created=[]
        with tempfile.TemporaryDirectory(prefix='simpleslideshow-pair-') as tmp:
            high, web = Path(tmp)/'high.mp4', Path(tmp)/'web.mp4'
            self.export(project, high, lambda fraction,message: progress(fraction*.8, 'High quality · '+message), size=high_size)
            progress(.82, 'Encoding smaller web version…')
            self.run(['-i',high,'-map','0:v:0','-map','0:a?','-vf',f'scale={web_size[0]}:{web_size[1]}',
                '-c:v','libx264','-preset','veryfast','-crf','26','-pix_fmt','yuv420p','-threads','2',
                '-c:a','aac','-b:a','128k','-movflags','+faststart',web])
            progress(.97, 'Saving both exports…')
            try:
                for source,target in zip((high,web),targets):
                    if self.cancelled.is_set():raise Cancelled('Export cancelled.')
                    output=target.open('xb');created.append(target)
                    with output, source.open('rb') as stream:
                        while chunk:=stream.read(1024*1024):
                            if self.cancelled.is_set():raise Cancelled('Export cancelled.')
                            output.write(chunk)
            except BaseException:
                for target in created:target.unlink(missing_ok=True)
                raise
        progress(1, 'Saved high-quality and web MP4s.')
        return targets

    def export_audio(self, music, destination, start=0, end=None):
        start,end=audio_range(music,start,end)
        destination=Path(destination).expanduser().absolute()
        if destination.suffix.lower()!='.mp3':raise ValueError('Choose an .mp3 output filename.')
        if destination.exists() or destination.is_symlink():raise ValueError('That output already exists. Choose a new filename.')
        if not destination.parent.is_dir():raise ValueError('The output folder does not exist.')
        with tempfile.TemporaryDirectory(prefix='simpleslideshow-audio-') as tmp:
            result=Path(tmp)/'cut.mp3'
            self.run(['-i',music.path,'-ss',start,'-t',end-start,'-map','0:a:0','-vn',
                '-c:a','libmp3lame','-q:a','2',result])
            if self.cancelled.is_set():raise Cancelled('Export cancelled.')
            output=destination.open('xb')
            try:
                with output,result.open('rb') as source:
                    while chunk:=source.read(1024*1024):
                        if self.cancelled.is_set():raise Cancelled('Export cancelled.')
                        output.write(chunk)
            except BaseException:
                destination.unlink(missing_ok=True)
                raise
        return destination

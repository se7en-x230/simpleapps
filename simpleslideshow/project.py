"""Explicit, portable edit projects. SPDX-License-Identifier: GPL-3.0-or-later"""
from pathlib import Path
from dataclasses import asdict
import json,os,tempfile
from render import Media,refresh_media,plan


def read_project(filename):
    path=Path(filename).expanduser().resolve(strict=True)
    data=json.loads(path.read_text())
    if data.get('format')!='simpleslideshow.project' or data.get('version')!=1:raise ValueError('Not a supported Simpleslideshow project.')
    def media(value):
        value=dict(value);source=Path(value['path']).expanduser()
        value['path']=str(source if source.is_absolute() else path.parent/source)
        return refresh_media(Media(**value))
    items=[media(item) for item in data['items']]
    music=media(data['music']) if data.get('music') else None
    seconds=float(data.get('photo_seconds',4));fit=bool(data.get('fit',False));start=float(data.get('music_in',0));end=data.get('music_out')
    subtitles=data.get('subtitles')
    if subtitles:
        sub=Path(subtitles);sub=sub if sub.is_absolute() else path.parent/sub
        subtitles=str(sub.resolve(strict=True))
    if items:plan(items,music,fit,seconds,start,end)
    return dict(items=items,music=music,photo_seconds=seconds,fit=fit,music_in=start,music_out=end,portrait=bool(data.get('portrait',False)),subtitles=subtitles,subtitles_enabled=bool(data.get('subtitles_enabled',True)))


def write_project(filename,items,music,photo_seconds=4,fit=False,music_in=0,music_out=None,portrait=False,subtitles=None,subtitles_enabled=True):
    path=Path(filename).expanduser().absolute()
    def media(item):
        value=asdict(item)
        try:value['path']=str(Path(item.path).resolve().relative_to(path.parent.resolve()))
        except ValueError:value['path']=str(Path(item.path).resolve())
        return value
    data=dict(format='simpleslideshow.project',version=1,items=[media(i) for i in items],music=media(music) if music else None,
              photo_seconds=photo_seconds,fit=fit,music_in=music_in,music_out=music_out,portrait=portrait)
    if subtitles:
        sub=Path(subtitles).resolve()
        try:sub=sub.relative_to(path.parent.resolve())
        except ValueError:pass
        data.update(subtitles=str(sub),subtitles_enabled=subtitles_enabled)
    temp=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix='.'+path.name,delete=False) as f:
            temp=Path(f.name);json.dump(data,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
        temp.replace(path)
    finally:
        if temp and temp.exists():temp.unlink()
    return path

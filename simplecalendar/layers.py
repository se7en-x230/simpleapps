"""Read the same local date layers used by the native dashboards."""
from pathlib import Path
from datetime import date,datetime,timedelta
import configparser,os
import core

def events(start,end):
    cfg=configparser.ConfigParser(interpolation=None,delimiters=('=',));cfg.optionxform=str
    cfg.read(Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'simple/calendar.ini')
    rows=[]
    def add(day,title,kind):
        if start<=day<end:rows.append(dict(day=day,title=title,layer=kind))
    def enabled(key):return cfg.getboolean('display',key,fallback=True)
    for group,kind,on in [('extra','Local dates',True),('buddhist','Thai Buddhist',enabled('buddhist'))]:
        if on and cfg.has_section(group):
            for key,title in cfg.items(group):
                try:add(date.fromisoformat(key),title,kind)
                except ValueError:continue
    if enabled('full_moon') and cfg.has_section('full-moons'):
        for key,_ in cfg.items('full-moons'):
            try:
                at=datetime.fromisoformat(key).astimezone(core.zone());add(at.date(),'● Full moon · '+at.strftime('%H:%M'),'Full moon')
            except ValueError:continue
    if enabled('western'):
        for year in range(start.year,end.year+1):
            for key,title in cfg.items('western-fixed') if cfg.has_section('western-fixed') else []:
                try:add(date.fromisoformat(str(year)+'-'+key),title,'Local holidays')
                except ValueError:continue
            a=year%19;b=year//100;c=year%100;d=b//4;e=b%4;f=(b+8)//25;g=(b-f+1)//3
            h=(19*a+b-d-g+15)%30;i=c//4;k=c%4;l=(32+2*e+2*i-h-k)%7;m=(a+11*h+22*l)//451;n=h+l-7*m+114
            easter=date(year,n//31,n%31+1)
            for key,title in cfg.items('western-easter') if cfg.has_section('western-easter') else []:
                try:add(easter+timedelta(days=int(key)),title,'Local holidays')
                except ValueError:continue
    return sorted(rows,key=lambda e:(e['day'],e['title']))

from pathlib import Path
import os,configparser,gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk
ROOT=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'));APP=ROOT/'simplecontacts'
DEFAULTS={'navigation':{'up':'k,Up','down':'j,Down','left':'h,Left','right':'l,Right','activate':'Return','cancel':'Escape'},'contacts':{'new':'n','edit':'e','delete':'x','search':'slash','sync':'s','accounts':'c','export':'b','quit':'q'}}
class Preferences:
 def __init__(self):
  self.keys={k:dict(v) for k,v in DEFAULTS.items()}
  for path in (ROOT/'simple/keys.ini',APP/'keys.ini'):
   c=configparser.ConfigParser(interpolation=None);c.read(path)
   for section,actions in self.keys.items():
    for action in actions:
     if c.has_option(section,action):
      value=c.get(section,action)
      if all(Gtk.accelerator_parse(x.strip())[0] for x in value.split(',') if x.strip()):actions[action]=value
  self.config=configparser.ConfigParser(interpolation=None);self.config.read(APP/'config.ini')
 def number(self,name,default,low,high):
  try:return max(low,min(high,self.config.getint('contacts',name,fallback=default)))
  except ValueError:return default
 def matches(self,section,name,key,state):
  for item in self.keys[section][name].split(','):
   ok,value,mods=Gtk.accelerator_parse(item.strip()) if item.strip() else (False,0,0)
   if ok and value==key and state&Gtk.accelerator_get_default_mod_mask()==mods:return True
  return False

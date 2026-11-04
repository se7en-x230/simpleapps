"""Global Simple navigation with optional calendar overrides."""
import os,configparser
from pathlib import Path
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk
ROOT=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))
APP=ROOT/'simplecalendar'
DEFAULTS={'navigation':{'left':'Left,h,<Control>h','right':'Right,l,<Control>l','up':'Up,k,<Control>k','down':'Down,j,<Control>j','activate':'Return,KP_Enter','cancel':'Escape','page_up':'Page_Up','page_down':'Page_Down'},
'calendar':{'previous_month':'H','next_month':'L','next_event':'J','previous_event':'K','edit':'e','new':'n','today':'t,g,Home','agenda':'a','sync':'s','help':'question','quit':'q','save':'<Control>s','delete':'x','accounts':'c','day_left':'h','day_right':'l','day_up':'k','day_down':'j'}}
class Preferences:
 def __init__(self):
  self.keys={section:dict(values) for section,values in DEFAULTS.items()}
  for path in (ROOT/'simple/keys.ini',APP/'keys.ini'):
   cfg=configparser.ConfigParser(interpolation=None)
   try:cfg.read(path)
   except configparser.Error:continue
   for section,actions in self.keys.items():
    for action in actions:
     if cfg.has_option(section,action):
      raw=cfg.get(section,action)
      if all(Gtk.accelerator_parse(k.strip())[0] for k in raw.split(',') if k.strip()):actions[action]=raw
  self.config=configparser.ConfigParser(interpolation=None)
  try:self.config.read(APP/'config.ini')
  except configparser.Error:self.config=configparser.ConfigParser()
 def number(self,key,default,low,high):
  try:return max(low,min(high,self.config.getint('calendar',key,fallback=default)))
  except ValueError:return default
 def matches(self,section,action,key,state):
  mask=Gtk.accelerator_get_default_mod_mask()
  for name in self.keys[section][action].split(','):
   if not name.strip():continue
   valid,value,mods=Gtk.accelerator_parse(name.strip())
   # GTK names uppercase letters without an explicit Shift modifier.
   symbol=name.strip().rsplit('>',1)[-1]
   if len(symbol)==1 and symbol.isupper():mods|=Gdk.ModifierType.SHIFT_MASK
   actual=state&mask
   if Gdk.keyval_to_lower(key)!=key:actual|=Gdk.ModifierType.SHIFT_MASK
   if valid and Gdk.keyval_to_lower(value)==Gdk.keyval_to_lower(key) and mods==actual:return True
  return False
 def legend(self):
  return '  ·  '.join(f'{self.keys[s][a] or "disabled"}: {title}' for s,a,title in [('calendar','day_left','previous day'),('calendar','day_down','week down'),('calendar','new','new'),('calendar','delete','delete'),('calendar','today','today'),('calendar','sync','sync'),('calendar','accounts','accounts'),('calendar','help','keys')])

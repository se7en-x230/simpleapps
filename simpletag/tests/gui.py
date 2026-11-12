import os,sys,tempfile,shutil,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'simpletag'),str(root/'simple-common')]
from gi.repository import GLib
with tempfile.TemporaryDirectory() as d:
 os.environ['XDG_CONFIG_HOME']=d
 cfg=Path(d)/'simpletag';cfg.mkdir();shutil.copy2(root/'simpletag/keys.ini',cfg/'keys.ini')
 from main import App,Gdk,Gtk
 fields={'artist':'Example','album':'Album','title':'Song','tracknumber':'1','date':'2026'}
 class Fake:
  def request(self,action,**kw):
   assert action=='status'
   return {'protocol':1,'busy':False,'message':'Ready','groups':[{'id':'a','title':'Example album','artist':'Example artist','kind':'matched','saveable':1,'files':[{'path':'/demo/song.flac','state':'changed','before':fields,'after':dict(fields,title='New title'),'saveable':True}]}]}
 app=App(client=Fake(),autostart=False);app.set_application_id('org.simpleapps.SimpletagTest');passed=[]
 def key(name,ctrl=False):
  handled=False
  controllers=app.win.observe_controllers()
  for i in range(controllers.get_n_items()):
   c=controllers.get_item(i)
   if isinstance(c,Gtk.EventControllerKey):
    handled=c.emit('key-pressed',Gdk.keyval_from_name(name),0,Gdk.ModifierType.CONTROL_MASK if ctrl else Gdk.ModifierType(0))
    if handled:break
  return handled
 def check():
  try:
   assert app.connected and app.group()['id']=='a'
   assert app.detail_card.has_css_class('card')
   assert not app.search.get_visible()
   assert app.buttons['save'].get_sensitive() and not app.buttons['scan'].get_sensitive()
   assert 'Song → New title' in app.review.get_text()
   original = app.snapshot
   group = app.group()
   app.snapshot = dict(original, groups=[dict(group, id=str(i), title=f'Album {i}') for i in range(25)])
   app.fill();app.list.get_selected_row().grab_focus()
   for i in range(35):
    assert key('j',True)
    assert app.list.get_selected_row().get_index()==min(i+1,24)
    assert app.win.get_focus()==app.list.get_selected_row()
   for i in range(35):
    assert key('k',True)
    assert app.list.get_selected_row().get_index()==max(23-i,0)
    assert app.win.get_focus()==app.list.get_selected_row()
   assert key('slash')
   for i in range(35):
    assert key('j',True)
    focus=app.win.get_focus()
    assert focus==app.search or focus.is_ancestor(app.search)
   assert app.list.get_selected_row().get_index()==24
   assert key('Escape')
   app.snapshot=original;app.fill()
   assert key('slash');assert app.search.get_visible()
   assert key('Escape');assert not app.search.get_visible() and app.win.get_visible()
   app.review.grab_focus();assert key('j',True)
   perform=app.perform;actions=[];app.perform=actions.append
   for letter,action in [('o','load'),('l','lookup'),('a','scan'),('s','save'),('r','remove'),('p','picard')]:
    assert key(letter);assert actions[-1]==action
   assert key('slash');actions.clear()
   for letter in 'olasrp':
    assert not key(letter)
   assert not actions
   assert key('s',True);assert actions==['save']
   assert key('Escape');app.perform=perform
   calls=[];app.request=lambda *a,**kw:calls.append((a,kw))
   key('s',True);assert calls==[(('save',),{'group':'a'})],calls
   key('r',True);assert calls[-1]==(('remove',),{'group':'a'}),calls
   app.snapshot['busy']=True
   assert app.close() is True and app.closing_requested
   assert calls[-1][0]==('status',)
   assert not any(c[0]==('clear',) for c in calls)
   app.received('status',Fake().request('status'),None,None)
   assert calls[-1][0]==('clear',)
   assert app.win.get_visible()
   app.cleared_for_close();assert app.closed
   passed.append(True)
  finally:app.quit()
  return False
 GLib.timeout_add(700,check);app.run([]);assert passed
print('PASS shared search/Esc, repeated list boundaries and typing focus, action override keys, review and save selection')

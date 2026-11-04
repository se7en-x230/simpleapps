from pathlib import Path
from urllib.parse import quote
from datetime import datetime
import sys,threading,subprocess,gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,GLib,Gio,Pango
import core,auth,preferences
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'simple-common'))
from theme_loader import load_css

def box(vertical=True,spacing=8):return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,spacing=spacing)
def label(text,css=None):
 w=Gtk.Label(label=text,xalign=0,wrap=True);w.set_selectable(css not in ('heading','section','muted'))
 if css:w.add_css_class(css)
 return w
def button(text,fn):
 b=Gtk.Button(label=text);b.connect('clicked',lambda _:fn());return b
def children(w):
 c=w.get_first_child()
 while c:
  n=c.get_next_sibling();yield c;c=n

def margins(w,n=12):
 for side in ('top','bottom','start','end'):getattr(w,'set_margin_'+side)(n)

class App(Gtk.Application):
 def __init__(self):
  super().__init__(application_id='space.go7.SimpleContacts')
  self.connect('activate',self.activate);self.win=None;self.busy=False;self.editor=None;self.current=None;self.rows=[];self.prefs=preferences.Preferences()
 def activate(self,*_):
  if self.win:self.win.present();return
  self.win=Gtk.ApplicationWindow(application=self,title='SimpleContacts');self.win.add_css_class('simple-contacts-app')
  self.win.set_default_size(self.prefs.number('width',850,650,1600),self.prefs.number('height',560,420,1000))
  for path,priority,loader in [(preferences.ROOT/'simple/aliases.css',801,False),(Path(__file__).with_name('style.css'),802,False),(preferences.APP/'style.css',803,True)]:
   provider=Gtk.CssProvider()
   if path.exists():
    if loader:load_css(provider,path)
    else:provider.load_from_path(str(path))
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,priority)
  outer=box();margins(outer);self.win.set_child(outer)
  header=box(False);outer.append(header);name=label('SimpleContacts','heading');name.set_hexpand(True);header.append(name)
  for text,fn in [('Sync',lambda:self.work(core.sync)),('Accounts',self.accounts),('Export',self.export),('+ Contact',self.edit)]:header.append(button(text,fn))
  self.status=label('','muted');outer.append(self.status)
  body=box(False,14);body.set_vexpand(True);outer.append(body)
  left=box();left.set_size_request(270,-1);body.append(left)
  self.search=Gtk.SearchEntry(placeholder_text='Search name, phone or email · /');left.append(self.search);self.search.connect('search-changed',lambda _:self.refresh())
  self.list=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE);self.list.add_css_class('contact-list');self.selection_handler=self.list.connect('row-selected',self.selected)
  self.list_scroll=Gtk.ScrolledWindow(vexpand=True);self.list_scroll.add_css_class('contact-list-frame');self.list_scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);self.list_scroll.set_child(self.list);left.append(self.list_scroll)
  self.detail=box();self.detail.set_hexpand(True);scroll=Gtk.ScrolledWindow(hexpand=True,vexpand=True);scroll.set_child(self.detail);body.append(scroll)
  outer.append(label('j/k contacts · h/l focus · / search · n new · e edit · x delete · s sync · c accounts · b export','muted'))
  keys=Gtk.EventControllerKey();keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE);keys.connect('key-pressed',self.keys);self.win.add_controller(keys)
  self.refresh();self.win.present()
  if self.rows:self.rows[0].grab_focus()
  else:self.search.grab_focus()
  if (core.ROOT/'google-token.json').exists():self.work(core.sync)
  GLib.timeout_add_seconds(self.prefs.number('sync_seconds',1800,300,86400),self.tick)
 def tick(self):
  if not self.win.get_visible():return False
  if not self.busy and (core.ROOT/'google-token.json').exists():self.work(core.sync)
  return True
 def keys(self,controller,key,code,state):
  focus=self.win.get_focus();node=focus
  while node:
   if isinstance(node,(Gtk.Editable,Gtk.TextView)):
    if key==Gdk.KEY_Escape:self.list.grab_focus();return True
    return False
   node=node.get_parent()
  match=lambda section,name:self.prefs.matches(section,name,key,state)
  if match('navigation','down') or match('navigation','up'):
   row=self.list.get_selected_row();i=row.get_index() if row else -1;i=max(0,min(len(self.rows)-1,i+(1 if match('navigation','down') else -1)))
   if self.rows:
    self.list.select_row(self.rows[i]);self.rows[i].grab_focus()
    GLib.idle_add(self.redraw_list)
   return True
  for name,direction in [('left',Gtk.DirectionType.LEFT),('right',Gtk.DirectionType.RIGHT)]:
   if match('navigation',name):self.win.child_focus(direction);return True
  actions={'new':self.edit,'edit':lambda:self.edit(self.current) if self.current else None,'delete':self.delete,'search':self.search.grab_focus,'sync':lambda:self.work(core.sync),'accounts':self.accounts,'export':self.export,'quit':self.win.close}
  for name,fn in actions.items():
   if match('contacts',name):fn();return True
  if match('navigation','cancel'):self.win.close();return True
  return False
 def redraw_list(self):
  # Redraw after detail-pane allocation and Gtk's automatic focus scrolling.
  self.list.queue_draw();self.list_scroll.queue_draw()
  return False
 def refresh(self):
  data=core.cache();query=self.search.get_text().casefold().strip();rid=self.current.get('resourceName') if self.current else None
  people=sorted(data['people'],key=lambda p:core.title(p).casefold())
  people=[p for p in people if query in (' '.join([core.title(p),*core.values(p,'emailAddresses'),*core.values(p,'phoneNumbers')])).casefold()]
  when=datetime.fromisoformat(data['synced']).astimezone().strftime('%d %b %H:%M') if data.get('synced') else 'not synced yet'
  self.status.set_text(f'{len(data["people"])} contacts · Local copy · {when}' if (core.ROOT/'google-token.json').exists() else 'Connect Google Contacts to download your local copy.')
  if people==getattr(self,'displayed_people',None):return
  self.displayed_people=people
  focus=self.win.get_focus()
  had_focus=bool(focus and (focus==self.list or focus.is_ancestor(self.list)))
  self.list.handler_block(self.selection_handler)
  try:
   for w in children(self.list):self.list.remove(w)
   self.rows=[];selected=None
   for p in people:
    row=Gtk.ListBoxRow();row.person=p;content=box(spacing=3);margins(content,8)
    name=label(core.title(p));name.set_selectable(False);name.set_wrap(False);name.set_ellipsize(Pango.EllipsizeMode.END);name.set_max_width_chars(30);content.append(name)
    extra=(core.values(p,'emailAddresses') or core.values(p,'phoneNumbers') or [''])[0]
    if extra:
     subtitle=label(extra,'muted');subtitle.set_wrap(False);subtitle.set_ellipsize(Pango.EllipsizeMode.END);subtitle.set_max_width_chars(30);content.append(subtitle)
    row.set_child(content);self.list.append(row);self.rows.append(row)
    if p.get('resourceName')==rid:selected=row
   selected=selected or (self.rows[0] if self.rows else None)
   self.list.select_row(selected)
  finally:self.list.handler_unblock(self.selection_handler)
  self.selected(self.list,selected)
  if had_focus:
   (selected or self.search).grab_focus()
  self.list.queue_resize();self.list.queue_draw()
 def selected(self,_,row):
  self.current=row.person if row else None
  for w in children(self.detail):self.detail.remove(w)
  if not row:self.detail.append(label('No contacts match your search.' if self.search.get_text() else 'Your contacts, kept locally and synced with Google.','muted'));return
  p=row.person;self.detail.append(label(core.title(p),'heading'))
  actions=box(False);actions.append(button('Edit · e',lambda:self.edit(p)));actions.append(button('Delete · x',self.delete));self.detail.append(actions)
  for field,title in [('emailAddresses','Email'),('phoneNumbers','Phone'),('addresses','Address'),('organizations','Organization'),('birthdays','Birthday'),('biographies','Notes'),('urls','Website')]:
   items=p.get(field,[])
   if not items:continue
   self.detail.append(label(title,'section'))
   for item in items:
    if field=='addresses':text=item.get('formattedValue') or ', '.join(item.get(k,'') for k in ('streetAddress','city','region','postalCode','country') if item.get(k))
    elif field=='organizations':text=' · '.join(item.get(k,'') for k in ('name','title') if item.get(k))
    elif field=='birthdays':text=item.get('text') or '-'.join(str(item.get('date',{}).get(k,'?')) for k in ('year','month','day'))
    else:text=item.get('value','')
    rowbox=box(False);rowbox.set_hexpand(True);textlabel=label(text);textlabel.set_hexpand(True);rowbox.append(textlabel)
    if field in ('emailAddresses','phoneNumbers'):
     rowbox.append(button('Copy',lambda text=text:Gdk.Display.get_default().get_clipboard().set(text)))
    if field=='emailAddresses':rowbox.append(button('Write',lambda text=text:subprocess.Popen(['simple-open','mail','mailto:'+quote(text,safe='@') ])))
    self.detail.append(rowbox)
 def work(self,fn,after=None,error_label=None):
  if self.busy:return
  self.busy=True;self.hold();self.status.set_text('Working…')
  def worker():
   try:value=fn();error=None
   except Exception as exc:value=None;error=str(exc)
   def finish():
    self.busy=False;self.refresh()
    if error:
     self.status.set_text(error)
     if error_label:error_label.set_text(error)
    elif after:after(value)
    self.release();return False
   GLib.idle_add(finish)
  threading.Thread(target=worker,daemon=True).start()
 def dialog(self,title):
  w=Gtk.Window(title=title,transient_for=self.win,modal=True,default_width=470);w.add_css_class('simple-contacts-app')
  content=box();margins(content);scroll=Gtk.ScrolledWindow(propagate_natural_height=True,max_content_height=650);scroll.set_child(content);w.set_child(scroll)
  keys=Gtk.EventControllerKey();keys.connect('key-pressed',lambda c,k,code,s:(w.close() or True) if k==Gdk.KEY_Escape else False);w.add_controller(keys)
  return w,content
 def edit(self,p=None):
  if self.busy:return
  if self.editor:self.editor.present();return
  if not (core.ROOT/'google-token.json').exists():self.accounts();return
  if p and not core.sources(p):self.status.set_text('This contact is read-only.');return
  w,form=self.dialog('Edit contact' if p else 'New contact');self.editor=w;w.connect('close-request',lambda *_:setattr(self,'editor',None) or False)
  original=core.editable_values(p or {});entries={}
  for key,title in [('given','Given name'),('family','Family name'),('emails','Email addresses · one per line'),('phones','Phone numbers · one per line'),('notes','Notes')]:
   form.append(label(title,'muted'))
   if key in ('emails','phones','notes'):
    v=Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR);v.get_buffer().set_text(original[key]);v.set_size_request(-1,64);entries[key]=v
   else:v=Gtk.Entry(text=original[key]);entries[key]=v
   form.append(v)
  form.append(label('Other contact fields stay unchanged. Save requires an internet connection.','muted'))
  error=label('');form.append(error)
  def values():
   result={}
   for k,v in entries.items():
    if isinstance(v,Gtk.TextView):b=v.get_buffer();result[k]=b.get_text(b.get_start_iter(),b.get_end_iter(),False)
    else:result[k]=v.get_text()
   return result
  def save():
   if self.busy:return
   fields=values()
   self.work(lambda:core.save(fields,p),lambda person:(setattr(self,'current',person),w.close(),self.refresh()),error)
  save_button=button('Save to Google',save);save_button.add_css_class('primary');form.append(save_button)
  def dirty(*_):save_button.set_sensitive(values()!=original)
  for v in entries.values():(v.get_buffer() if isinstance(v,Gtk.TextView) else v).connect('changed',dirty)
  dirty();form.append(button('Cancel',w.close));w.present()
 def delete(self):
  if self.busy or not self.current:return
  p=self.current;w,body=self.dialog('Delete contact?');body.append(label('Delete “'+core.title(p)+'” from Google Contacts? This also removes it from your synced devices.'))
  error=label('');body.append(error);cancel=button('Cancel',w.close);body.append(cancel)
  body.append(button('Delete from Google',lambda:self.work(lambda:core.remove(p),lambda _:w.close(),error)));w.present();cancel.grab_focus()
 def accounts(self):
  w,body=self.dialog('Google Contacts');body.append(label('Google Contacts','heading'))
  body.append(label('Connected on this device.' if (core.ROOT/'google-token.json').exists() else 'Not connected yet.'))
  body.append(label('Enable People API in your Calendar Google Cloud project. The existing Desktop OAuth client can be reused; approve Contacts access once on each computer.'))
  body.append(Gtk.LinkButton(uri='https://console.cloud.google.com/apis/library/people.googleapis.com',label='Enable Google People API'))
  error=label('');body.append(error)
  body.append(button('Reconnect Google' if (core.ROOT/'google-token.json').exists() else 'Connect Google',lambda:self.work(auth.connect,lambda _:w.close(),error)))
  body.append(button('Close',w.close));w.present()
 def export(self):
  w,body=self.dialog('Export local contacts');body.append(label('Export names, phone numbers, emails, addresses, organizations, websites and notes as a vCard file.'))
  entry=Gtk.Entry(text=str(Path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD) or str(Path.home()))/('contacts-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.vcf')));body.append(entry);error=label('');body.append(error)
  def save():
   path=Path(entry.get_text()).expanduser()
   if path.exists():error.set_text('Choose a new filename; this file already exists.');return
   self.work(lambda:core.export_vcard(path),lambda n:(w.close(),self.status.set_text(f'Exported {n} contacts to {path}')),error)
  body.append(button('Export',save));body.append(button('Cancel',w.close));w.present()

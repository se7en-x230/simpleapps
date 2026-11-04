"""Google People contacts with a private local snapshot; mutations require online access."""
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime,timezone
import os,json,tempfile,fcntl,time,copy,re
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import AuthorizedSession,Request

ROOT=Path(os.environ.get('SIMPLE_CONTACTS_HOME',str(Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'simplecontacts')))
SCOPE='https://www.googleapis.com/auth/contacts'
FIELDS='names,emailAddresses,phoneNumbers,addresses,organizations,birthdays,biographies,urls,memberships,metadata'
class ContactError(RuntimeError):pass

def init():
 ROOT.mkdir(parents=True,exist_ok=True,mode=0o700);ROOT.chmod(0o700)
def write(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.contacts-')
 try:
  with os.fdopen(fd,'w') as f:f.write(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False))
  os.replace(tmp,path)
 finally:Path(tmp).unlink(missing_ok=True)
def read(name,default):
 try:return json.loads((ROOT/name).read_text())
 except FileNotFoundError:return default
@contextmanager
def locked():
 init()
 with (ROOT/'operations.lock').open('a') as f:
  fcntl.flock(f,fcntl.LOCK_EX);yield

def cache():return read('contacts.json',{'people':[],'overrides':{},'synced':None})
def title(p):
 n=next(iter(p.get('names',[])),{})
 return n.get('displayName') or ' '.join(x for x in (n.get('givenName'),n.get('familyName')) if x) or next(iter(p.get('emailAddresses',[])),{}).get('value') or next(iter(p.get('phoneNumbers',[])),{}).get('value') or 'Unnamed contact'
def values(p,key):return [v.get('value','') for v in p.get(key,[]) if v.get('value')]
def sources(p):return [copy.deepcopy(s) for s in p.get('metadata',{}).get('sources',[]) if s.get('type')=='CONTACT']
def revision(p):return sorted((s.get('id',''),s.get('etag','')) for s in sources(p))
def resource(p):
 r=p.get('resourceName','')
 if not re.fullmatch(r'people/[A-Za-z0-9_-]+',r):raise ContactError('Invalid contact identifier')
 return r

def snapshot(data):
 if not data.get('people'):return
 folder=ROOT/'history';folder.mkdir(exist_ok=True,mode=0o700)
 write(folder/(str(time.time_ns())+'.json'),data)
 for f in sorted(folder.glob('*.json'))[:-10]:f.unlink()

def api():
 if not (ROOT/'google-token.json').exists():raise ContactError('Connect Google Contacts first.')
 c=Credentials.from_authorized_user_file(str(ROOT/'google-token.json'),scopes=[SCOPE])
 if not c.valid:
  try:c.refresh(Request())
  except Exception:raise ContactError('Google sign-in needs attention. Reconnect from Accounts.') from None
  write(ROOT/'google-token.json',c.to_json())
 return AuthorizedSession(c)

def request(session,method,path,**kwargs):
 try:r=session.request(method,'https://people.googleapis.com/v1/'+path,timeout=35,**kwargs)
 except Exception:
  if method!='GET':raise ContactError('Connection interrupted. Google may have received the change; sync and check before trying again.') from None
  raise ContactError('Could not reach Google. Your local contacts are still available.') from None
 if not r.ok:
  if r.status_code==403:raise ContactError('Google denied access. Enable People API in your Cloud project and approve Contacts permission.')
  if r.status_code in (409,412):raise ContactError('Contact changed on Google. Sync and reopen it before editing.')
  if r.status_code==401:raise ContactError('Google sign-in expired. Reconnect from Accounts.')
  if r.status_code==429:raise ContactError('Google request limit reached. Try syncing later.')
  if r.status_code==400:raise ContactError('Google rejected the change or the contact is out of date. Sync and reopen it.')
  raise ContactError(f'Google returned error {r.status_code}. Local contacts were kept.')
 return r.json() if r.content else {}

def sync(session=None):
 with locked():
  session=session or api();old=cache();people={};params={'personFields':FIELDS,'pageSize':1000,'sources':'READ_SOURCE_TYPE_CONTACT'}
  while True:
   result=request(session,'GET','people/me/connections',params=dict(params))
   for person in result.get('connections',[]):
    if not person.get('metadata',{}).get('deleted'):people[resource(person)]=person
   token=result.get('nextPageToken')
   if not token:break
   params['pageToken']=token
  # The list endpoint can lag a successful mutation. Keep its returned data briefly.
  overrides={}
  for rid,o in old.get('overrides',{}).items():
   if time.time()-o['at']<600:
    overrides[rid]=o
    if o['person'] is None:people.pop(rid,None)
    else:people[rid]=o['person']
  snapshot(old)
  new={'people':sorted(people.values(),key=lambda p:title(p).casefold()),'overrides':overrides,'synced':datetime.now(timezone.utc).isoformat()}
  write(ROOT/'contacts.json',new);write(ROOT/'status.json',{'ok':True});return new

def editable_values(p):
 n=next(iter(p.get('names',[])),{})
 return {'given':n.get('givenName',''),'family':n.get('familyName',''),'emails':'\n'.join(values(p,'emailAddresses')),'phones':'\n'.join(values(p,'phoneNumbers')),'notes':next(iter(p.get('biographies',[])),{}).get('value','')}

def changes(original,form):
 old=editable_values(original);body={};fields=[]
 if form['given'].strip()!=old['given'] or form['family'].strip()!=old['family']:
  n={k:v for k,v in next(iter(original.get('names',[])),{}).items() if k not in ('metadata','displayName','displayNameLastFirst','unstructuredName')}
  n.update(givenName=form['given'].strip(),familyName=form['family'].strip());body['names']=[n];fields.append('names')
 for key,label in [('emailAddresses','emails'),('phoneNumbers','phones')]:
  new=[v.strip() for v in form[label].splitlines() if v.strip()]
  if new!=values(original,key):
   prior={x.get('value'):x for x in original.get(key,[])}
   body[key]=[{k:v for k,v in prior.get(value,{'value':value}).items() if k not in ('metadata','formattedType','canonicalForm')} for value in new];fields.append(key)
 if form['notes']!=old['notes']:
  body['biographies']=[{'value':form['notes'],'contentType':'TEXT_PLAIN'}] if form['notes'] else [];fields.append('biographies')
 if not any(form[k].strip() for k in ('given','family','emails','phones')):raise ContactError('Enter a name, email address or phone number.')
 return body,fields

def save(form,original=None,session=None):
 with locked():
  session=session or api();original=original or {};body,fields=changes(original,form)
  if not fields:return original
  old=cache()
  if original:
   if not sources(original):raise ContactError('This contact is read-only.')
   rid=resource(original)
   live=request(session,'GET',rid,params={'personFields':FIELDS})
   if revision(live)!=revision(original):raise ContactError('This contact changed on Google. Sync and reopen it before saving.')
   body['metadata']={'sources':sources(original)}
   person=request(session,'PATCH',rid+':updateContact',params={'updatePersonFields':','.join(fields),'personFields':FIELDS},json=body)
  else:person=request(session,'POST','people:createContact',params={'personFields':FIELDS},json=body)
  rid=resource(person);snapshot(old)
  old['people']=[p for p in old['people'] if p.get('resourceName')!=rid]+[person]
  old.setdefault('overrides',{})[rid]={'person':person,'at':time.time()};write(ROOT/'contacts.json',old)
  return person

def remove(person,session=None):
 with locked():
  if not sources(person):raise ContactError('This contact is read-only.')
  session=session or api();rid=resource(person)
  live=request(session,'GET',rid,params={'personFields':FIELDS})
  if revision(live)!=revision(person):raise ContactError('This contact changed on Google. Sync and review it before deleting.')
  old=cache();snapshot(old)
  request(session,'DELETE',rid+':deleteContact')
  old['people']=[p for p in old['people'] if p.get('resourceName')!=rid]
  old.setdefault('overrides',{})[rid]={'person':None,'at':time.time()};write(ROOT/'contacts.json',old)

def export_vcard(path):
 def esc(s):return str(s).replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')
 lines=[]
 for p in cache()['people']:
  n=next(iter(p.get('names',[])),{})
  lines+=['BEGIN:VCARD','VERSION:3.0','FN:'+esc(title(p)),'N:'+esc(n.get('familyName',''))+';'+esc(n.get('givenName',''))+';;;']
  for key,tag in [('emailAddresses','EMAIL'),('phoneNumbers','TEL')]:lines += [tag+':'+esc(v) for v in values(p,key)]
  for v in p.get('addresses',[]):
   lines.append('ADR:;;'+ ';'.join(esc(v.get(k,'')) for k in ('streetAddress','city','region','postalCode','country')))
  for v in p.get('organizations',[]):lines.append('ORG:'+esc(v.get('name','')))
  for v in p.get('urls',[]):lines.append('URL:'+esc(v.get('value','')))
  for v in p.get('biographies',[]):lines.append('NOTE:'+esc(v.get('value','')))
  lines.append('END:VCARD')
 folded=[]
 for line in lines:
  part=''
  for ch in line:
   if len((part+ch).encode())>75:folded.append(part);part=' '
   part+=ch
  folded.append(part)
 write(Path(path),'\r\n'.join(folded)+'\r\n');return len(cache()['people'])

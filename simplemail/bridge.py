"""JSON boundary for the native frontend. Mail protocols stay in simplemail.py."""
import sys,json,io,contextlib,os,uuid,hashlib
from pathlib import Path
import simplemail as m

def config():
 raw,data=m.setup_config()
 return raw,m.account_settings(data) if m.setup_accounts(data) else {'accounts':[]}

def cache_path(folder):
 if folder not in ('inbox','sent','trash'):raise ValueError('Unknown folder')
 return Path(os.environ.get('XDG_CACHE_HOME',str(Path.home()/'.cache')))/'simplemail'/('native-'+folder+'.json')

def normal(value):
 if isinstance(value,bytes):return value.decode('ascii',errors='replace')
 if isinstance(value,dict):return {k:normal(v) for k,v in value.items()}
 if isinstance(value,(list,tuple)):return [normal(v) for v in value]
 return value

def identity(e):return [e.get(k,'') for k in ('account','folder','validity','uid')]

def cached(folder,cfg):
 try:
  data=json.loads(cache_path(folder).read_text());users={a['username'] for a in m.configured_accounts(cfg)}
  data['messages']=[e for e in data['messages'] if e.get('account') in users]
  return data
 except (OSError,ValueError,KeyError):return {'messages':[],'total':0,'errors':[]}

def save_cache(folder,value):
 p=cache_path(folder);p.parent.mkdir(parents=True,exist_ok=True,mode=0o700);m.save(p,normal(value))

def serialize_message(message):
 value=dict(message);value['images']=[{'name':i.get('name','Image'),'remote':bool(i.get('url'))} for i in message.get('images',[])];return value

def account(cfg,user):return m.message_account(cfg,{'account':user})

def invalidate(items,cfg,remove=False):
 for folder in ('inbox','sent','trash'):
  data=cached(folder,cfg);ids=[identity(e) for e in items]
  if remove:data['messages']=[e for e in data['messages'] if identity(e) not in ids]
  else:
   for e in data['messages']:
    if identity(e) in ids:e['unread']=False
  save_cache(folder,data)

def handle(r):
 raw,cfg=config();op=r['op'];folder=r.get('folder','inbox')
 if op=='boot':return dict(accounts=m.configured_accounts(cfg),default=cfg.get('username',''),invoice_account=cfg.get('invoice_account',cfg.get('username','')),raw=raw,**cached(folder,cfg))
 if op=='list':
  if not m.configured_accounts(cfg):return {'messages':[],'total':0,'errors':['No accounts configured.']}
  notices=m.NewMailNotifications();rows,total,errors=m.combined_headers(cfg,observer=notices.observe,folder=folder)
  data=dict(messages=normal(rows),total=total,errors=errors);save_cache(folder,data);return data
 if op in ('read','resources','image','attachment','reply'):
  e=r['item'];a=m.message_account(cfg,e);limit=m.MEDIA_LIMIT if op in ('resources','image','attachment') else m.MESSAGE_LIMIT
  message=m.inbox_message(a,m.password(a),e,limit)
  if op=='reply':return dict(m.reply_draft(message,a),_reply_source=m.reply_source(a,e),_reply_id='|'.join(map(str,identity(e))))
  if op=='image':
   i=int(r['index']);items=message['images']
   if not 0<=i<len(items):raise ValueError('Image is no longer available')
   p=m.image_file(items[i]);thumb=m.image_thumbnail(p);preview=m.cache_folder('thumbnails')/(p.stem+'.png');thumb.savev(str(preview),'png',[],[]);return {'path':str(p),'preview':str(preview)}
  if op=='attachment':
   if message['truncated']:raise ValueError('Message exceeds the 20 MiB attachment limit')
   p=m.preview_file(a,e,m.MEDIA_LIMIT);_,_,rawmail=p.read_bytes().partition(b'\n');parsed=m.BytesParser(policy=m.email.policy.default).parsebytes(rawmail)
   parts=list(parsed.iter_attachments());i=int(r['index'])
   if not 0<=i<len(parts):raise ValueError('Attachment is no longer available')
   target=Path(r['path']).expanduser()
   with target.open('xb') as out:os.chmod(target,0o600);out.write(parts[i].get_payload(decode=True) or b'')
   return {'message':'Attachment saved','path':str(target)}
  result=serialize_message(message)
  if op=='resources':
   p=m.preview_file(a,e,m.MEDIA_LIMIT)
   if not message['truncated'] and p.exists():
    _,_,rawmail=p.read_bytes().partition(b'\n');parsed=m.BytesParser(policy=m.email.policy.default).parsebytes(rawmail)
    result['attachments']=[part.get_filename() or 'attachment' for part in parsed.iter_attachments()]
  return result
 if op in ('mark','trash','restore'):
  done=[]
  for e in r['items']:
   a=m.message_account(cfg,e)
   try:
    {'mark':m.inbox_mark_read,'trash':m.inbox_trash,'restore':m.restore_trash}[op](a,m.password(a),e)
    done.append(e);invalidate([e],cfg,op!='mark')
   except Exception as exc:return dict(cached(folder,cfg),message=f'{len(done)} completed; '+str(exc))
  return dict(cached(folder,cfg),message=f'{len(done)} message(s) updated')
 if op=='trash_plan':return {'plan':normal(m.prepare_empty_trash(cfg))}
 if op=='empty_trash':
  # Re-resolve account configuration; a confirmation may outlive setup edits.
  plan=[]
  for item in r['plan']:
   current=account(cfg,item['account']['username'])
   if current['imap_host']!=item['account']['imap_host']:raise ValueError('Account server changed; review Trash again')
   plan.append(dict(item,account=current))
  count,errors=m.empty_trash_plan(plan);save_cache('trash',{'messages':[],'total':0,'errors':errors})
  return {'messages':[],'message':f'{count} messages permanently removed'+('\n'+'\n'.join(errors) if errors else '')}
 if op=='send':
  d=r['draft'];a=account(cfg,d['account']);invoice=bool(d.get('invoice'));pdf=d.get('attachment','');attachments=d.get('attachments') or ([pdf] if pdf else [])
  token=str(uuid.UUID(d['id']));base=Path(pdf).resolve() if invoice and pdf else Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'simplemail/outbox'/token
  if d.get('revision'):base=base.with_name(base.name+'.revision-'+token)
  receipt=base.with_suffix(base.suffix+'.sent.json')
  if invoice and not d.get('revision') and receipt.exists() and json.loads(receipt.read_text()).get('status')=='filed':return {'revision_required':True}
  source=d.get('_reply_source');replycfg=m.message_account(cfg,source) if source else None
  try:message=m.send(pdf,d['recipient'],d['subject'],d['body'],a,m.password(a),attachments=attachments,record_base=base,invoice=invoice,reply_to=source,reply_cfg=replycfg)
  except Exception as exc:message=str(exc)
  state=json.loads(receipt.read_text()).get('status') if receipt.exists() else None
  return {'message':message,'send_status':state,'complete':state=='filed','pending':state=='accepted'}
 if op=='restore_origin':
  from mail_foreground import restore_origin
  restore_origin(r.get('origin'));return {}
 if op=='origin':
  from mail_foreground import capture_origin
  return {'origin':capture_origin()}
 if op=='editor':return {'body':m.edit_body(r['body'])}
 if op=='save_account':
  a=m.setup_account(r['values']);original=r.get('original') or None
  secret=r.get('password','')
  if not secret and original:secret=m.password(account(cfg,original))
  if not secret:raise ValueError('Enter a password or app password')
  m.verify_account(a,secret);m.save_setup_account(a,secret,original,r['raw']);return handle({'op':'boot'})
 if op=='remove_account':m.remove_setup_account(r['original'],r.get('replacement'),r['raw']);return handle({'op':'boot'})
 if op=='import':
  import fairemail_import as f
  data=f.read_backup(r['path'],r.get('password',''));domains=[d.strip() for d in r['domains'].split(',') if d.strip()]
  if not domains:raise ValueError('Enter the email domains to import')
  result=f.import_accounts(data,domains)
  if r.get('report'):
   target=Path(r['report']).expanduser();target.parent.mkdir(parents=True,exist_ok=True);target.write_text('\n'.join(result)+'\n');target.chmod(0o600)
  return dict(handle({'op':'boot'}),message='\n'.join(result))
 raise ValueError('Unknown operation')

def main():
 try:
  r=json.load(sys.stdin)
  with contextlib.redirect_stdout(io.StringIO()):data=handle(r)
  print(json.dumps({'ok':True,'data':normal(data)},ensure_ascii=False))
 except Exception as exc:print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False))
if __name__=='__main__':main()

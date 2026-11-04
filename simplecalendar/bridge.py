"""JSON bridge for the native GTK calendar. Existing sync/storage stays in Python."""
from datetime import date,datetime,timedelta
import sys,json,io,contextlib
import core,layers

def handle(r):
 op=r['op']
 if op=='sync':
  if not core.sync():raise RuntimeError(core.read_json('sync.json',{}).get('error','Calendar is not connected.'))
 elif op=='save':
  form=r['form'];original=r.get('original')
  if original:core.update(original,**form)
  else:
   name=core.settings().get('calendar','main')
   if r.get('report'):
    core.report_due(r['base'])
    due=date.fromisoformat(form['day']);rows,errors=core.events(core.local_dt(due),core.local_dt(due+timedelta(days=1)))
    if any(e['calendar']==name and e['title'].removeprefix('🛂 ').strip()==form['title'].removeprefix('🛂 ').strip() and datetime.fromisoformat(e['start']).date()==due for e in rows):raise ValueError('A report already exists on this date. Edit it instead.')
   core.add(calendar=name,**form)
  core.sync()
 elif op=='remove':core.remove(r['original']);core.sync()
 elif op not in ('list','report'):raise ValueError('Unknown calendar operation')
 if op=='report':return {'day':core.report_due(r['base'])}
 selected=date.fromisoformat(r.get('day',date.today().isoformat()));end=selected+timedelta(days=max(1,min(int(r.get('days',1)),90)))
 first=selected.replace(day=1);last=(first+timedelta(days=32)).replace(day=1)
 rows,errors=core.events(core.local_dt(min(first,selected)),core.local_dt(max(last,end)))
 local=layers.events(min(first,selected),max(last,end)) if r.get('local',True) else []
 cards=[]
 for offset in range((end-selected).days):
  day=selected+timedelta(days=offset)
  for e in rows:
   if core.on_day(e,day):cards.append(dict(e,view_day=day.isoformat()))
  for e in local:
   if e['day']==day:cards.append(dict(e,day=e['day'].isoformat(),view_day=day.isoformat(),editable=False))
 marks=[]
 for offset in range((last-first).days):
  day=first+timedelta(days=offset)
  if any(core.on_day(e,day) for e in rows) or any(e['day']==day for e in local):marks.append(day.day)
 moons=[e['day'].day for e in local if e['layer']=='Full moon' and first<=e['day']<last]
 allrows,_=core.events();report=core.next_report(allrows)
 state=core.read_json('sync.json',{});settings=core.settings()
 status=state.get('error') or ('Changes saved locally · waiting to sync' if state.get('pending') else 'Synced' if state.get('ok') else 'Not synced yet' if settings else 'Connect Google / CalDAV from Accounts')
 if state.get('ok') and state.get('last'):status+=' · '+datetime.fromisoformat(state['last']).astimezone().strftime('%d %b %H:%M')
 if errors:status+=' · some events could not be read'
 log=core.ROOT/'sync.log'
 return {'sync_log':log.read_text()[-5000:] if log.exists() else '', 'day':selected.isoformat(),'cards':cards,'marks':marks,'moons':moons,'report':report,'status':status,'connected':bool(settings),'provider':settings.get('provider','')}
if __name__=='__main__':
 try:
  r=json.load(sys.stdin)
  with contextlib.redirect_stdout(io.StringIO()):data=handle(r)
  print(json.dumps({'ok':True,'data':data},ensure_ascii=False))
 except Exception as e:print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=False))

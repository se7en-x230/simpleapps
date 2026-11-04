"""One JSON request on stdin, one JSON response on stdout. No GUI imports."""
import sys,json,contextlib,io
from pathlib import Path
import core,auth

def handle(r):
 op=r['op']
 if op=='sync':core.sync()
 elif op=='connect':auth.connect()
 elif op=='save':core.save(r['form'],r.get('original'))
 elif op=='remove':core.remove(r['original'])
 elif op=='export':
  path=Path(r['path']).expanduser()
  if path.exists():raise core.ContactError('Choose a new export filename; this file already exists.')
  return {'message':f'Exported {core.export_vcard(path)} contacts to {path}'}
 elif op!='list':raise ValueError('Unknown contacts operation')
 data=core.cache();data['error']=core.read('status.json',{}).get('error','');data['connected']=(core.ROOT/'google-token.json').exists()
 return data
if __name__=='__main__':
 try:
  request=json.load(sys.stdin)
  with contextlib.redirect_stdout(io.StringIO()):data=handle(request)
  print(json.dumps({'ok':True,'data':data},ensure_ascii=False))
 except Exception as e:print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=False))

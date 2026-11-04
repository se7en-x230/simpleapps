"""Desktop OAuth: loopback callback, state verification and PKCE."""
from pathlib import Path
from http.server import HTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlencode,urlparse,parse_qs
import os,shutil,secrets,hashlib,base64,time,json,subprocess,requests

def authorize(scope,client_path=None):
 path=Path(client_path).expanduser() if client_path else Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'simplecalendar/google-client.json'
 try:client=json.loads(path.read_text())['installed'];cid=client['client_id'];secret=client['client_secret']
 except (OSError,KeyError,ValueError):raise RuntimeError('Desktop OAuth client missing. Set up Calendar first or provide --client-json.') from None
 state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
 challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=');result={}
 class Callback(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_GET(self):
   q=parse_qs(urlparse(self.path).query)
   if urlparse(self.path).path!='/callback' or not secrets.compare_digest(q.get('state',[''])[0],state):
    self.send_response(400);self.end_headers();self.wfile.write(b'Invalid callback. Return to the Google sign-in tab.');return
   result.update(code=q.get('code',[''])[0],error=q.get('error',[''])[0])
   self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
   self.wfile.write(b'<html><body style="background:#252525;color:#eee;font:20px sans-serif;padding:40px">Return to your calendar or contacts app to finish connecting. You may close this tab.</body></html>')
 with HTTPServer(('127.0.0.1',0),Callback) as server:
  redirect=f'http://127.0.0.1:{server.server_port}/callback'
  url='https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(dict(client_id=cid,redirect_uri=redirect,response_type='code',scope=scope,access_type='offline',prompt='consent',state=state,code_challenge=challenge,code_challenge_method='S256'))
  browser=['simple-open','browser'] if shutil.which('simple-open') else ['xdg-open']
  subprocess.Popen([*browser,url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  print('Approve the requested Google access in the browser. Waiting up to thirty minutes…',flush=True)
  deadline=time.monotonic()+1800;server.timeout=1
  while not result and time.monotonic()<deadline:server.handle_request()
 if not result.get('code'):raise RuntimeError('Google sign-in was cancelled or timed out. Try again from Accounts.')
 r=requests.post('https://oauth2.googleapis.com/token',data=dict(code=result['code'],client_id=cid,client_secret=secret,redirect_uri=redirect,grant_type='authorization_code',code_verifier=verifier),timeout=35)
 if not r.ok:raise RuntimeError('Google could not complete sign-in. Try connecting again.')
 token=r.json()
 if not token.get('refresh_token') or scope not in token.get('scope','').split():raise RuntimeError('The requested permission was not granted. Connect again and approve access.')
 token['expires_at']=time.time()+int(token.get('expires_in',3600))
 return client,token

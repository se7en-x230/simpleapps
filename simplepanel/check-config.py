from pathlib import Path
import subprocess,tempfile,os,json
root=Path(__file__).resolve().parents[1];panel=root/'simplepanel/simplepanel'
valid='[panel]\nclock_timezone=Europe/Lisbon\n[dashboard]\nclock_labels=Lisbon;Tokyo;\nclock_zones=Europe/Lisbon;Asia/Tokyo;\n[markets]\nids=bitcoin;ethereum;\nlabels=BTC;ETH;\ncurrency=usd\ndecimals=2\n'
with tempfile.TemporaryDirectory() as t:
 p=Path(t)/'config.ini'
 for content,ok in [('',True),(valid,True),(valid.replace('Asia/Tokyo','Invalid/Zone'),False),(valid.replace('BTC;ETH;','BTC;'),False),(valid.replace('decimals=2','decimals=9'),False),(valid.replace('currency=usd','currency=usd&bad=1'),False),(valid+'[unused]\na=b\n',True),(valid.replace('clock_timezone=Europe/Lisbon','clock_timezone=not-a-zone'),False),(valid.replace('[dashboard]','[dashboard]\nclocks=maybe'),False)]:
  p.write_text(content)
  for args in [[],['--system-dashboard']]:
   r=subprocess.run([str(panel),'--config',str(p),'--check',*args],capture_output=True,text=True);assert (r.returncode==0)==ok,(content,r.stderr)
 print('PASS: defaults, custom cities/markets, invalid zones/lists/currency/precision/booleans, dashboard --config/--check')
# Compile an integration harness against the real market module; fake curl serves deterministic fixtures.
scratch=tempfile.TemporaryDirectory(prefix='simplepanel-check-');work=Path(scratch.name)
(work/'market-test.c').write_text('''#include "dashboard-settings.h"
#include <stdio.h>
int main(int argc,char **argv){GKeyFile *f=g_key_file_new();GError *e=NULL;if(!g_key_file_load_from_file(f,argv[1],0,&e)||!dashboard_settings_load(f,&e))return 2;simple_market_refresh();for(int i=0;i<100;i++){while(g_main_context_iteration(NULL,FALSE));g_usleep(10000);}json_object *p=simple_market_read();for(gsize i=0;i<dashboard_settings.markets;i++){char *s=simple_market_price(p,i);puts(s);g_free(s);}if(p)json_object_put(p);simple_market_stop();return 0;}
''')
flags=subprocess.check_output(['pkg-config','--cflags','--libs','gio-2.0','json-c'],text=True).split()
subprocess.run(['cc','-I'+str(root/'simplepanel'),str(work/'market-test.c'),str(root/'simplepanel/dashboard-settings.c'),'-o',str(work/'market-test'),*flags,'-lm'],check=True)
with tempfile.TemporaryDirectory() as t:
 d=Path(t);(d/'bin').mkdir();curl=d/'bin/curl';curl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_CALLS"\ncat "$TEST_RESPONSE"\n');curl.chmod(0o755)
 response=d/'response';response.write_text(json.dumps({'bitcoin':{'usd':12.345,'usd_24h_change':1.2},'ethereum':{'usd':2.5}}))
 conf=d/'config.ini';conf.write_text(valid)
 env=dict(os.environ,PATH=str(d/'bin')+':/usr/bin',XDG_CACHE_HOME=str(d/'cache'),TEST_CALLS=str(d/'calls'),TEST_RESPONSE=str(response))
 def run():return subprocess.check_output([str(work/'market-test'),str(conf)],env=env,text=True)
 assert run()=='12.35 USD\n2.50 USD\n';assert 'ids=bitcoin,ethereum&vs_currencies=usd' in (d/'calls').read_text()
 assert run()=='12.35 USD\n2.50 USD\n';assert len((d/'calls').read_text().splitlines())==1
 for f in (d/'cache').rglob('*.json'):os.utime(f,(1,1))
 response.write_text('{"error":"rate limit"}')
 assert run()=='12.35 USD\n2.50 USD\n'
 conf.write_text(valid.replace('currency=usd','currency=eur'))
 assert run()=='Price unavailable\nPrice unavailable\n'
 print('PASS: real asynchronous quote fetch/format, cache reuse, failed request preserves good cache, currency isolation')

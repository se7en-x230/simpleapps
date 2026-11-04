import os,json,subprocess,tempfile,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
exe=root/'simplepicker-native'
sys.path.insert(0,str(root/'python'))
from ui import line_search
text='Café menu\nSTRASSE\nStraße\nAlpha beta\nBeta alpha\n東京\nRésumé\n\nDuplicate\nDuplicate\n'
for query in ('','cafe','strasse','alpha beta','beta ALPHA','résumé','東京','missing','alpha\u2003beta'):
    result=subprocess.run([str(exe),'--search',query],input=text,text=True,capture_output=True,check=True)
    assert result.stdout==''.join(s+'\n' for s in line_search(text.splitlines())(query)),(query,result.stdout)
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/'config.toml'
    for content,ok in (('',True),('[desktop]\nbackend="generic"',True),('[power.lock]\nicon="system-lock-screen-symbolic"',True),('[commands]\ncopy=["wl-copy", "--primary"]',True),('[power.lock]\nicon=42',False),('[power.lock]\nicon="./missing.png"',False),('[commands]\ncopy=[42]',False),('[commands]\ncopy=[""]',False),('[power.lock]\nkey="u"',False),('[screensaver]\nidle_seconds=10',True),('[screensaver]\nidle_seconds=0',False),('[screensaver]\nidle_seconds=86401',False),('[screensaver]\nidle_seconds=true',False),('[wrong]\na=1',False),('[desktop]\nbackend="oops"',False),('broken=[',False)):
        path.write_text(content)
        result=subprocess.run([str(exe),'--config',str(path),'--check-config'],capture_output=True,text=True)
        assert (result.returncode==0)==ok,(content,result.returncode,result.stderr)
    for payload in (b'bad\xff',b'bad\x00text'):
        result=subprocess.run([str(exe),'--search',''],input=payload,capture_output=True)
        assert result.returncode==2
print('PASS: search parity, Unicode, TOML config validation, duplicate shortcuts, bad paths/types and invalid input.')

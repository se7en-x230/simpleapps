"""Actual cliphist + ffmpeg, GTK selection/preview, and an isolated clipboard sink."""
import json,os,subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='clipboard-video-') as tmp:
    work=Path(tmp);bindir=work/'bin';bindir.mkdir();config=work/'config';(config/'simplepicker').mkdir(parents=True)
    folder=work/('long recording folder '*8);folder.mkdir()
    video=folder/'short screenrecord #1.MP4'
    subprocess.run(['/usr/bin/ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=red:s=160x90:r=25','-frames:v','1','-c:v','libx264','-threads','1',str(video)],check=True)
    missing=work/'missing.mp4';image=work/'image.png'
    subprocess.run(['/usr/bin/ffmpeg','-nostdin','-v','error','-i',str(video),'-frames:v','1',str(image)],check=True)
    helper=bindir/'helper'
    helper.write_text('''#!/usr/bin/env python3
import json,os,sys,time
from pathlib import Path
name=Path(sys.argv[0]).name
if name=='cliphist':os.execv('/usr/bin/cliphist',['cliphist','-db-path',os.environ['TEST_DB'],*sys.argv[1:]])
if name=='ffmpeg':
 with open(os.environ['TEST_CALLS'],'a') as stream:stream.write(json.dumps(sys.argv[1:])+'\\n')
 time.sleep(float(os.environ.get('TEST_DELAY','0')))
 os.execv('/usr/bin/ffmpeg',['ffmpeg',*sys.argv[1:]])
if sys.argv[1]=='copy':
 Path(os.environ['TEST_COPY']).write_bytes(sys.stdin.buffer.read())
 Path(os.environ['TEST_ARGS']).write_text(json.dumps(sys.argv[2:]))
''');helper.chmod(0o755)
    for name in ('cliphist','ffmpeg'):(bindir/name).symlink_to(helper)
    (config/'simplepicker/config.toml').write_text(f'[desktop]\nbackend="generic"\n[commands]\ncopy=["{helper}","copy"]\n')
    env=dict(os.environ,HOME=tmp,XDG_CONFIG_HOME=str(config),XDG_DATA_HOME=str(work/'data'),SIMPLEPICKER_ASSETS=str(root/'assets'),PATH=str(bindir)+':'+os.environ['PATH'],TEST_DB=str(work/'history.db'),TEST_COPY=str(work/'copy'),TEST_ARGS=str(work/'args'),TEST_CALLS=str(work/'calls'),SP_TEST_PLAN=str(work/'plan'),GTK_A11Y='none')
    env.pop('SIMPLEPICKER_CONFIG',None);env.pop('SIMPLEPICKER_THEME',None)
    uri=(video.as_uri()+'\r\n').encode()
    for payload in (uri,(missing.as_uri()+'\r\n').encode(),b'Ordinary text',image.read_bytes()):
        subprocess.run([str(bindir/'cliphist'),'store'],input=payload,env=env,check=True)
    def run(steps):
        (work/'plan').write_text(json.dumps(steps))
        result=subprocess.run([str(root/'tests/driver'),'--clipboard'],env=env,capture_output=True,timeout=20)
        assert result.returncode==0,result.stderr
    run([dict(query='video'),dict(select='Video · '+video.name,wait=800),dict(expect_preview='image'),dict(select='Video · '+missing.name),dict(expect_preview='moved or deleted'),dict(select='Video · '+video.name),dict(expect_preview='image',key='Return')])
    assert (work/'copy').read_bytes()==uri
    assert json.loads((work/'args').read_text())==['--type','text/uri-list']
    assert len((work/'calls').read_text().splitlines())==1,'Repeated selection decoded the same video again'
    print('PASS: Video filter and filenames; long encoded path; 40ms recording previews; moved-file message; cached frame; Enter keeps the exact file attachment.',flush=True)
    env['TEST_DELAY']='0.6'
    run([dict(query='video'),dict(select='Video · '+video.name,wait=200),dict(select='Video · '+missing.name),dict(expect_preview='moved or deleted'),dict(select='Video · '+video.name,wait=1200),dict(expect_preview='image',key='Return')])
    assert len((work/'calls').read_text().splitlines())==3,'Cancelled preview did not retry exactly once'
    assert (work/'copy').read_bytes()==uri
    print('PASS: switching away cancels the preview; returning retries and displays the frame.',flush=True)
    env.pop('TEST_DELAY')
    run([dict(query='image',wait=800),dict(expect_preview='image',key='Return')])
    assert (work/'copy').read_bytes()==image.read_bytes()
    assert json.loads((work/'args').read_text())==['--type','image/png']
    print('PASS: Image filtering, previews and image clipboard format unchanged.',flush=True)

    photo=folder/'family photo #1.png';photo.write_bytes(image.read_bytes())
    absent=work/'missing-photo.png'
    for target in (photo,absent):
        subprocess.run([str(bindir/'cliphist'),'store'],input=(target.as_uri()+'\r\n').encode(),env=env,check=True)
    run([dict(query='image'),dict(select='Image · '+photo.name,wait=800),dict(expect_preview='image'),dict(select='Image · '+absent.name),dict(expect_preview='moved or deleted'),dict(select='Image · '+photo.name),dict(expect_preview='image',key='Return')])
    assert (work/'copy').read_bytes()==(photo.as_uri()+'\r\n').encode()
    assert json.loads((work/'args').read_text())==['--type','text/uri-list']
    multiple=(photo.as_uri()+'\r\n'+image.as_uri()+'\r\n').encode()
    subprocess.run([str(bindir/'cliphist'),'store'],input=multiple,env=env,check=True)
    run([dict(query=photo.name,wait=800),dict(expect_preview='image',key='Return')])
    assert (work/'copy').read_bytes()==multiple
    print('PASS: Yazi image URI thumbnail, encoded filename, missing image, multiple-file preview and unchanged attachments.',flush=True)

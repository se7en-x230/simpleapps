import importlib.util,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
S=Path(__file__).resolve().parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=load('streams',S/'scripts/simpleplayer-streams.py')
class Streams(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.env=patch.dict(os.environ,{'HOME':str(self.root),'XDG_CONFIG_HOME':str(self.root/'cfg'),'XDG_CACHE_HOME':str(self.root/'cache'),'XDG_RUNTIME_DIR':str(self.root/'run')});self.env.start();self.s=m.Streams()
 def tearDown(self):self.env.stop();self.temp.cleanup()
 def test_bad_urls(self):
  for url in ('file:///etc/passwd','--script=oops','https://user:pass@host/x','https://a/\nthing','ftp://a/x'):
   with self.assertRaises(ValueError):m.http_url(url)
  with self.assertRaises(ValueError):m.youtube_url('https://youtube.com.evil.invalid/watch')
 def test_favourites_no_network_and_portable(self):
  with patch.object(m,'get_bytes',side_effect=AssertionError('Unexpected network')):
   self.assertEqual(self.s.search('radio',''),[])
   self.s.favourite('radio','https://example.org/live');self.assertEqual(self.s.search('radio','')[0]['path'],'https://example.org/live')
   self.assertTrue((self.root/'cfg/simpleplayer/streams.json').exists())
   self.assertFalse(self.s.favourite('radio','https://example.org/live'));self.assertEqual(self.s.saved(),[])
 def test_bad_favourites_preserved(self):
  self.s.file.parent.mkdir(parents=True);self.s.file.write_text('broken')
  with self.assertRaises(ValueError):self.s.favourite('radio','https://example.org/live')
  self.assertEqual(self.s.file.read_text(),'broken')
 def test_radio_search_filters_and_fails_over(self):
  self.s.mirrors=['https://one.invalid','https://two.invalid']
  data=[dict(name='Jazz',url_resolved='https://example.org/live',country='Germany',codec='MP3'),dict(name='Bad',url='file:///etc/passwd')]
  with patch.object(m,'get_bytes',side_effect=[OSError(),json.dumps(data).encode()]) as get:
   rows=self.s.search('radio','jazz & soul');self.assertEqual(len(rows),1);self.assertEqual(get.call_count,2);self.assertIn('name=jazz+%26+soul',get.call_args.args[0])
 def test_youtube_args_and_playlist(self):
  data={'title':'Playlist','entries':[{'id':'abc','url':'https://www.youtube.com/watch?v=abc','title':'Track'}]}
  with patch.object(m.shutil,'which',return_value='/bin/yt-dlp'),patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(data),'') ) as run:
   self.assertEqual(len(self.s.search('youtube','https://www.youtube.com/playlist?list=abc')),2)
   self.s.search('youtube','music; echo test');args=run.call_args.args[0];self.assertEqual(args[-1],'ytsearch25:music; echo test');self.assertIn('--ignore-config',args)
 def test_thumbnail_for_playlist_tracks_and_reopened_player(self):
  url='https://www.youtube.com/watch?v=aqz-KE-bpKQ'
  item=self.s.current(url)
  self.assertEqual(m.youtube_thumbnail(item['path']),'https://i.ytimg.com/vi/aqz-KE-bpKQ/hqdefault.jpg')
  self.assertEqual(m.youtube_thumbnail('https://youtu.be/aqz-KE-bpKQ?t=1'),m.youtube_thumbnail(url))
  self.assertEqual(m.youtube_thumbnail('https://www.youtube.com/playlist?list=abc'),'')
  self.assertEqual(m.youtube_thumbnail('https://evil.invalid/watch?v=aqz-KE-bpKQ'),'')
 def test_optional_youtube(self):
  with patch.object(m.shutil,'which',return_value=None):
   with self.assertRaisesRegex(ValueError,'optional yt-dlp'):self.s.youtube('test')
   self.assertEqual(self.s.search('radio','https://example.org/live')[0]['source'],'radio')
 def test_playback_options_same_session(self):
  item,args=self.s.play_args('radio','https://example.org/live?x=1&y=2')
  self.assertEqual(args[-2:],['--',item['path']]);self.assertIn('--ytdl=no',args);self.assertIn('--no-video',args)
 def test_art_cache_and_state(self):
  with patch.object(m,'get_bytes',return_value=b'\x89PNG\r\n\x1a\nTEST') as get:
   item={'thumbnail':'https://example.org/a.png'};a=self.s.artwork(item);self.assertEqual(a,self.s.artwork(item));self.assertEqual(get.call_count,1)
  m.atomic_json(self.s.state,dict(path='https://a/live',source='radio'));self.assertEqual(self.s.current('/local/song'),{});self.assertEqual(self.s.current('https://a/live')['source'],'radio')
 def test_search_does_not_block_status(self):
  bridge=load('bridge',S/'bridge.py');b=bridge.Bridge();events=[];b.send=lambda **x:events.append(x)
  import threading,time
  gate=threading.Event()
  with patch.object(b.streams,'search',side_effect=lambda *x:gate.wait(2) or []),patch.object(bridge,'ipc',side_effect=OSError()):
   b.handle({'action':'browse','source':'radio','query':'test','id':1});start=time.monotonic();b.handle({'action':'status'});self.assertLess(time.monotonic()-start,.5)
   b.browse_id=2;gate.set();b.search_worker.shutdown(wait=True)
  self.assertFalse(any(x.get('event')=='rows' for x in events));b.art_worker.shutdown()
if __name__=='__main__':unittest.main()

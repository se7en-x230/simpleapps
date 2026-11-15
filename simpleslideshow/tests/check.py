import sys,tempfile,subprocess,json,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from render import Media,plan,probe,Renderer,Cancelled,audio_range,folder_images
from PIL import Image
class Timing(unittest.TestCase):
 def test_folder_import_order(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for name in ['image10.JPG','image2.png','image1.png','notes.txt','clip.mp4']:(root/name).touch()
   (root/'subfolder').mkdir();(root/'subfolder'/'hidden.png').touch()
   self.assertEqual([p.name for p in folder_images(root)],['image1.png','image2.png','image10.JPG'])
 def test_fit(self):
  p=plan([Media('/a','image'),Media('/b','video',3),Media('/c','image')],Media('/m','audio',10),True)
  self.assertEqual(p.total,300);self.assertEqual(p.frames[1],90)
 def test_fixed(self):self.assertAlmostEqual(plan([Media('/a','image'),Media('/b','image')],photo_seconds=4).seconds,7.4)
 def test_impossible(self):
  with self.assertRaisesRegex(ValueError,'too short'):plan([Media('/a','image'),Media('/b','video',30)],Media('/m','audio',4),True)
  with self.assertRaises(ValueError):plan([Media('/a','video',3)],Media('/m','audio',4),True)
 def test_timeline_spans(self):
  from timeline import spans
  p=plan([Media('/a','image'),Media('/b','video',2),Media('/c','image')])
  blocks=spans(p)
  self.assertEqual(blocks[0][0],0);self.assertAlmostEqual(blocks[-1][1],p.seconds)
  for before,after in zip(blocks,blocks[1:]):self.assertAlmostEqual(before[1]-after[0],p.fade/30)
 def test_music_cut_timing(self):
  music=Media('/song','audio',30)
  p=plan([Media('/a','image'),Media('/b','image')],music,True,music_in=12.5,music_out=22.5)
  self.assertEqual(p.total,300)
  for start,end in [(-1,5),(3,3),(5,4),(0,31),(float('nan'),5)]:
   with self.assertRaises(ValueError):audio_range(music,start,end)
 def test_short_clip(self):
  p=plan([Media('/a','video',.3),Media('/b','image')]);self.assertLess(2*p.fade,p.frames[0])
class Export(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
  for name,color in [('red','red'),('blue','blue')]:Image.new('RGB',(90,60),color).save(cls.root/(name+'.png'))
  cls.audio=cls.root/'song.wav';cls.video=cls.root/'clip.mp4'
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=2','-y',str(cls.audio)],check=True)
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=green:s=96x64:r=24:d=1.5','-c:v','libx264','-pix_fmt','yuv420p','-y',str(cls.video)],check=True)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def metadata(self,path):return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)]))
 def test_project_roundtrip_and_crop(self):
  from dataclasses import replace
  from project import write_project,read_project
  from render import refresh_media
  source=self.root/'split.png';im=Image.new('RGB',(200,100),'red');im.paste('blue',(100,0,200,100));im.save(source)
  item=Media(str(source),'image',1.2,'Focus',2,.2,.5,False)
  path=write_project(self.root/'edit.simpleslideshow.project',[item],probe(self.audio,True),fit=False)
  loaded=read_project(path);self.assertEqual(loaded['items'],[item]);self.assertEqual(refresh_media(item),item)
  self.assertEqual(json.loads(path.read_text())['items'][0]['path'],'split.png')
  self.assertEqual(plan(loaded['items']).total,36)
  for focus,channel in [(.2,0),(.8,2)]:
   target=self.root/f'crop-{channel}.mp4';Renderer().export(plan([replace(item,focus_x=focus)]),target,size=(160,90))
   raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(target),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
   pixel=raw[(45*160+80)*3:(45*160+80)*3+3];self.assertGreater(pixel[channel],200);self.assertLess(pixel[2-channel],30)
  self.assertEqual(Image.open(source).size,(200,100))
 def test_gentle_zoom_motion(self):
  from dataclasses import replace
  from render import refresh_media
  source=self.root/'zoom.png';im=Image.new('RGB',(640,360),'black');im.paste('white',(280,140,360,220));im.save(source)
  item=Media(str(source),'image',2,zoom=1,fill=True,end_zoom=1.2)
  self.assertEqual(refresh_media(item).end_zoom,1.2)
  target=self.root/'zoom.mp4';Renderer().export(plan([item]),target,size=(320,180))
  def white_area(at):
   raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(at),'-i',str(target),'-frames:v','1','-f','rawvideo','-pix_fmt','gray','-'])
   return sum(v>180 for v in raw)
  self.assertGreater(white_area(1.9),white_area(0)*1.25)
  raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(target),'-f','rawvideo','-pix_fmt','gray','-'])
  centers=[]
  for offset in range(0,len(raw),320*180):
   pixels=raw[offset:offset+320*180];points=[(i%320,i//320,v) for i,v in enumerate(pixels) if v>30]
   mass=sum(v for x,y,v in points);centers.append((sum(x*v for x,y,v in points)/mass,sum(y*v for x,y,v in points)/mass))
  # A centered slow zoom must not wobble by whole pixels between frames.
  for axis in (0,1):self.assertLess(max(c[axis] for c in centers)-min(c[axis] for c in centers),.6)

  self.assertAlmostEqual(float(self.metadata(target)['format']['duration']),2,delta=.05)
  joined=self.root/'zoom-crossfade.mp4';sequence=plan([item,item]);Renderer().export(sequence,joined,size=(320,180))
  self.assertAlmostEqual(float(self.metadata(joined)['format']['duration']),sequence.seconds,delta=.05)
 def test_subtitle_overlay(self):
  sub=self.root/'captions.srt';sub.write_text('1\n00:00:00,000 --> 00:00:01,000\nReadable caption\n')
  p=plan([probe(self.root/'red.png')],photo_seconds=1,subtitles=str(sub));target=self.root/'subtitled.mp4'
  Renderer().export(p,target,size=(360,640))
  raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(target),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
  self.assertGreater(sum(r>150 and g>150 and b>150 for r,g,b in zip(raw[0::3],raw[1::3],raw[2::3])),10)
 def test_fit_export(self):
  # Longer test track, with fixed video length in the middle.
  audio=self.root/'long.wav';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=5','-y',str(audio)],check=True)
  p=plan([probe(self.root/'red.png'),probe(self.video),probe(self.root/'blue.png')],probe(audio,True),True)
  target=self.root/'fit.mp4';Renderer().export(p,target,size=(160,90));data=self.metadata(target)
  self.assertAlmostEqual(float(data['format']['duration']),5,delta=.08)
  self.assertEqual({s['codec_type'] for s in data['streams']},{'audio','video'})
  v=next(s for s in data['streams'] if s['codec_type']=='video');self.assertEqual((v['width'],v['height']),(160,90));self.assertEqual(int(v['nb_frames']),150)
 def test_loop_fade_and_crossfade_pixels(self):
  p=plan([probe(self.root/'red.png'),probe(self.root/'blue.png')],probe(self.audio,True),False,2)
  target=self.root/'fixed.mp4';Renderer().export(p,target,size=(160,90))
  self.assertAlmostEqual(float(self.metadata(target)['format']['duration']),p.seconds,delta=.08)
  raw=subprocess.check_output(['ffmpeg','-v','error','-ss','1.7','-i',str(target),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
  pixel=raw[(45*160+80)*3:(45*160+80)*3+3];self.assertGreater(pixel[0],40);self.assertGreater(pixel[2],40)
  import array,math
  def rms(start):
   raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(start),'-i',str(target),'-t','0.08','-vn','-f','f32le','-ac','1','-']);samples=array.array('f');samples.frombytes(raw);return math.sqrt(sum(v*v for v in samples)/len(samples))
  self.assertLess(rms(p.seconds-.09),rms(.2)/8)
 def test_preview_matches_timing_and_music_cut(self):
  p=plan([probe(self.root/'red.png'),probe(self.root/'blue.png')],probe(self.audio,True),False,2,.5,1.5)
  target=self.root/'preview.webm';Renderer().preview(p,target)
  data=self.metadata(target)
  self.assertAlmostEqual(float(data['format']['duration']),p.seconds,delta=.08)
  video=next(s for s in data['streams'] if s['codec_type']=='video')
  self.assertEqual((video['width'],video['height']),(640,360));self.assertEqual(video['codec_name'],'vp8')
  self.assertIn('vorbis',[s['codec_name'] for s in data['streams']])
 def test_pair_full_resolution(self):
  p=plan([probe(self.root/'red.png'),probe(self.root/'blue.png')],probe(self.audio,True),False,1)
  outputs=Renderer().export_pair(p,self.root/'pair.mp4')
  self.assertEqual([x.name for x in outputs],['pair-high.mp4','pair-web.mp4'])
  for target,size in zip(outputs,[(1920,1080),(1280,720)]):
   data=self.metadata(target);v=next(s for s in data['streams'] if s['codec_type']=='video')
   self.assertEqual((v['width'],v['height']),size);self.assertEqual(v['codec_name'],'h264')
   self.assertAlmostEqual(float(data['format']['duration']),p.seconds,delta=.08)
   raw=target.read_bytes();self.assertLess(raw.index(b'moov'),raw.index(b'mdat'))
  before=[x.read_bytes() for x in outputs]
  with self.assertRaises(ValueError):Renderer().export_pair(p,self.root/'pair.mp4')
  self.assertEqual(before,[x.read_bytes() for x in outputs])
 def test_portrait_pair(self):
  p=plan([probe(self.root/'red.png')],photo_seconds=1)
  outputs=Renderer().export_pair(p,self.root/'portrait.mp4',portrait=True)
  for target,size in zip(outputs,[(1080,1920),(720,1280)]):
   v=next(s for s in self.metadata(target)['streams'] if s['codec_type']=='video')
   self.assertEqual((v['width'],v['height']),size)
 def test_cut_audio_and_loop_selected_range(self):
  source=self.root/'three-tones.wav'
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',r"aevalsrc=0.2*sin(2*PI*if(lt(t\,1)\,220\,if(lt(t\,2)\,660\,1100))*t):s=48000:d=3",str(source)],check=True)
  music=probe(source,True);cut=self.root/'cut.mp3'
  Renderer().export_audio(music,cut,1,2)
  self.assertAlmostEqual(probe(cut,True).duration,1,delta=.08)
  def frequency(path,start):
   import array
   raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-ss',str(start),'-t','0.2','-vn','-f','f32le','-ac','1','-ar','48000','-'])
   samples=array.array('f');samples.frombytes(raw)
   return sum(a<=0<b for a,b in zip(samples,samples[1:]))/.2
  self.assertAlmostEqual(frequency(cut,.2),660,delta=10)
  target=self.root/'cut-loop.mp4'
  p=plan([probe(self.root/'red.png')],music,False,4,1,2)
  Renderer().export(p,target,size=(160,90))
  for t in (.2,1.2,2.2):self.assertAlmostEqual(frequency(target,t),660,delta=10)
  fit=self.root/'cut-fit.mp4'
  Renderer().export(plan(p.items,music,True,4,1,2),fit,size=(160,90))
  self.assertAlmostEqual(float(self.metadata(fit)['format']['duration']),1,delta=.08)
  before=cut.read_bytes()
  with self.assertRaises(ValueError):Renderer().export_audio(music,cut,0,1)
  self.assertEqual(cut.read_bytes(),before)
 def test_cancel_and_existing(self):
  p=plan([probe(self.root/'red.png')],photo_seconds=1);r=Renderer();r.cancel();target=self.root/'cancel.mp4'
  with self.assertRaises(Cancelled):r.export(p,target,size=(160,90))
  self.assertFalse(target.exists());target.write_bytes(b'keep')
  with self.assertRaises(ValueError):Renderer().export(p,target)
  self.assertEqual(target.read_bytes(),b'keep')
if __name__=='__main__':unittest.main()

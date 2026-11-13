import io,runpy,tempfile,unittest,configparser
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout
module=runpy.run_path(str(Path(__file__).resolve().parents[1]/'simplecapture'),run_name='capture_test')
class Annotation(unittest.TestCase):
 def test_existing_image_uses_editor_without_screen_capture(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source.jpg';source.write_bytes(b'original')
   config=module['DEFAULTS']|{'copy':False,'save':True,'notify':False,'save_dir':root/'titles'}
   commands=[]
   def run(args,**kwargs):
    commands.append(args)
    if args[0]=='ffmpeg':self.assertEqual(args[args.index('-i')+1],str(source));return module['PNG']+b'converted'
    self.assertEqual(args[0],'swappy')
    settings=configparser.ConfigParser();settings.read(Path(kwargs['env']['XDG_CONFIG_HOME'])/'swappy/config')
    self.assertTrue(settings.getboolean('Default','early_exit'));self.assertFalse(settings.getboolean('Default','auto_save'))
    self.assertEqual(Path(args[2]).read_bytes(),module['PNG']+b'converted')
    (Path(settings['Default']['save_dir'])/'title.png').write_bytes(module['PNG']+b'annotated');return b''
   function=module['capture']
   with patch.dict(function.__globals__,run=run),patch('shutil.which',side_effect=lambda name:name):
    output=function(config,source)
   self.assertEqual(source.read_bytes(),b'original');self.assertEqual(output.read_bytes(),module['PNG']+b'annotated')
   self.assertEqual([x[0] for x in commands],['ffmpeg','swappy'])
 def test_closing_without_save_adds_no_file(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source.jpg';source.write_bytes(b'original')
   config=module['DEFAULTS']|{'copy':False,'save':True,'notify':False,'save_dir':root/'titles'}
   function=module['capture']
   with patch.dict(function.__globals__,run=lambda args,**kw:module['PNG'] if args[0]=='ffmpeg' else b''),patch('shutil.which',side_effect=lambda name:name):
    self.assertIsNone(function(config,source))
   self.assertFalse((root/'titles').exists());self.assertEqual(source.read_bytes(),b'original')
 def test_input_cli_prints_saved_filename(self):
  output=io.StringIO();seen=[];function=module['main']
  def capture(config,source):seen.append((config,source));return Path('/tmp/title-copy.png')
  with patch.dict(function.__globals__,load_config=lambda:dict(module['DEFAULTS']),capture=capture),redirect_stdout(output):
   self.assertEqual(function(['--input','/tmp/original.png','--save','--no-copy','--print-path']),0)
  self.assertEqual(output.getvalue(),'/tmp/title-copy.png\n');self.assertEqual(seen[0][1],Path('/tmp/original.png'));self.assertTrue(seen[0][0]['edit'])
if __name__=='__main__':unittest.main()

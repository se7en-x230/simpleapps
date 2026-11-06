#!/usr/bin/env python3
"""Exercise standalone wrapper and actual shared UI against temporary clipboard fixtures."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os,shutil,json,subprocess
root=Path(__file__).resolve().parent;picker=root.parent/'simplepicker'
with TemporaryDirectory() as tmp:
 work=Path(tmp);bins=work/'bin';bins.mkdir();data=work/'share/simpleclip';data.mkdir(parents=True)
 shutil.copy(root/'simpleclip',bins/'simpleclip');shutil.copy(picker/'tests/driver',bins/'simpleclip-native')
 for name in ('config.toml','keys.ini'):shutil.copy(root/name,data/name)
 shutil.copy(picker/'assets/defaults.json',data/'defaults.json')
 (data/'style.css').write_text('@define-color simple_heading #f3a40a;')
 helper=bins/'helper';helper.write_text('''#!/usr/bin/env python3
from pathlib import Path
import os,sys
root=Path(os.environ['CLIP_TEST'])
if Path(sys.argv[0]).name=='cliphist':
 if sys.argv[-1]=='list':print('2\\tFirst item\\n1\\tSecond item')
 elif sys.argv[-1]=='decode':sys.stdout.buffer.write(sys.stdin.buffer.read())
 elif sys.argv[-1]=='delete':(root/'deleted').write_bytes(sys.stdin.buffer.read())
else:(root/'copied').write_bytes(sys.stdin.buffer.read())
''');helper.chmod(0o755)
 (bins/'cliphist').symlink_to(helper);(bins/'wl-copy').symlink_to(helper)
 env=dict(os.environ,HOME=str(work),XDG_CONFIG_HOME=str(work/'config'),XDG_DATA_HOME=str(work/'share'),PATH=str(bins)+':'+os.environ['PATH'],CLIP_TEST=str(work),SP_TEST_PLAN=str(work/'plan'),GTK_A11Y='none')
 for plan,expected in [([{'key':'Return','ctrl':True},{'key':'j'},{'key':'Return'}],b'1\tSecond item'),([{'query':'Second'},{'key':'Return'}],b'1\tSecond item'),([{'key':'Escape'}],None)]:
  (work/'copied').unlink(missing_ok=True);(work/'plan').write_text(json.dumps(plan))
  result=subprocess.run([str(bins/'simpleclip')],env=env,capture_output=True,timeout=15)
  assert result.returncode==0,result.stderr
  assert ((work/'copied').read_bytes() if (work/'copied').exists() else None)==expected
 assert (work/'config/simpleclip/config.toml').is_file()
 print('PASS: standalone launcher with no Simplepicker installation, private config, search, Ctrl+Enter navigation, j selection and Esc cancellation',flush=True)

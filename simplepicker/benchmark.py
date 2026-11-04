"""Read-only startup comparison: auto-close before any selection/action."""
from pathlib import Path
import subprocess,time,re,json,statistics
root=Path(__file__).resolve().parent
python_probe=root/'tests/python-probe.py'
records=[]
for name,args,stdin in [('menu-100',['-d'],''.join(f'Item {i}\n' for i in range(100))),('apps',['--apps'],''),('runner',['--runner'],''),('symbols',['--symbols'],'')]:
    for iteration in range(7):
        for implementation in (('Python','C') if iteration%2==0 else ('C','Python')):
            command=['python3',str(python_probe),*args] if implementation=='Python' else [str(root/'simplepicker-native'),*args,'--benchmark']
            start=time.monotonic_ns()//1000
            result=subprocess.run(command,input=stdin,text=True,capture_output=True,timeout=20)
            match=re.search(r'BENCH first_us=(\d+)',result.stderr)
            if result.returncode not in (0,1) or not match:raise RuntimeError((command,result.returncode,result.stderr))
            records.append(dict(mode=name,implementation=implementation,warmup=iteration==0,startup_ms=(int(match[1])-start)/1000))
    print(name+' complete',flush=True)
(root/'benchmark-results.json').write_text(json.dumps(records,indent=2))
report=['Native conversion startup comparison','Six measured warm runs per mode; one discarded warmup, alternating order.','Process start to first GTK after-paint; not physical presentation latency.','No selections, history writes or external actions. Installed Python files unchanged.','The C implementation differs internally; these are implementation comparisons, not isolated language overhead.','']
for name in ('menu-100','apps','runner','symbols'):
    values={impl:statistics.median(r['startup_ms'] for r in records if r['mode']==name and r['implementation']==impl and not r['warmup']) for impl in ('Python','C')}
    report.append(f'{name}: Python {values["Python"]:.1f} ms; C {values["C"]:.1f} ms')
(root/'benchmark-report.txt').write_text('\n'.join(report)+'\n')
print('\n'.join(report),flush=True)

#!/usr/bin/env python3
"""Headless config validation; optional --runtime tests require a GTK display."""
import os
from pathlib import Path
import subprocess
import tempfile
import sys
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='simplepanel-modules-') as tmp:
    work=Path(tmp);config=work/'config.ini'
    valid='[panel]\nenvironment=mango\n[layout]\nleft=clock;sample;\ncenter=\nright=\n[custom.sample]\ncommand=echo ok\ninterval=60\ntimeout=5\n'
    for content,ok in [('',True),(valid,True),*( (valid.replace('mango',env),True) for env in ('auto','hyprland','sway','generic')),
                       (valid.replace('mango','unknown'),False),(valid.replace('mango','kde'),False),(valid.replace('mango','gnome'),False),(valid.replace('clock;sample;','clock;clock;'),False),
                       (valid.replace('clock;sample;','missing;'),False),(valid.replace('interval=60','interval=0'),False),
                       (valid.replace('timeout=5','timeout=301'),False),(valid.replace('timeout=5','timeout=no'),False),
                       (valid.replace('command=echo ok','command='),False),(valid.replace('custom.sample','custom.clock'),False),
                       (valid+'max_chars=201\n',False),('[panel]\ninvest=true\n',True)]:
        config.write_text(content)
        run=subprocess.run([str(root/'simplepanel'),'--config',str(config),'--check'],capture_output=True,text=True)
        assert (run.returncode==0)==ok,(content,run.stderr)
    print('PASS module config: environments, ordering, duplicates, unknown names, bounded values, legacy investment')
    if '--runtime' not in sys.argv:sys.exit(0)
    config.write_text(f'''[panel]
environment=generic
[layout]
left=clock;ok;failure;flood;timeout;slow;
center=
right=
[custom.ok]
command=printf 'hello\\nTooltip'
interval=60
[custom.failure]
command=echo bad; exit 1
interval=60
[custom.flood]
command=head -c 5000 /dev/zero
interval=60
[custom.timeout]
command=sleep 20 & echo $! > {work}/child; wait
interval=60
timeout=1
[custom.slow]
command=sleep 20
interval=1
timeout=30
[custom.disabled]
command=touch {work}/disabled
''')
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','gtk4'],text=True).split()
    subprocess.run(['cc','-Wall','-Wextra','-Werror','-Wno-unused-parameter',str(root/'tests/modules.c'),'-o',str(work/'modules'),*flags],check=True)
    subprocess.run([str(work/'modules'),str(config)],check=True,timeout=10)
    assert not (work/'disabled').exists()
    pid=(work/'child').read_text().strip()
    status=Path('/proc')/pid/'stat'
    assert not status.exists() or status.read_text().split(') ')[1].startswith('Z'), 'Timeout left child alive'
    print('PASS child process cleanup; disabled command never executed')

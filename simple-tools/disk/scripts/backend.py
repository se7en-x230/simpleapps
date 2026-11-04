import os as _path_os, sys as _path_sys
from pathlib import Path as _Path
_roots=[_Path(__file__).resolve().parents[3],_Path(_path_os.environ.get('XDG_DATA_HOME',_Path.home()/'.local/share')),_Path.home()/'.local/src']
if _path_os.environ.get('SIMPLE_SOURCE_ROOT'):_roots.insert(0,_Path(_path_os.environ['SIMPLE_SOURCE_ROOT']))
for _root in reversed(_roots):
    for _name in ('simplepicker/python','simple-common'):
        if (_root/_name).is_dir():_path_sys.path.insert(0,str(_root/_name))
import json, os, subprocess
from pathlib import Path
EXCLUDED = set('tmpfs devtmpfs squashfs overlay proc sysfs devpts cgroup cgroup2 securityfs pstore debugfs tracefs configfs fusectl mqueue hugetlbfs autofs binfmt_misc ramfs bpf nsfs efivarfs rpc_pipefs'.split())

def mount_order(mount):
    target = mount['target']
    if target == '/boot' or target.startswith('/boot/'):
        group = 0
    elif target == '/':
        group = 1
    elif mount['source'].startswith('/dev/') or mount['fstype'] == 'zfs':
        group = 2
    else:
        group = 3
    return group, target.casefold(), mount['source']

def number(value):
    return None if value == '-' else int(value)

def human(value):
    if value is None:
        return 'Not reported'
    value = int(value)
    for unit in ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']:
        if abs(value) < 1024 or unit == 'PiB':
            return f'{value:.1f} {unit}'
        value /= 1024

def clean(value):
    return str(value).replace('\n', r'\n').replace('\r', r'\r').replace('\t', r'\t')

def folder_label(target):
    home = os.path.expanduser('~')
    if target == home:
        return '~'
    if target.startswith(home + '/'):
        return '~' + clean(target[len(home):])
    return clean(target)

def usage(mount):
    try:
        # Only numeric columns: mount paths never undergo whitespace splitting.
        result = subprocess.run(['df', '-B1', '--output=pcent,size,avail', '--', mount['target']],
                                capture_output=True, text=True, timeout=4,
                                env=dict(os.environ, LC_ALL='C'))
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or 'df failed')
        percent, size, available = result.stdout.splitlines()[-1].split()
        percent = number(percent.rstrip('%'))
        size, available = number(size), number(available)
        used = f'{percent}%' if percent is not None else 'Not reported'
        if percent is None and size is None and available is None:
            row = f'{folder_label(mount["target"])}  |  Capacity not reported'
        else:
            row = f'{folder_label(mount["target"])}  |  {human(available)} free / {human(size)}  |  {used} used'
        details = [
            f'Folder: {folder_label(mount["target"])}',
            f'Free: {human(available)}',
            f'Total: {human(size)}',
            f'Used: {used}',
            f'Mount point: {clean(mount["target"])}',
            f'Device: {clean(mount["source"])}',
            f'Filesystem: {clean(mount["fstype"])}',
            f'UUID: {clean(mount.get("uuid") or "Not available")}',
        ]
        return percent if percent is not None else -1, row, None, details
    except subprocess.TimeoutExpired:
        error = 'timed out after 4 seconds'
    except (ValueError, IndexError, RuntimeError, OSError) as exc:
        error = str(exc)
    return -1, f'{folder_label(mount["target"])}  |  Unavailable', error, [
        f'Mount point: {clean(mount["target"])}',
        f'Device: {clean(mount["source"])}',
        f'Filesystem: {clean(mount["fstype"])}',
        f'UUID: {clean(mount.get("uuid") or "Not available")}',
        f'Error: {clean(error)}',
    ]

def mounted_storage(choice):
    result = subprocess.run(['findmnt', '--json', '--list', '--output', 'SOURCE,TARGET,FSTYPE,UUID'],
                            capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Could not list mounted storage.')
    mounts = []
    for mount in json.loads(result.stdout).get('filesystems', []):
        source, kind = mount.get('source') or '', mount.get('fstype') or ''
        if not mount.get('target') or kind in EXCLUDED:
            continue
        # Local disks include encrypted/LVM/RAID devices and local ZFS pools.
        if choice == 'Local disks' and not (source.startswith('/dev/') or kind == 'zfs'):
            continue
        mounts.append(mount)
    mounts.sort(key=mount_order)
    return mounts

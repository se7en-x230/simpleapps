"""Display plans and recoverable wlr-output-management transactions."""
import os as _path_os, sys as _path_sys
from pathlib import Path as _Path
_roots=[_Path(__file__).resolve().parents[3],_Path(_path_os.environ.get('XDG_DATA_HOME',_Path.home()/'.local/share')),_Path.home()/'.local/src']
if _path_os.environ.get('SIMPLE_SOURCE_ROOT'):_roots.insert(0,_Path(_path_os.environ['SIMPLE_SOURCE_ROOT']))
for _root in reversed(_roots):
    for _name in ('simplepicker/python','simple-common'):
        if (_root/_name).is_dir():_path_sys.path.insert(0,str(_root/_name))
import copy
import fcntl
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile


def run(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Display request rejected')
    return result.stdout


def query():
    rows = json.loads(run(['wlr-randr', '--json']))
    if not rows:
        raise ValueError('No connected displays were reported.')
    return rows


def preferred(row):
    modes = row.get('modes', [])
    return next((m for m in modes if m.get('preferred')), next(iter(modes), None))


def snapshot(rows):
    result = []
    for row in rows:
        mode = next((m for m in row['modes'] if m.get('current')), preferred(row))
        result.append(dict(name=row['name'], make=row.get('make', ''), model=row.get('model', ''),
                           serial=row.get('serial', ''), enabled=row['enabled'],
                           mode={k: mode[k] for k in ('width', 'height', 'refresh')} if mode else None,
                           position=row.get('position', {'x': 0, 'y': 0}),
                           scale=row.get('scale', 1), transform=row.get('transform', 'normal'),
                           adaptive_sync=row.get('adaptive_sync', False)))
    return sorted(result, key=lambda r: r['name'])


def identity(row):
    return tuple(row.get(k, '') for k in ('name', 'make', 'model', 'serial'))


def mode_matches(a, b):
    return (a and b and a['width'] == b['width'] and a['height'] == b['height']
            and abs(a['refresh'] - b['refresh']) < .002)


def size(row):
    w, h = row['mode']['width'], row['mode']['height']
    if row['transform'] in ('90', '270', 'flipped-90', 'flipped-270'):
        w, h = h, w
    return max(1, int(w / row['scale'])), max(1, int(h / row['scale']))


def validate(plan, rows):
    if not isinstance(plan, list) or not plan or len({r['name'] for r in plan}) != len(plan):
        raise ValueError('Invalid display layout.')
    available = {identity(r): r for r in rows}
    if set(available) != {identity(r) for r in plan}:
        raise ValueError('The connected displays have changed. Reopen the layout for these screens.')
    if not any(r['enabled'] for r in plan):
        raise ValueError('At least one display must stay enabled.')
    for row in plan:
        if not isinstance(row['enabled'], bool):
            raise ValueError('Invalid display state.')
        if not row['enabled']:
            continue
        if not any(mode_matches(row['mode'], m) for m in available[identity(row)]['modes']):
            raise ValueError('The saved mode is unavailable on ' + row['name'])
        if not math.isfinite(row['scale']) or not .5 <= row['scale'] <= 4:
            raise ValueError('Display scale must be between 0.5 and 4.')
        if row['transform'] not in ('normal', '90', '180', '270', 'flipped', 'flipped-90', 'flipped-180', 'flipped-270'):
            raise ValueError('Invalid display rotation.')
        if any(type(row['position'][k]) is not int or not 0 <= row['position'][k] <= 100000 for k in ('x', 'y')):
            raise ValueError('Display positions must be nonnegative integers.')


def arguments(plan, dryrun=False):
    args = ['wlr-randr'] + (['--dryrun'] if dryrun else [])
    for r in plan:
        args += ['--output', r['name'], '--on' if r['enabled'] else '--off']
        if r['enabled']:
            m = r['mode']
            args += ['--mode', f"{m['width']}x{m['height']}@{m['refresh']:.6f}Hz",
                     '--pos', f"{r['position']['x']},{r['position']['y']}",
                     '--scale', str(r['scale']), '--transform', r['transform'],
                     '--adaptive-sync', 'enabled' if r['adaptive_sync'] else 'disabled']
    return args


def arrange(plan, names, vertical=False):
    result = copy.deepcopy(plan)
    by_name = {r['name']: r for r in result}
    offset = 0
    for name in names:
        row = by_name[name]
        row['enabled'] = True
        row['position'] = {'x': 0 if vertical else offset, 'y': offset if vertical else 0}
        offset += size(row)[1 if vertical else 0]
    for row in result:
        if row['name'] not in names:
            row['enabled'] = False
    return result


def internal(row):
    return bool(re.match(r'^(eDP|LVDS|DSI)-', row['name']))


def order(plan):
    return [r['name'] for r in sorted(plan, key=lambda r: (r['position']['x'], r['position']['y'], not internal(r), r['name']))]


def overlaps(plan):
    active = [r for r in plan if r['enabled']]
    for i, a in enumerate(active):
        aw, ah = size(a)
        ax, ay = a['position']['x'], a['position']['y']
        for b in active[i+1:]:
            bw, bh = size(b)
            bx, by = b['position']['x'], b['position']['y']
            if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                return True
    return False


def resize(plan, name, **changes):
    result = copy.deepcopy(plan)
    next(r for r in result if r['name'] == name).update(changes)
    if overlaps(result):
        active = [r for r in plan if r['enabled']]
        vertical = len(active) > 1 and len({r['position']['x'] for r in active}) == 1
        names = [r['name'] for r in sorted(active, key=lambda r: (r['position']['y'], r['position']['x']))] if vertical else order(active)
        result = arrange(result, names, vertical)
    return result


def restore(before):
    """Restore surviving outputs, retaining hotplugged screens and a visible fallback."""
    rows = query()
    old = {identity(r): r for r in before}
    plan = [copy.deepcopy(old.get(identity(r), r)) for r in snapshot(rows)]
    if not any(r['enabled'] for r in plan):
        first = plan[0]
        source = next(r for r in rows if r['name'] == first['name'])
        first.update(enabled=True, mode=preferred(source), scale=1, transform='normal', position={'x': 0, 'y': 0})
    try:
        validate(plan, rows)
        run(arguments(plan))
        return 'Previous layout restored.'
    except (ValueError, RuntimeError, subprocess.SubprocessError):
        fallback = snapshot(rows)
        for row in fallback:
            source = next(r for r in rows if r['name'] == row['name'])
            row.update(enabled=True, mode=preferred(source), scale=1, transform='normal', adaptive_sync=False)
        fallback = arrange(fallback, order(fallback))
        validate(fallback, rows)
        run(arguments(fallback))
        return 'Previous layout was unavailable; connected displays restored to preferred modes.'


def trial(before, after, confirm):
    rows = query()
    if snapshot(rows) != before:
        raise ValueError('The display layout changed while the menu was open. Please choose again.')
    validate(after, rows)
    run(arguments(after, dryrun=True))
    keep = False
    try:
        run(arguments(after))
        accepted = bool(confirm())
        if accepted:
            # A hotplug during confirmation invalidates the decision.
            validate(after, query())
            keep = True
    finally:
        if not keep:
            recovery = restore(before)
    return 'Layout kept for this session.' if keep else recovery


def bounded_confirmation(argv, seconds):
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=seconds)
        return process.returncode == 0 and output.strip() == 'keep'
    except subprocess.TimeoutExpired:
        return False
    finally:
        # Also close a native menu child left behind by a crashed Python bridge.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        process.stdout.close()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def transaction_lock():
    path = Path(os.environ['XDG_RUNTIME_DIR']) / 'simplepicker-displays-transaction.lock'
    lock = path.open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError('Another display change is awaiting confirmation.')
    return lock

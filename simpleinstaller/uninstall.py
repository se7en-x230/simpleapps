"""Receipt-based removal of app files, with shared ownership and rollback."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def registry_path(dirs):
    return dirs['state'] / 'simpleinstaller' / 'installed-files.json'

def read(dirs):
    path = registry_path(dirs)
    return json.loads(path.read_text()) if path.exists() else {'schema': 1, 'apps': [], 'files': {}}

def registration(files, stage, names, owners, dirs):
    registry = read(dirs)
    registry['apps'] = sorted(set(registry['apps']) | set(names))
    for dst, (src, preserve) in files.items():
        if preserve or src not in owners:
            continue
        previous = registry['files'].get(str(dst), {})
        registry['files'][str(dst)] = {
            'sha256': digest(src),
            'owners': sorted(set(previous.get('owners', [])) | owners[src]),
        }
    output = stage / 'installed-files.json'
    output.write_text(json.dumps(registry, indent=2) + '\n')
    files[registry_path(dirs)] = (output, False)

def safe_path(path, dirs):
    # Records may only remove installed programs and resources, never settings,
    # maintained sources, or a directory tree containing personal data.
    roots = [dirs['bin'], dirs['data'], dirs['home'] / '.local/lib']
    if not path.is_absolute() or '..' in path.parts or not any(path != root and path.is_relative_to(root) for root in roots):
        raise ValueError('Invalid uninstall receipt path: ' + str(path))
    if any(parent.is_symlink() for parent in [path, *path.parents]):
        raise ValueError('Refusing symlinked uninstall path: ' + str(path))

def plan(dirs, names):
    registry = read(dirs)
    selected = set(names) & set(registry['apps'])
    remove, keep = [], []
    for value, record in registry['files'].items():
        owners = set(record['owners'])
        if not owners & selected or owners - selected:
            continue
        path = Path(value)
        safe_path(path, dirs)
        if not path.exists():
            continue
        if not path.is_file() or digest(path) != record['sha256']:
            keep.append(path)
        else:
            remove.append(path)
    return registry, selected, sorted(remove), sorted(keep)

def atomic_json(path, value):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2)
        stream.write('\n')
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

def apply(dirs, names):
    registry, selected, remove, keep = plan(dirs, names)
    if not selected:
        return None
    state = registry_path(dirs).parent
    backup = state / ('uninstall-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(mode=0o700)
    shutil.copy2(registry_path(dirs), backup / 'installed-files.json.before')
    records = []
    for index, path in enumerate(remove):
        saved = backup / str(index)
        shutil.copy2(path, saved)
        records.append({'path': str(path), 'backup': str(saved)})
    receipt = {'status': 'prepared', 'apps': sorted(selected), 'files': records,
               'preserved_modified': [str(p) for p in keep]}
    atomic_json(backup / 'receipt.json', receipt)
    removed = []
    try:
        for record in records:
            path = Path(record['path'])
            safe_path(path, dirs)
            if digest(path) != registry['files'][str(path)]['sha256']:
                raise ValueError('File changed during uninstall: ' + str(path))
            path.unlink()
            removed.append(record)
        for path, record in list(registry['files'].items()):
            record['owners'] = sorted(set(record['owners']) - selected)
            if not record['owners']:
                del registry['files'][path]
        registry['apps'] = sorted(set(registry['apps']) - selected)
        atomic_json(registry_path(dirs), registry)
        receipt['status'] = 'uninstalled'
        atomic_json(backup / 'receipt.json', receipt)
    except BaseException:
        for record in reversed(removed):
            shutil.copy2(record['backup'], record['path'])
        shutil.copy2(backup / 'installed-files.json.before', registry_path(dirs))
        receipt['status'] = 'rolled-back'
        atomic_json(backup / 'receipt.json', receipt)
        raise
    return backup

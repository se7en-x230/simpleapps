#!/usr/bin/env python3
"""Small KeePassXC Secret Service picker; secrets never enter the UI bridge."""
import os
from pathlib import Path
import resource
import subprocess
import sys

BASE = '/org/freedesktop/secrets'
IFACE = 'org.freedesktop.Secret'
PROPS = 'org.freedesktop.DBus.Properties'

class Vault:
    def __init__(self):
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
        DBusGMainLoop(set_as_default=True)
        self.db = dbus
        self.bus = dbus.SessionBus()
        self.owner = self.bus.get_name_owner('org.freedesktop.secrets')
        daemon = dbus.Interface(self.bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus'), 'org.freedesktop.DBus')
        pid = int(daemon.GetConnectionUnixProcessID(self.owner))
        if subprocess.check_output(['ps', '-p', str(pid), '-o', 'comm='], text=True).strip() != 'keepassxc':
            raise ValueError('KeePassXC is not the active password service.')
        self.service = self.interface(BASE, IFACE + '.Service')
        self.paths = set()

    def interface(self, path, interface):
        return self.db.Interface(self.bus.get_object(self.owner, path), interface)

    def prop(self, path, kind, name):
        return self.interface(path, PROPS).Get(IFACE + '.' + kind, name)

    def entries(self):
        rows = {}
        locked = False
        for collection in self.prop(BASE, 'Service', 'Collections'):
            if self.prop(collection, 'Collection', 'Locked'):
                locked = True
                continue
            group = str(self.prop(collection, 'Collection', 'Label'))
            for path in self.prop(collection, 'Collection', 'Items'):
                if self.prop(path, 'Item', 'Locked'):
                    continue
                attrs = self.prop(path, 'Item', 'Attributes')
                user = str(attrs.get('UserName', attrs.get('username', attrs.get('account', ''))))
                rows[str(path)] = (str(self.prop(path, 'Item', 'Label')), ' · '.join(filter(None, (user, group))))
        self.paths = set(rows)
        if not rows:
            raise ValueError('Unlock your vault in KeePassXC.' if locked else 'No exposed entries. Check Database settings → Secret Service Integration in KeePassXC.')
        return dict(sorted(rows.items(), key=lambda row: row[1][0].casefold()))

    def secret(self, path):
        if path not in self.paths:
            raise ValueError('Unknown password entry.')
        if self.prop(path, 'Item', 'Locked'):
            raise ValueError('The vault is locked. Unlock it in KeePassXC and retry.')
        _, session = self.service.OpenSession('plain', self.db.String('', variant_level=1))
        try:
            return bytes(self.interface(path, IFACE + '.Item').GetSecret(session)[2])
        finally:
            self.interface(session, IFACE + '.Session').Close()


def copy_secret(secret, notify):
    # Foreground owner exits after 30 seconds; never clear a newer clipboard owner.
    proc = subprocess.Popen(['wl-copy', '--foreground', '--sensitive', '--type', 'text/plain;charset=utf-8'],
                            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        proc.stdin.write(secret)
        proc.stdin.close()
        try:
            code = proc.wait(timeout=0.15)
        except subprocess.TimeoutExpired:
            notify('Passwords', 'Copied for 30 seconds.')
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait(timeout=2)
        else:
            if code:
                raise ValueError('Could not copy the password.')
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    roots = [Path(__file__).resolve().parents[2], Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share')), Path.home()/'.local/src']
    for root in reversed(roots):
        folder = root/'simplepicker/python'
        if folder.is_dir():
            sys.path.insert(0, str(folder))
    from simplepicker_api import notify
    from ui import show_menu, normalize
    vault = None
    try:
        vault = Vault()
        rows = vault.entries()
        hint = '/ Search · Ctrl+J/K move · Enter copy · Ctrl+O KeePassXC'
    except Exception:
        rows = {}
        hint = 'Unlock KeePassXC or check its Secret Service group · Enter opens vault'
    labels = {path: row[0] for path, row in rows.items()}
    descriptions = {path: row[1] for path, row in rows.items()}
    if not rows:
        labels['open'] = 'Open KeePassXC'
    search = {path: normalize(label + ' ' + descriptions.get(path, '')) for path, label in labels.items()}
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'simplepicker/passwords/keys.ini'
    selected = show_menu(lambda query: [p for p, text in search.items() if all(w in text for w in normalize(query).split())],
                         labels=labels, subtitles=descriptions, title='Passwords · KeePassXC', prompt=hint,
                         width=660, height=460, default_icon='dialog-password-symbolic', auto_accept=False,
                         key_scope='passwords', keys=config if config.is_file() else Path(__file__).with_name('keys.ini'),
                         shortcuts=[('o', 'Open KeePassXC', 'open')])
    if selected == 'open':
        subprocess.Popen(['keepassxc', str(Path.home()/'.local/share/passwords/passwords.kdbx')], start_new_session=True)
    elif selected in rows:
        try:
            copy_secret(vault.secret(selected), notify)
        except Exception:
            notify('Passwords', 'Could not copy. Check that KeePassXC is unlocked and wl-copy is available.', error=True)
            return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())

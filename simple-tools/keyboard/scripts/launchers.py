"""Desktop opening shortcuts and their explicit launch targets."""
import os
from pathlib import Path
import re
import shutil
from wm_config import settings, bindings

APPS = {
 'simplepicker': 'Application launcher', 'simplebookmarks': 'Bookmarks',
 'simpleclip': 'Clipboard history', 'simplenotes': 'Notes',
 'simpleplayer': 'Music player', 'simplemail': 'Mail',
 'simpletorrent': 'Torrents', 'simplecalendar': 'Calendar',
 'simplecontacts': 'Contacts', 'simpletimer': 'Timer', 'simplegarmin': 'Garmin health dashboard',
 'simplepanel': 'System dashboard', 'simplelock': 'Lock screen',
 'simplecapture': 'Screenshot', 'simplefiles': 'File chooser',
 'simpleimage': 'Image viewer', 'simplephoto': 'Photo editor',
 'simplepdf': 'PDF reader', 'simplewallpaper': 'Wallpaper',
 'simpleinstaller': 'Install Simple apps', 'simpletag': 'Music tagging · Picard',
}
# Specific wrappers and picker modules get recognizable, searchable names.
ALIASES = [
 ('kitty-drop', 'Drop-down terminal'),
 ('kitty-lf', 'Yazi — File manager'),
 ('accounting-chooser', 'Accounting'),
 ('haadthien-invoice', 'Haad Thien invoice'),
 ('invoice-chooser', 'Invoices'),
 ('color-code-finder', 'Color picker'),
 ('ip-info', 'IP address information'),
 ('mount-all', 'Mount drives'),
 ('passwd', 'Simplepicker — Passwords (KeePassXC)'),
 ('paste-share', 'Share files'),
 ('pastebin-invite', 'Create sharing invitation'),
 ('screen-ocr', 'Copy text from screen'),
 ('screen-zoom', 'Screen magnifier'),
 ('send-device', 'Send to device'),
 ('simplefinalsetup', 'Simplefinalsetup — Cloud accounts and setup'),
 ('translat', 'Translate text'),
 ('website-update', 'Update websites'),
 ('mepo', 'Maps'),
 ('youtube --now-playing', 'YouTube — Find current song'),
 ('youtube --clipboard', 'YouTube — Open clipboard link'),
 ('youtube', 'YouTube — Search videos'),
 ('bm-add', 'Simplepicker — Add bookmark'),
 ('--bookmark-add', 'Simplepicker — Add bookmark'),
 ('logoutlaunch.sh', 'Simplepicker — Logout and power menu'),
 ('--power', 'Simplepicker — Logout and power menu'),
 ('kitty-updater', 'Package updates'),
 ('fleet-kitty', 'Newinit — Machine updates'),
 ('kitty-yazi-floating', 'Yazi — File manager'),
 ('sync-folder', 'Folder synchronization'),
 ('btop', 'System — Process monitor'),
 ('standard-replies', 'Simplepicker — Standard replies'),
 ('--dashboard', 'Simplepicker — Now playing music dashboard'),
 ('fleet-dashboard', 'Devices dashboard'),
 ('--websearch', 'Simplepicker — Web and image search'),
 ('--runner', 'Simplepicker — Command runner'),
 ('--calc', 'Simplepicker — Calculator'),
 ('--symbols', 'Simplepicker — Symbols and emoji'),
 ('--fonts', 'Simplepicker — Fonts'),
 ('--windows', 'Simplepicker — Window picker'),
 ('simple-network bt', 'Simplepicker — System Bluetooth'),
 ('simple-network', 'Simplepicker — System network'),
 ('simple-sound', 'Simplepicker — System sound'),
 ('simple-disk', 'Simplepicker — System disk space'),
 ('simple-cpu', 'Simplepicker — System CPU'),
 ('simple-memory', 'Simplepicker — System memory'),
 ('system_control', 'Simplepicker — System menu'),
 ('desktop-health', 'Simplepicker — System health'),
 ('simplecapture --record', 'Simplecapture — Screen recording'),
 ('simplecapture --menu', 'Simplecapture — Screenshot menu'),
 ('keyboard-layout', 'Keyboard layout and app shortcuts'),
 ('simple-calendar', 'Simplecalendar — Calendar'),
 ('transmission-ensure', 'Simpletorrent — Torrents'),
 ('simplepanel-config', 'Simplepanel — Edit configuration'),
 ('simplepanel --system-dashboard', 'Simplepanel — System dashboard'),
 ('helium-chat', 'Browser — Chat profile'),
 ('helium', 'Browser'),
 ('standard-replies', 'Simplepicker — Standard replies'),
 ('app-terminal', 'Terminal'),
]


def launch_rows(root=None, targets=None):
    root = Path(root) if root else Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))
    found = {}
    options = settings(root)
    for keys, command, description, target in bindings(options):
        if any(name in command for name in ('playerctl', 'simpleplayer-control.py', 'killall', 'volumenew.sh', 'mmsg dispatch', 'reload-config', 'lid-display', 'notification-activate', 'makoctl', 'mtoggle', 'focus-floating')):
            continue
        name = next((title for marker, title in ALIASES if marker in command), None)
        if name is None:
            app = next((app for app in APPS if re.search(r'(?<![\w-])'+app+r'(?![\w-])', command)), None)
            name = app.capitalize()+' — '+APPS[app] if app else description.removeprefix('Open ')
            if name == 'Kitty':
                name = 'Terminal — Kitty'
        for marker, title in options['names'].items():
            if re.search(r'(?<![\w-])'+re.escape(marker)+r'(?![\w-])', command):
                name = title
                break
        if targets is not None:
            targets.setdefault(name, target)
        found.setdefault(name, [])
        if keys not in found[name]:found[name].append(keys)
    # Include apps without a dedicated global binding, with an honest opening route.
    for app, description in APPS.items():
        if shutil.which(app) and not any(name.lower().split(' — ', 1)[0] == app for name in found):
            if targets is not None:
                targets[app.capitalize()+' — '+description] = ('argv', [app])
            found[app.capitalize()+' — '+description] = [f'No dedicated shortcut · Open {app} from your application launcher or terminal']
    if shutil.which('simplepicker'):
        found.setdefault('Simplepicker — Now playing music dashboard',
                     ['No dedicated shortcut · Run simplepicker --dashboard'])
    if targets is not None and shutil.which('simplepicker'):
        targets.setdefault('Simplepicker — Now playing music dashboard', ('argv', ['simplepicker', '--dashboard']))
    return dict(sorted(found.items(), key=lambda item: item[0].casefold()))

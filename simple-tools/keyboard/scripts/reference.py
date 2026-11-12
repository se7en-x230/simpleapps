"""Small searchable reference; common navigation follows installed overrides."""
import configparser
import os
from pathlib import Path

# app | keys | action. Capital letters mean Shift; sequences are written with spaces.
REFERENCE = '''
Simplepicker | Ctrl+A | Application launcher: app actions
Simplepicker | Ctrl+E / Ctrl+F | Calculator: edit / copy expression and result
Simplepicker | Ctrl+D / Ctrl+M | Window picker: close / move window to current workspace
Simplepicker | Ctrl+T | Font picker: edit sample
Simpleclip | Enter | Restore selected clipboard item
Simpleclip | Ctrl+D | Delete selected history entry
Simpleclip | Ctrl+P | Paste plain text
Simpleclip | g g / G | First / last result in navigation mode
Simplebookmarks | a / e / x | Add / edit / remove bookmark
Simplebookmarks | y / r / l | Copy URL / reload / open
Simplebookmarks | g / G | First / last bookmark
Simplebookmarks | Ctrl+Enter | Save bookmark dialog
Simplenotes | i / Enter | Edit selected note
Simplenotes | l / h | Preview / return to list
Simplenotes | n / N | New note / new folder
Simplenotes | p / a | New note from clipboard / append clipboard
Simplenotes | y / Y | Copy note text / file reference
Simplenotes | Ctrl+S / Ctrl+Shift+S | Save / save a separate copy
Simplenotes | Ctrl+R / R | Refresh notes / recover draft
Simplenotes | Ctrl+Enter | Save and leave editor
Simplenotes | g g / G / Ctrl+U / Ctrl+D | First / last / jump up / jump down
Simplenotes | Esc | Save and close; a failed save keeps the editor open
Simpleplayer | Enter / Shift+Enter | Shuffle play / ordered play
Simpleplayer | Space / n / p | Pause / next track / previous track
Simpleplayer | h / Alt+Left / l | Back / back / open folder
Simpleplayer | g g / G / g h | First / last / music root
Simpleplayer | 1 / 2 / 3 | Local / Radio / YouTube
Simpleplayer | Ctrl+H / Ctrl+L | Previous / next source, also while searching
Simpleplayer | f / Ctrl+R | Favourite stream / refresh library
Simpletorrent | Space / Enter | Mark torrent; Space also advances
Simpletorrent | u / a | Clear marks / add torrent
Simpletorrent | s / p | Start / pause selected torrents
Simpletorrent | x | Delete torrents AND downloaded files, after confirmation
Simpletorrent | X | Remove torrents, keep files, after confirmation
Simpletorrent | g / G | First / last torrent
Simplecontacts | n / e / x | New / edit / delete contact
Simplecontacts | s / c / b | Sync / accounts / export
Simplecontacts | h / l | Change focus
Simplecalendar | h / l / j / k | Previous day / next day / next week / previous week
Simplecalendar | H / L / J / K | Previous month / next month / next event / previous event
Simplecalendar | t / g / Home | Today
Simplecalendar | n / Ctrl+N / e / x | New event / new event / edit / delete
Simplecalendar | a / s / c | Agenda / sync / accounts
Simplecalendar | Ctrl+S / Ctrl+Shift+N | Save event / add notification
Simplegarmin | h / l / t | Previous day / next day / today
Simplegarmin | r / c | Refresh / connection settings
Simplegarmin | j / k / 1–6 | Change section / change section / select section
Simpletimer | 1–5 / h / l / j / k | Select or cycle timer mode
Simpletimer | Space / r / i | Start or pause / reset / edit duration
Simpletimer | m / f | Mute meditation bells / finish meditation
Simpletimer | Esc / q / Q | Hide / hide / quit with confirmation
Simplecapture | r / f / c / a | Menu: region / full desktop / quick region / quick desktop
Simplemail | n / r / R | Compose / reply / refresh
Simplemail | s / t / a | Switch folder / Trash / accounts
Simplemail | o / i | Message resources
Simplemail | Space / m | Select message / mark read or unread
Simplemail | x / u / E | Trash / restore / empty Trash
Simplemail | h / l / g g / G | List / reader / first message / last message
Simplemail | Ctrl+U / Ctrl+D | Scroll half-page
Simplemail | Ctrl+Shift+Enter | Composer: send message
Simplemail | Ctrl+E / Ctrl+O | Composer: external editor / attach file
Simplemail | Ctrl+[ / quick j k | Composer: leave insert mode
Simplemail | Esc | Composer: return to inbox
Simplefiles | h / l | Parent folder / enter folder or choose file
Simplefiles | g g / G / Ctrl+U / Ctrl+D | First / last / ten entries up / ten entries down
Simplefiles | Ctrl+O / Ctrl+I | Back / forward
Simplefiles | Space / . | Mark files / show hidden files
Simplefiles | Ctrl+L / m d / i | Edit location / create folder / edit save filename
Simplefiles | g h / g d / g D / g m / g c / g / | Home / Downloads / Documents / Music / config / root
Simpleimage | n / Space / p / Backspace | Next / next / previous / previous image
Simpleimage | h / j / k / l | Pan image or move thumbnails
Simpleimage | + / - / = / 1 | Zoom in / out / fit / actual pixels
Simpleimage | Enter / z / m | Grid or open thumbnail / thumbnail size / mark
Simpleimage | x / Delete / Ctrl+P | Trash / Trash / print
Simpleimage | e / r / R / X | Edit in Simplephoto / reload / rotate / mirror
Simpleimage | f / b / s | Fullscreen / bars / slideshow
Simpleimage | y / Ctrl+X / Y / Ctrl+C | Copy paths / paths / image / image
Simpleimage | i / o / ? | Information / open / help
Simplephoto | j / k / h / l / Shift+H / Shift+L | Select adjustment / change value; Shift uses larger steps
Simplephoto | g / G / 0 / r | First / last adjustment / reset selected / reset all
Simplephoto | v / b / c | Compare original / blur brush / crop
Simplephoto | t / T / x / X | Rotate right / left / mirror horizontally / vertically
Simplephoto | s / Ctrl+S / o / n / ] | Save copy / save copy / open / next / next photo
Simplephoto | h j k l / Shift+movement / Ctrl+movement | Crop: move / resize / pixel precision
Simplephoto | f / z / Z / + / - | Crop: fast steps / shrink / grow / grow / shrink
Simplephoto | Enter / Esc | Crop: return to adjustments
Simplephoto | [ / ] / j / k / h / l | Brush: size / size / size / size / strength / strength
Simplephoto | m / u / Ctrl+Z / r | Brush: overlay / undo / undo / clear mask
Simplephoto | b / Enter / Esc | Brush: return to adjustments
Simplepdf | h / j / k / l / d / u | Scroll / half-page down or up
Simplepdf | Ctrl+D / Ctrl+U / Space / Backspace | Next / previous / next / previous page
Simplepdf | g g / G / number then G / : | First / last / jump to page / page prompt
Simplepdf | J / K / - / + / ; w / ; p | Zoom out / in / out / in / fit width / fit page
Simplepdf | / / n / N | Search / next match / previous match
Simplepdf | R / i / r / p | Rotate / invert / reload / print
Simplepdf | ; b / ; l / t / f | Add bookmark / list bookmarks / contents / links
Simplepdf | o / y / ? | Open / copy page text / help
Simplepdf | ; t / ; e / ; c / ; o | Extract text / extract pages / compress / OCR
Simplepanel | h / l | Time converter: move between fields or hours/minutes
Simplepanel | j / - / k / + | Time converter: decrease / decrease / increase / increase unit
Simplepanel | Enter / Esc | Time converter: next field / return to system controls
Simplelock | Enter / Esc | Password: unlock / clear password
Simpleinstaller | Space / j / k / a / Enter / q | Select app / down / up / toggle all / continue / cancel
Simplewallpaper | Shared picker navigation | Configuration menus use Simplepicker
'''

DEFAULTS = {
    'up': ('Up,k,<Control>k', 'Previous result; Ctrl+K keeps search focused'),
    'down': ('Down,j,<Control>j', 'Next result; Ctrl+J keeps search focused'),
    'left': ('Left,h,<Control>h', 'Left or back where supported'),
    'right': ('Right,l,<Control>l', 'Right or open where supported'),
    'activate': ('Return,KP_Enter', 'Activate selected result'),
    'cancel': ('Escape', 'Close search/list window; editors keep their save/cancel handling'),
    'page_up': ('Page_Up,<Control>u', 'Page up where supported'),
    'page_down': ('Page_Down,<Control>d', 'Page down where supported'),
}


def config(path):
    result = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        result.read(path)
    except configparser.Error:
        pass
    return result


def app_rows(root=None):
    root = Path(root) if root else Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))
    common = config(root/'simple/keys.ini')
    rows = ['Shared | '+common.get('navigation', action, fallback=value)+' | '+description
            for action, (value, description) in DEFAULTS.items()]
    rows += ['Shared | Ctrl+Enter | Leave search for navigation',
             'Shared | / | Return from navigation to search',
             'Shared | q | Close outside text entry',
             'Shared | Tab / Shift+Tab | Next / previous control',
             'Shared | Letter shortcuts | Use navigation mode first; letters type normally in search',
             'Shared | Configuration | ~/.config/simple/keys.ini; per-app ~/.config/simplexy/keys.ini']
    rows += [line.strip() for line in REFERENCE.splitlines() if line.strip()]
    # Show configured overrides separately, avoiding a claim that the static
    # app reference is authoritative when the user has customized an action.
    for path in sorted(root.glob('simple*/keys.ini')):
        if path.parent.name == 'simple':
            continue
        keys = config(path)
        for section in keys.sections():
            for action, value in keys.items(section):
                rows.append(f'{path.parent.name} configured | {value or "disabled"} | {section}: {action}')
    return rows

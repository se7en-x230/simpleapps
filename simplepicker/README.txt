Simplepicker — native C / GTK4 edition
====================================
Status: active native edition. ~/.local/bin/simplepicker points to the native
binary; existing shortcuts and personal tools use it. The retired Python
application has been removed. The separate Python scripting adapter remains.

Build and install for your user
-------------------------------
  cd ~/.local/src/simplepicker
  make
  ./simplepicker-native --apps
  make install PREFIX="$HOME/.local"

No sudo is needed. Installation adds ~/.local/bin/simplepicker-native and
resources under ~/.local/share/simplepicker. It preserves personal config and
histories. The active simplepicker symlink follows this binary, so make install
updates the launcher without editing shortcuts. The Python scripting adapter
was installed during activation; make install alone does not update that adapter.

  make clean
  make
  make install PREFIX="$HOME/.local"

Avoid parallel "make -j clean install": clean can race the build. Plain
"make clean install PREFIX=..." works, but separate commands are clearer.
PROGRAM defaults to simplepicker-native; simplepicker is a symlink to it. DESTDIR is supported for package/staging builds.

See ../docs/portability.md for Debian 13 and Arch dependency commands.
Run make check-deps before building on a new host.

Requires: a C compiler, make, pkg-config, GTK4 >= 4.12, gtk4-layer-shell >= 1.0, GIO and json-c
headers/libraries. The TOML parser is vendored, so builds need no downloads.
The binary dynamically links GTK and other system libraries.

Built-in modes
--------------
  --apps          Desktop-file apps, icons, usage ranking, Ctrl+A app actions.
  --runner        PATH executables and explicitly entered shell commands.
  --calc          qalc; Enter copies, Ctrl+E edits, Ctrl+F copies expression/result.
  --clipboard     cliphist; asynchronous text/image previews, Ctrl+D deletes,
                  Enter restores local file lists for pasting as attachments,
                  video file entries show Video + filename and a still frame;
                  type video to filter. Preview requires the original local file.
                  Ctrl+P copies text-only and pastes into the prior application.
  --bookmarks     Bookmark labels/URLs, usage history, Ctrl+E opens draft editor.
  --bookmark-add  Add an HTTP(S) URL from the clipboard.
  --bookmark-edit Validated draft editing with conflict detection and backup.
  --websearch     Configured engines and prefixes.
  --windows       Focus; Ctrl+D close; Ctrl+M move to captured workspace.
  --symbols       Unicode symbols/emoji search and copy.
  --fonts         Font/sample previews, Ctrl+T edits sample, Enter copies name.
  --power         CSS power row, configured icons/commands/keys, toggle to close.

The CLI accepts -m/--provider and the old menus: prefix as well.
Applications are discovered through GIO desktop entries. Runner scans PATH.
Both discover entries per invocation; no launcher daemon or persistent list
cache has been added. History JSON formats and lock names match the Python
version so both versions can use the same personal data.

Dmenu interface
---------------
  printf 'One\nTwo\n' | ./simplepicker-native -d -p Choose
  ./simplepicker-native -I -p 'Enter text' </dev/null
  ./simplepicker-native -x -p Password </dev/null
  ./simplepicker-native -d --input choices.txt
  ./simplepicker-native --search cafe < choices.txt

Enter prints the selected value to stdout. Escape/outside-click returns 1;
errors return 2. Up/Down, Ctrl+J/K and PageUp/PageDown navigate. Search ignores
case and accents; input order is retained; at most 200 results are displayed.
--query, --selected-row, --width, --height, -l, --icon and --theme are supported.
Use --help for the full list. No shell is used by the dmenu interface.

Configuration and resources
---------------------------
Reads the existing ~/.config/simplepicker/config.toml and CSS overrides.
It does not copy your personal settings into the source tree or overwrite them.
--config and SIMPLEPICKER_CONFIG select an alternate config.
--theme and SIMPLEPICKER_THEME select alternative CSS.
Without a CSS override, GTK styling follows the system theme.
Each power action supports label/key/enabled/command/icon; icon may be a theme
name or a file relative to the config directory. Missing override files fail
validation. Desktop adapters cover Mango, Sway, Hyprland legacy/Lua, and hooks.

  ./simplepicker-native --check-config
  ./simplepicker-native --doctor

Data normally remains in $XDG_DATA_HOME/simplepicker (default ~/.local/share/
simplepicker). SIMPLEPICKER_DATA_DIR allows an isolated test data directory.
SIMPLEPICKER_ASSETS overrides the bundled resource location for development.
A copy of websearch.json is bundled as fallback when personal config is absent.

Provider helpers are invoked when needed: qalc, cliphist, wl-clipboard, file,
fontconfig, xdg-open, ffmpeg (video clipboard previews), and compositor IPC tools. Clipboard recording remains
session/autostart configuration; the launcher does not start another recorder.
Power commands and your bookmark editor/terminal are configured argv arrays.
Install a system wtype for paste simulation. The build does not install a
prebuilt architecture-specific wtype helper. The picker builds from source on the host.

Personal scripted menus
----------------------
The built-in modes and GUI are C. Your disk/music/system tools remain scripts.
python/ui.py implements the existing show_menu interface over a small JSON-line
pipe to the native GUI; it does not import GTK. Existing callbacks, IDs, labels,
icons, previews, custom shortcuts and keep-open selections are supported.

The installed tools already use this adapter. To test a source build explicitly:
  ./run-tool system-hub
  ./run-tool diskfree

run-tool opts child Python processes into the adapter using a local
sitecustomize module. It applies only to that command and its children; nothing
is written into your shell config. run-script.py also supports standalone Python
scripts. Native built-in modes do not use this bridge or require Python.
The bridge is a compatibility layer; -d remains the simple public script API.

Validation
----------
  make check
  make tests/driver tests/desktop-check
  python3 tests/desktop.py
  python3 tests/editor.py
  python3 tests/gui.py

GUI tests require the user's Wayland session. They use isolated config/data,
fake desktop entries and fake clipboard/window/power commands. The image
fixture exposes only system icon/MIME/loader resources to the isolated session.
ASan/UBSan were run against the same GUI/provider/bridge tests, with leak
checking disabled for system GTK/driver caches. All passed.
The desktop test compares native command construction against the installed
Python implementation for Mango, Sway, Hyprland legacy and Hyprland Lua.

Startup results and measurement limits: benchmark-report.txt.
benchmark.py uses tests/python-probe.py to instrument the installed Python
version; use --benchmark for native auto-close timing on another machine.
Measurements cover warm process start to GTK after-paint, not physical display
latency. No selections/actions are executed during these timing probes.

Third-party material
--------------------
vendor/tomlc99: MIT; see vendor/LICENSE.tomlc99 and vendor/README.txt.
Unicode annotations: assets/Unicode-3.0.txt.
wtype helper: assets/wtype-LICENSE.

Dashboard
---------
simplepicker --dashboard opens a native music and system dashboard.
Calling it again toggles it closed; Escape and clicking outside also close it.
Shows MPRIS now-playing metadata and large artwork, clock, month calendar,
local IPv4 addresses, NetworkManager connection name, hostname, uptime,
home filesystem free space, and batteries when available. Updates run only
while open. Artwork is reused until the track or artwork URI changes.
Local and embedded artwork require no extra programs; HTTP artwork uses curl.
There are no music transport controls.

The dashboard follows GTK system colors and loads the usual Simplepicker CSS.
Optional dashboard/style.css beside config.toml overrides dashboard styling.
Selectors: .dashboard-panel, .dash-title, .dash-art, .dash-clock,
.dash-info, .dash-muted, .dash-status.
Example: .dashboard-panel { background: alpha(@theme_bg_color, 0.96); }

Dashboard visualizer and artwork
-------------------------------
Optional cava runs privately while the dashboard is open, using the default
PulseAudio/PipeWire-Pulse output monitor. Its 32 raw bars render natively at
30 fps; closing the dashboard stops and reaps its child. If cava is absent,
the visualizer hides. No background daemon or persistent Cava config changes.
Put a portrait illustration at dashboard/images/monk.png beside config.toml to display it
next to the calendar. Replace that image or edit dashboard/style.css to customize.
System details include OS, host, kernel, CPU, memory, load averages, uptime,
free home-disk space, network addresses, and power status.

Fullscreen screensaver
----------------------
--screensaver opens an opaque fullscreen dashboard; repeated starts are
idempotent. Mouse movement, a click, or any key dismisses it. --screensaver-stop
closes only this mode, never the popup. This is a screensaver, not a session lock.

The optional ~/.config/simplepicker/dashboard/scripts/idle watcher uses swayidle (Wayland
idle notifications) and Python 3.11+ tomllib. Settings in config.toml:
[screensaver]
enabled = true
idle_seconds = 160

Settings reload automatically. Run the watcher once at session startup; --restart
restarts it, --stop stops it, --check validates settings. One watcher per runtime
directory; resume closes the screensaver. Invalid edits keep the last valid
settings. Cava and dashboard sampling run only while the view is visible.
The popup remains simplepicker --dashboard. Fullscreen CSS uses .screensaver.

Screensaver backdrop and layout
------------------------------
Fullscreen mode captures the chosen output once with optional grim, before
showing the view. GTK renders the in-memory texture with blur, a light tint and
a 450 ms fade-in. No compositor blur settings or screenshot files are used.
This is a static desktop snapshot; it does not refresh while visible. Compositors
must support grim's Wayland capture protocol; without it, a plain backdrop is
used. Popup mode does not capture the desktop. Fullscreen mode has larger artwork,
aligned information panels, and 64 Cava bars spanning the bottom. The popup keeps
its 32-bar layout. CSS remains customizable via dashboard/style.css.

Optional dashboard/images/album-idle.png beside config.toml fills the artwork area when no
player is active, a player is stopped, or artwork is unavailable. Paused tracks
keep their album art. The calendar and clock have cards in both views; fullscreen
card gaps show the desktop snapshot with a softer 11-pixel GTK blur.

Calendar annotations: shared with the Simple family. Build alongside
../simple-common/calendar.h; configuration and offline dates are in
~/.config/simple/calendar.ini. See ~/.config/simple/calendar-README.txt.

Calendar keys: h/l move one day; k/j move one week; Page Up/Down move one
month; Home returns to today. The calendar is focused when the dashboard
opens. Escape still closes it; fullscreen screensaver input still dismisses
the screensaver. Movement uses simple/keys.ini, then simplepicker/keys.ini
and simplepicker/dashboard/keys.ini overrides. See simple/navigation.txt.

Idle chant: the optional ~/.config/simple/idle-audio.py helper loops the shared
audio/namo-tassa.mp3 only while this view is open and no other audio/music plays.
One shared playback lock prevents duplicate audio across views/outputs. Playback
stops on close/unlock, parent exit, or other audio starting. No MPRIS registration
is made for the chant, so it does not replace track metadata or the idle layout.
Requires mpv, pactl, and Python GObject; failures leave the UI/lock functional.

## Shared base and portable installation

Uses the shared C/GTK4 base in `simple-common`. Python UI code calls the same native library through a thin adapter. Shared theme and keyboard adapters replace separate implementations; app-specific commands and content remain local.

Requires Linux and Python 3.11+ for the source installer. Building the shared base requires a C compiler, make, pkg-config and GTK4 >= 4.12 development files. Install dependencies using your distribution’s package manager; package names can differ.

- Libraries / pkg-config modules: `gtk4 >= 4.12`, `gtk4-layer-shell-0`, `gio-unix-2.0`, `json-c`.
- Python imports: none beyond the standard library for the base app.
- Required commands: `cc`, `make`, `pkg-config`, `python3`, `xdg-open`, `wl-copy`.
- Optional Calculator: `qalc`.
- Desktop requirements: GTK window; Wayland layer-shell when available.

From the suite checkout (no pacman or distro detection on this path):

```sh
./install --dependencies simplepicker
./install --check simplepicker
./install --no-packages --install simplepicker
```

To build a relocatable staging tree without changing your installation:

```sh
./install --install simplepicker --stage "$PWD/package-simplepicker"
```

Keep `simple-common` alongside the app sources. Staged files are under `.local/`; move that prefix as a unit so executables, shared libraries and resources stay together. Individual C Makefiles also accept `PREFIX`/`DESTDIR` where documented. See [portable builds](../docs/portability.md) for Debian/Arch dependency examples and limitations.

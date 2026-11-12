Simplepanel — small, configurable Wayland status bar
================================================
Status: installed as the active Mango panel. Noctalia autostart is disabled;
~/.config/noctalia/ is preserved. Notifications are deferred.

The existing Simplepicker dashboard already provides album art, media controls,
network details, CPU model/load, memory, disk, and battery. Simplepanel keeps
only the compact status line; no tray, plugin engine or control-center UI.

Displays:
  occupied/active/urgent Mango tags and focused-window app/title
  current MPRIS artist/album/title and playback state
  thin playback progress bar below the song text when duration is available
  clock in the existing format: %a %d  %H:%M
  network receive/transmit speed on the default IPv4 route
  default audio output volume/mute
  optional custom modules, including a personal investment module
  first reachable paired KDE Connect device's charge/charging state

Configuration and custom modules
--------------------------------
Keep the existing INI file at ~/.config/simplepanel/config.ini. No new config
parser or service is needed. Restart with simplepanel-session restart after edits.
A minimal portable example is shipped in examples/config.ini (installed under
~/.local/share/simplepanel/examples/).

  [panel]
  environment=mango

  [layout]
  left=workspaces;window-title;
  center=music;clock;
  right=network;volume;invest;battery;phone;

  [custom.invest]
  command=~/.config/simplepanel/scripts/invest
  interval=3600
  timeout=10
  max_chars=24

Layout lists use semicolons, including an optional trailing semicolon. Empty
lists hide that section. Each module may appear once across all three sections.
Builtins: workspaces, window-title, music (including optional Cava), clock,
network, volume, battery, phone. Omitted modules do not start their polling;
volume_osd can still independently enable audio events. Legacy cava/phone/clock
switches remain supported. Old layouts and panel.invest=true still work; the
legacy investment switch now creates a custom subprocess module.

Environment choices: auto, mango, hyprland, sway, generic. Auto checks the current
session variables; generic is for other Wayland window managers with layer-shell.
Only Mango currently has built-in workspace and focused-title integration.
Other choices run the common modules and omit those two widgets; they do NOT
contact Mango sockets. Hyprland/Sway workspace adapters are not yet implemented.
Their layer-shell display support is upstream-supported but has not been tested
on this machine. KDE/GNOME are outside this project's supported scope. A normal
GTK window remains available through --preview for development, not as a desktop
panel replacement. Layer-shell is required for the normal docked panel.

Each [custom.NAME] defines a command and optional interval (seconds, 1–86400,
default 60), timeout (seconds, 1–300, default 5), max_chars (1–200, default 24),
and on_click. Names may contain letters, numbers, hyphens, and underscores;
builtin names are reserved. At most 32 custom modules can be defined. Only names
included in the layout are started. Missing commands, unknown layout names,
duplicate placement, and invalid numeric settings fail --check before launch.

Commands run through /bin/sh -c, as your user. Use executable scripts for anything
more involved than one command. They receive SIMPLEPANEL_CONFIG and
SIMPLEPANEL_ENVIRONMENT. The first stdout line becomes plain label text; remaining
lines become a plain tooltip. No markup or JSON parser is required. Output is
limited to 4096 bytes; stderr is discarded. A failed poll keeps the previous value
and sets an explanatory tooltip. Polls never overlap. Timeouts and panel shutdown
kill the command's process group, including ordinary child processes.

Optional on_click commands are asynchronous and independently limited to one
running action per module, with the same timeout/output limits. Use short actions;
a long-running GUI should instead be started through its own service/launcher.
Without on_click, clicking a custom module opens the existing system dashboard.
Demo previews show module names and never execute custom commands.

The optional examples/invest script calls simplepanel --market-summary. This
short-lived helper uses the same [markets] settings and hourly disk cache as the
dashboard; it exits after printing the prices. The running panel no longer polls
market files or contains investment-specific widgets. New installs do not enable
investment by default. No embedded Python/browser, runtime plugin loader, or
persistent module daemon has been added.

Checks:
  make check                         # config + market-cache regression tests
  python3 tests/check-modules.py --runtime  # GTK display needed; no visible window

Architecture:
  C, GTK4 + gtk4-layer-shell, GLib/GIO, json-c, libpulse/glib integration.
  These development/runtime libraries already exist on this machine.
  Direct Mango Unix socket subscriptions and Pulse audio events.
  Direct MPRIS/KDE Connect D-Bus calls; no playerctl, mmsg, wpctl or network
  command polling in the panel. Noctalia is not a dependency.
  Network counters: kernel sysfs once per second; music discovery every 5s,
  phone status every 30s. Bounded asynchronous D-Bus calls.
  Optional external helpers: configured custom commands,
  and Cava. Cava is off by default. Missing helpers do not close the panel.
  Cairo renderer avoids allocating a large GPU rendering context.

Build/check:
  make
  ./simplepanel --config ./config.ini --check

Safe live preview (bottom of the screen; closes in 30s; reserves no space):
  ./simplepanel --config ./config.ini --preview-layer --duration 30
Normal-window preview (Esc or q closes):
  ./simplepanel --config ./config.ini --preview
Synthetic preview without contacting services:
  ./simplepanel --config ./config.ini --demo --duration 15
Optional Cava version:
  ./simplepanel --config ./config-cava.ini --preview-layer --duration 30

Actual top panel (do not launch over another top panel):
  ./simplepanel --config ./config.ini
The default config location is ~/.config/simplepanel/config.ini.
A blank monitor uses the first GDK output. A fixed monitor can be configured.
Click tags to switch workspaces. Click music/date for the media/calendar
dashboard; click anywhere on the right for the system information dashboard.
Optional volume_osd=true provides a simple volume/mute OSD. It is off while
Noctalia still owns that role. Simplepanel does not own or display notifications.

Measurements on this desktop (short live tests, not a general benchmark):
  text-only: ~21 MiB proportional memory; ~0.5% of one CPU core
  with Cava: ~26 MiB combined proportional memory; ~7% of one core at the
             measured moment, largely visualization activity
  native executable: ~60 KiB; shared libraries account for most memory
See measurements-minimal.json and measurements.json for the samples. RSS is
larger because it counts shared library pages in full. Source/build size is
not a claim about total installed library footprint.

Known limits before replacing Noctalia:
  one selected output; no monitor hotplug reconfiguration yet
  workspace/title integration currently requires Mango's JSON IPC protocol
  auto network selection uses IPv4 default routes (set interface explicitly
  for IPv6-only or non-default traffic); no sum of VPN/bridge interfaces
  phone report uses the first reachable paired device
  no notification daemon/history or tray implementation
  volume OSD has compiled successfully but has not been interactively tested
  source installed at ~/.local/src/simplepanel and registered with Newinit
  rebuilds, backups, sync and desktop-check dependency/config validation

Tests performed: warnings-as-errors C build, config/parser check, live desktop
feeds, live normal-window preview, live Wayland bottom-layer preview, Cava
process lifecycle, clean timed exit, and resource samples. Noctalia remained
running throughout. A pre-existing GTK portal-inhibit warning appeared; no
inhibition is used or requested by this panel.

Installed setup: ~/.config/simplepanel/config.ini (Cava + volume OSD enabled).
Super+Ctrl+T edits the config. Run simplepanel-session restart to apply edits.
Session launcher prevents duplicate panels. Logs: ~/.local/state/simplepanel/panel.log.
Working source for development: ./simplepanel.
Deploy source changes to ~/.local/src/simplepanel too before future rebuilds.

System dashboard: simplepanel --system-dashboard (Esc/Q closes; rerun toggles).
Also opened by worldclock.sh; worldclock.sh --text keeps its plain text output.
World clocks: Koh Tao, Sydney, Berlin, Los Angeles, using system time-zone data.
Live CPU, memory, root/home disk space, interface addresses/traffic, audio,
Bluetooth, battery, uptime, phone charging; investment prices use the panel cache.
Runs only while open; no extra daemon, package or polling process.
Shares ~/.config/simplepicker/dashboard/style.css with the media dashboard.
Panel sections/click areas have transparent gaps and no hover overlay on music.

System graphs: CPU (gold, 0–100%), network receive/send (blue/gold, automatic
scale), memory usage (green), root disk usage (purple). Histories contain up to
60 one-second samples, collected only while the dashboard is open.

Volume OSD: vertical level meter, speaker/mute icon and percentage at center right.
Fades in/out over 180 ms and hides 1.5 seconds after the last volume change.
Mango anim.conf disables compositor movement for the simplepanel-osd layer;
the OSD uses its own crossfade. The panel itself retains its existing animation.

Super+G: system dashboard; Super+Ctrl+G: btop.
The two dashboards are normal floating windows; other apps remain interactive.
simplepanel-session restart detaches and returns to the terminal.
Mako owns notifications; song-notify is in ~/.config/mango/scripts/.

Laptop battery in the bar: detected automatically from system power supplies,
refreshed every 15 seconds and hidden when absent. Shows each battery percentage
with ⚡ while charging, like the phone indicator. Hover for battery names and
status. Peripheral batteries are excluded; phone charge remains separate.

Volume: left-click opens Sound; right-click opens Bluetooth. Scroll over the bar
volume for 5% steps (maximum 100%); middle-click toggles mute.
Sound and Bluetooth include shortcuts to switch to each other.
Network, Volume and Bluetooth dashboard cards open their controls.
Global shortcuts: Super+Ctrl+W network, Super+Ctrl+B Bluetooth, Super+Ctrl+S
Sound controls.

Investment cards show Tether Gold (XAUT) and BTC in THB with cached 24-hour
percentage changes. Hover shows the quote timestamp; unavailable changes are
labelled rather than estimated. Quotes share the existing hourly request.

Phone charging estimates
------------------------
The panel estimates net charging speed from KDE Connect battery percentages.
⚡… gathers readings, ⚡↓ is slow, ⚡ is normal, ⚡↑ is rapid, ⚡✓ is full.
Hover for the measured percentage change and explanation. These are estimates
of battery gain, not the phone's charging-mode label or charger wattage.
A first estimate appears after about one minute, including a flat reading.
The tooltip marks the first five minutes as provisional. Each new reading
refines the estimate using up to ten minutes of history. Integer percentages
can initially give a misleading speed, so the icon may change. Slow is below
0.3 percentage points/minute, rapid is at least 0.8, normal is between them.
Unplugging, device changes, missing readings and gaps over two minutes reset
the estimate. Near-full batteries, heat and phone use can reduce the rate.
The estimator uses memory only; restarting the panel starts a fresh history.
Thresholds and timing are in phone-charge.h. No phone-side app is needed.

The system dashboard Phone card shows battery percentage and charging status on
one line. It does not calculate or display charging-speed estimates.

System dashboard appearance inherits simple/theme.css, including simple_heading.
Optional per-dashboard overrides belong in simplepanel/dashboard.css; legacy
simplepicker/dashboard/style.css applies to the older music/dashboard views.

System facts: fastfetch runs once per dashboard opening with its user config
disabled and JSON output, asynchronously with a five-second timeout. OS, host,
kernel, init, WM/protocol, GPU, displays and package count come from that result.
Shell is the user's configured login shell (a GUI has no enclosing terminal).
Missing facts are marked unavailable. Volume and Bluetooth are compact stacked
cards alongside the network graph; keyboard navigation follows their positions.

Configurable clocks and quotes
-----------------------------
Super+G includes a timezone converter beneath the clocks, defaulting to Thailand
(Asia/Bangkok) → Germany (Europe/Berlin). Both dropdowns are searchable. Enter a
date (YYYY-MM-DD) and 24-hour time (HH:MM) in the source timezone. Thailand and
Germany appear first, followed by configured cities and system timezones.
Date/time fields use direct typing and keyboard adjustment, without picker buttons.
Results update immediately, including destination date and UTC offset. The
result is shown as a compact source-time → destination-time line with a subtle
highlight and date/day-change information alongside it. The swap
button reverses the zones while preserving the instant. Inputs start at the current
Thailand time. Timezone rules apply for the date;
invalid dates and nonexistent local times during daylight-saving jumps are rejected.
During a repeated local hour, GLib selects the standard-time occurrence.
Text fields retain direct typing; timezone search popovers use their
normal keyboard controls.
The dashboard opens focused on the source timezone. Date/time fields do not
automatically select text; selections clear when leaving a field. h/l moves between converter controls
and between hours/minutes. j/k and -/+ decrease/increase the selected time unit,
or one day in the date field; crossing midnight updates the date. Enter moves to
the next field. Tab moves normally; Esc returns to CPU, then Esc closes. From
the CPU/memory/disk row, k/Up returns to the converter. Dropdowns use j/k to select
zones; open their search to type normally. Now has been removed. Section order is
system details, markets, world clocks, converter, then system cards.
The compact three-column system grid fits the desktop screen. System details
can be collapsed and start collapsed on shorter screens; graph/control shortcuts
remain available through card tooltips. Remind opens a native calendar draft for
the selected future instant, with a notification at the event start. Review its
title and save to sync. Android calendar sync and notifications must be enabled;
this is a calendar notification, not an Android Clock alarm. No event is saved
merely by opening the draft. Times are converted to the calendar's local timezone.

See ../docs/simplepanel.md for [dashboard], [markets], and panel clock settings.
Defaults retain the original four cities, XAUT/BTC and THB. Market fetching is now standalone (curl), with configuration-specific caches.

## Shared base and portable installation

Uses the shared C/GTK4 base in `simple-common`. Python UI code calls the same native library through a thin adapter. Shared theme and keyboard adapters replace separate implementations; app-specific commands and content remain local.

Requires Linux and Python 3.11+ for the source installer. Building the shared base requires a C compiler, make, pkg-config and GTK4 >= 4.12 development files. Install dependencies using your distribution’s package manager; package names can differ.

- Libraries / pkg-config modules: `gtk4 >= 4.12`, `json-c`, `gtk4-layer-shell-0`, `gio-unix-2.0`, `libpulse-mainloop-glib`.
- Python imports: none beyond the standard library for the base app.
- Required commands: `cc`, `make`, `pkg-config`, `python3`, `fastfetch`, `curl`.
- Optional Panel audio visualization: `cava`.
- Desktop requirements: Panel: Wayland layer-shell; workspace/title integration: Mango. Dashboard: normal GTK window..

From the suite checkout (no pacman or distro detection on this path):

```sh
./install --dependencies simplepanel
./install --check simplepanel
./install --no-packages --install simplepanel
```

To build a relocatable staging tree without changing your installation:

```sh
./install --install simplepanel --stage "$PWD/package-simplepanel"
```

Keep `simple-common` alongside the app sources. Staged files are under `.local/`; move that prefix as a unit so executables, shared libraries and resources stay together. Individual C Makefiles also accept `PREFIX`/`DESTDIR` where documented. See [portable builds](../docs/portability.md) for Debian/Arch dependency examples and limitations.

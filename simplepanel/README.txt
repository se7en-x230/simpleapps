Simplepanel — small, fixed-layout Mango status bar
================================================
Status: installed as the active Mango panel. Noctalia autostart is disabled;
~/.config/noctalia/ is preserved. Notifications are deferred.

The existing Simplepicker dashboard already provides album art, media controls,
network details, CPU model/load, memory, disk, and battery. Simplepanel keeps
only the compact status line; no tray, plugin engine or control-center UI.

Displays:
  occupied/active/urgent Mango tags and focused-window app/title
  current MPRIS artist/title and playback state
  clock in the existing format: %a %d  %H:%M
  network receive/transmit speed on the default IPv4 route
  default audio output volume/mute
  existing invest.sh output, refreshed hourly
  first reachable paired KDE Connect device's charge/charging state

Architecture:
  C, GTK4 + gtk4-layer-shell, GLib/GIO, json-c, libpulse/glib integration.
  These development/runtime libraries already exist on this machine.
  Direct Mango Unix socket subscriptions and Pulse audio events.
  Direct MPRIS/KDE Connect D-Bus calls; no playerctl, mmsg, wpctl or network
  command polling in the panel. Noctalia is not a dependency.
  Network counters: kernel sysfs once per second; music discovery every 5s,
  phone status every 30s. Bounded asynchronous D-Bus calls.
  Optional external helpers: existing invest.sh (curl/jq inside that script),
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
  requires Mango's current JSON IPC protocol
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

The system dashboard Phone card shares the panel charging-speed estimate, showing
slow/normal/rapid and net percentage points per minute. A session-local snapshot
is accepted only for the same device, level and charging state, for up to 90 seconds.
Without a fresh snapshot the dashboard collects its own readings.

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
See ../docs/simplepanel.md for [dashboard], [markets], and panel clock settings.
Defaults retain the original four cities, XAUT/BTC and THB. Market fetching is now standalone (curl), with configuration-specific caches.

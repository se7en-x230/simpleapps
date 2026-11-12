Native C/GTK frontend
---------------------
World-clock reminders: `simple-calendar --remind-at 2026-11-10T14:00:00+07:00`
opens an editable event draft at the given instant, converted to the calendar's
local timezone, with a 15-minute duration and an At start notification. Nothing
is saved until Add event / Ctrl+S. An existing editor is preserved. After saving
and syncing, Android can notify through the same calendar account with calendar
sync and notifications enabled; KDE Connect and shared Wi-Fi are not required.

The window is compiled C/GTK4. Shared frontend source: ../simple-common/organizer.c, built separately by each app Makefile. Native executable: ~/.local/bin/simplecalendar-native. Python remains the provider/storage worker. Both frontends invoke ../simple-common/organizer-helper.py using JSON on stdin/stdout; adapters are bridge.py. Future Google sign-ins share google_oauth.py; existing tokens and caches retain their formats and locations. Calendar and Contacts keep separate permission grants.

Newinit setup-runtime.py builds and installs the native binary locally. Sources and configuration sync; compiled binaries, account tokens and personal caches do not. Legacy ui.py is retained only as reference and is not launched.

# Dashboard calendar

Left-click the date in SimplePanel or launch SimpleCalendar from the app menu. Browse the month and selected-day/30-day agenda. Add, edit or remove single events with reminders; multi-day events are supported. Edits preserve event UID and other metadata. Repeating series and invitations are managed in the provider. Both dashboards only display/browse cached events and local date layers. Full-moon popups include published nearby party dates.

Connect launches a terminal wizard. For Google, enable the CalDAV API in a Google Cloud project, configure OAuth consent for your account, and download a Desktop application OAuth client JSON. Supply its local path and your calendar ID to the wizard, then authorize in the browser. See https://developers.google.com/workspace/calendar/caldav/v2/guide and https://vdirsyncer.pimutils.org/en/stable/config.html . A Google OAuth app left in Testing may require renewed authorization; follow Google's current consent-screen guidance.

A generic HTTPS CalDAV collection is supported for Disroot and other providers. Existing accounts are not automatically migrated. Private credentials and calendars are stored under ~/.local/share/simple-calendar with private permissions, independently on each device. They are not part of dotfile synchronization.

The supervised simple-calendar service checks reminders every 15 seconds and syncs every five minutes. Sync in the editor updates immediately. Offline changes remain pending. Conflicting edits stop sync for manual resolution instead of overwriting data. Sync details shows errors. Deleted local files have a recovery copy in the private trash folder. Recurring events are displayed; manage recurring-series edits and deletion in the provider. The sync engine blocks emptying a whole calendar; remove its final event in the provider and resolve the empty-calendar safeguard explicitly if encountered.

Code: ~/.local/src/simplecalendar; launcher: ~/.local/bin/simple-calendar. Runtime: ~/.local/share/simple-calendar-runtime. Newinit installs the Python runtime and supervises the service. Calendar cache: ~/.cache/simple-calendar/events.ini. No calendar account is connected by installation.

Appearance and keys
-------------------
Global theme: ~/.config/simple/theme.css, using the shared C theme loader.
Global navigation: ~/.config/simple/keys.ini.
Optional app overrides: ~/.config/simplecalendar/keys.ini and style.css.
An empty binding disables that action. Invalid accelerators retain the inherited binding.
App settings: ~/.config/simplecalendar/config.ini (size, day/agenda view, agenda_days, refresh_seconds).
Theme changes reload on the refresh interval; reopen for key/config changes. Press ? for the configured shortcuts.
Default navigation: h/l day, j/k week, Tab/Shift+Tab focus controls, H/L month, J/K event, Enter activate/details, e edit, n new, x delete with confirmation, t today, a agenda, s sync, c accounts, q close. Ctrl+s saves in the editor. Text inputs retain normal typing.

90-day report calculator
------------------------
Use the 90-day report button. Enter a report or arrival date to calculate date + 90 days. The due date is editable: use the immigration receipt appointment date if different. Saving adds a single event to the configured calendar and syncs normally, with a one-day DISPLAY reminder by default. All-day reminders fire at midnight the preceding day; choose a timed event for a daytime reminder. Enter the next actual report/arrival date to calculate the following report; this is not an automatically recurring series. Duplicate title/date submissions are rejected.

Compact layout: event cards use two short rows; empty views show the bundled matrix monk. Default height is 520. Unchanged event lists retain their widgets and keyboard focus during periodic refresh.

Event editing: Save and Cancel stay in a fixed top bar. Existing events enable Save only when fields or notifications differ from the opened event; reverting changes disables it again. New events require a nonblank title. Ctrl+S respects the same state.

Keyboard: n or Ctrl+N creates an event; e edits; Ctrl+S saves from any editor field; Ctrl+Shift+N adds a notification. Tab/Shift+Tab or Ctrl+j/k move between fields and buttons, Space toggles controls, arrows choose dropdown items, Enter activates focused buttons, and Esc cancels. Save remains disabled for unchanged events.

The no-event image follows the shared daylight wallpaper portrait used by the idle dashboard and lockscreen. It refreshes while the calendar remains open, with the bundled image as fallback when wallpaper art is unavailable.

The no-event card uses the full current wallpaper with edge-to-edge cover scaling, cropping without distortion. Idle dashboard and lockscreen portrait framing stays unchanged.

Optional report UI: `simple-calendar --show-90-day-report`. Hidden by default; existing events and reminders are preserved.

## Shared base and portable installation

Uses the shared C/GTK4 base in `simple-common`. Python UI code calls the same native library through a thin adapter. Shared theme and keyboard adapters replace separate implementations; app-specific commands and content remain local.

Requires Linux and Python 3.11+ for the source installer. Building the shared base requires a C compiler, make, pkg-config and GTK4 >= 4.12 development files. Install dependencies using your distribution’s package manager; package names can differ.

- Libraries / pkg-config modules: `gtk4 >= 4.12`, `json-c`.
- Python imports: `icalendar`, `recurring_ical_events`, `requests`, `vdirsyncer`.
- Required commands: `cc`, `make`, `pkg-config`, `python3`, `notify-send`.
- Optional Google Calendar connection: `aiohttp_oauthlib`.
- Desktop requirements: GTK desktop.

From the suite checkout (no pacman or distro detection on this path):

```sh
./install --dependencies simplecalendar
./install --check simplecalendar
./install --no-packages --install simplecalendar
```

To build a relocatable staging tree without changing your installation:

```sh
./install --install simplecalendar --stage "$PWD/package-simplecalendar"
```

Keep `simple-common` alongside the app sources. Staged files are under `.local/`; move that prefix as a unit so executables, shared libraries and resources stay together. Individual C Makefiles also accept `PREFIX`/`DESTDIR` where documented. See [portable builds](../docs/portability.md) for Debian/Arch dependency examples and limitations.

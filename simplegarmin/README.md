# Garmin dashboard

Separate GTK4 desktop dashboard for health and activity data synced to Garmin Connect.
Source is installed in `~/.local/src/simplegarmin/`; the launcher is
`~/.local/bin/simplegarmin`. Development files remain in
`~/Test/simpleapps/simplegarmin/`.

Launch `simplegarmin` or Super+Shift+G. Requires Python 3 and PyGObject GTK4.

Click Connect Garmin, create a Personal API key using the official linked Garmin
page, then paste it into the masked field. No Garmin password is stored. Keys
are saved with mode 0600 under `$XDG_CONFIG_HOME/simplegarmin/credentials.json`
(default `~/.config`). Responses are privately cached by date under
`$XDG_CACHE_HOME/simplegarmin` (default `~/.cache`). An internet connection is
required to refresh; the watch must first sync to Garmin Connect. Data is not live.

h/l changes day, t selects today, r refreshes, c opens connection settings,
q or Escape closes. Tab and Shift+Tab move between buttons; Enter activates.
The dashboard fetches on opening, changing dates, and manual refresh. No background
polling. Missing readings remain blank; network errors retain saved data for that day.
Partial responses are marked; unavailable endpoints remain blank.

Official API: https://developer.garmin.com/gc-developer-program/personal/personal-api/
Schema: https://developer.garmin.com/gc-developer-program/personal/swagger-docs/

Run `python3 check.py` for data/authentication/storage tests. Live authentication
requires the user's own Personal API key and has not been verified without one.

Detail sections: Heart, Recovery, Sleep, Stress and Breathing. j/k cycles
sections; 1–6 selects one directly. Includes the official overnight HRV endpoint.
Missing or unsupported readings stay blank.

Appearance uses the C Simple UI framework through `simple_ui.py` and `~/.config/simple/` palette.
Navigation reads `~/.config/simple/keys.ini`, with optional overrides in
`~/.config/simplegarmin/keys.ini`. The shared C keyboard handling preserves Tab,
Enter/Space activation, native control arrows, and text entry.

## Shared base and portable installation

Uses the shared C/GTK4 base in `simple-common`. Python UI code calls the same native library through a thin adapter. Shared theme and keyboard adapters replace separate implementations; app-specific commands and content remain local.

Requires Linux and Python 3.11+ for the source installer. Building the shared base requires a C compiler, make, pkg-config and GTK4 >= 4.12 development files. Install dependencies using your distribution’s package manager; package names can differ.

- Libraries / pkg-config modules: `gtk4 >= 4.12`.
- Python imports: `gi`.
- Required commands: `cc`, `make`, `pkg-config`, `python3`.
- Desktop requirements: GTK desktop; internet and Garmin Personal API key for live data.

From the suite checkout (no pacman or distro detection on this path):

```sh
./install --dependencies simplegarmin
./install --check simplegarmin
./install --no-packages --install simplegarmin
```

To build a relocatable staging tree without changing your installation:

```sh
./install --install simplegarmin --stage "$PWD/package-simplegarmin"
```

Keep `simple-common` alongside the app sources. Staged files are under `.local/`; move that prefix as a unit so executables, shared libraries and resources stay together. Individual C Makefiles also accept `PREFIX`/`DESTDIR` where documented. See [portable builds](../docs/portability.md) for Debian/Arch dependency examples and limitations.

# Simpleclip

Standalone clipboard history using the existing Simplepicker clipboard module. The installer builds and installs a private native binary and resources; no separately installed Simplepicker application is required. History stays in cliphist's existing database and is never migrated or cleared.

```sh
./install --install simpleclip
simpleclip
simpleclip --check-config
```

Settings are created under `$XDG_CONFIG_HOME/simpleclip` (`~/.config/simpleclip`): `config.toml` sets the title, size, startup search and Wayland layer behaviour; `keys.ini` sets navigation. Colours use the shared Simpleapps theme. Python launches the native GTK interface; cliphist stores history; wl-clipboard restores clipboard contents; `file` detects image MIME types. Optional ffmpeg enables video-file previews.

Type immediately to search. Enter copies the selected item and closes. Ctrl+j/k or arrows move while searching. Ctrl+Enter enters navigation: j/k move, gg/G jump, / resumes search, q closes. Esc closes in either mode. Ctrl+d deletes the selected history entry. The original text/image/file-reference restore logic is retained. Auto-paste is disabled by default; it can be configured with command argument arrays in `[commands]`.

Recording is separate from the interface. Reuse existing watchers; do not start duplicates. On a fresh Wayland desktop, arrange these commands in your session startup:

```sh
wl-paste --type text --watch cliphist store
wl-paste --type image --watch cliphist store
```

The installer does not enable watchers, change keyboard shortcuts, or read clipboard history. Clipboard storage limits and the database path remain cliphist settings. This app has no dependency on Yazi or Mango; compositor integration is detected automatically.

## Shared base and portable installation

Uses the shared C/GTK4 base in `simple-common`. Python UI code calls the same native library through a thin adapter. Shared theme and keyboard adapters replace separate implementations; app-specific commands and content remain local.

Requires Linux and Python 3.11+ for the source installer. Building the shared base requires a C compiler, make, pkg-config and GTK4 >= 4.12 development files. Install dependencies using your distribution’s package manager; package names can differ.

- Libraries / pkg-config modules: `gtk4 >= 4.12`, `gtk4-layer-shell-0`, `gio-unix-2.0`, `json-c`.
- Python imports: none beyond the standard library for the base app.
- Required commands: `cc`, `make`, `pkg-config`, `python3`, `cliphist`, `wl-copy`, `file`.
- Optional Clipboard video previews: `ffmpeg`.
- Desktop requirements: Wayland clipboard; GTK window with optional layer-shell.

From the suite checkout (no pacman or distro detection on this path):

```sh
./install --dependencies simpleclip
./install --check simpleclip
./install --no-packages --install simpleclip
```

To build a relocatable staging tree without changing your installation:

```sh
./install --install simpleclip --stage "$PWD/package-simpleclip"
```

Keep `simple-common` alongside the app sources. Staged files are under `.local/`; move that prefix as a unit so executables, shared libraries and resources stay together. Individual C Makefiles also accept `PREFIX`/`DESTDIR` where documented. See [portable builds](../docs/portability.md) for Debian/Arch dependency examples and limitations.

## License

Original Simpleapps code is licensed under GPL-3.0-or-later (GNU GPL version 3 or any later version). See the repository’s LICENSE and COPYING files. Third-party components retain their own licenses and notices.

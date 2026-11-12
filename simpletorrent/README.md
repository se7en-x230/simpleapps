# SimpleTorrent

Small C/GTK4 frontend for the existing local Transmission daemon. It does not replace the daemon or alter its settings, downloads, trackers or sharing configuration.

Build: `make`; install: `make install`. Dependencies: GTK4, json-c and libcurl. Newinit builds from source on each machine.

- j/k or arrows: navigate; g/G: first/last; /: search.
- Space: mark and move down; u: clear all marks. Enter or double-click also marks.
- a: add magnet, URL or .torrent path; File button: browse for a torrent.
- s/p: start/pause marked torrents, or the current row if none are marked.
- x: delete the marked torrents and their downloaded files, after confirmation.
- Shift+X: remove only the torrents, keeping downloaded files, after confirmation.
- q/Escape: close; Escape in search clears search first.

Global keys load from ~/.config/simple/keys.ini. Local overrides: ~/.config/simpletorrent/keys.ini, style.css and config.ini. The footer shows default shortcuts.

RPC runs off the GTK thread. Rows are updated in place every three seconds, preserving cursor and marked IDs. The session challenge is handled automatically. No login or other runtime is needed for the existing unauthenticated loopback daemon. Password-authenticated RPC is not supported in this first version; it reports an authentication error instead of modifying the daemon settings.

Super+O launches this interface and starts the existing daemon. tremc remains installed as a fallback. Closing the interface leaves Transmission running.

Completion: 100% requires metadata, selected download size, zero bytes remaining and no pending verification or local error. Seeding may continue after completion. Incomplete percentages never round up to 100%. While the UI is open, a desktop notification is sent once when an observed unfinished download completes; old completed torrents are silent on startup. Closing the UI leaves downloads running, but stops these notifications. Uses the existing desktop notification service through GIO/D-Bus, with no additional packages.

A dedicated All torrents summary shows combined download and upload speeds,
including torrents hidden by search. It refreshes every three seconds and clears
to unavailable when the daemon cannot be reached.

Uses the C Simple UI framework in `simple-common` for shared component styling,
navigation configuration and native GTK control handling. `make install` also
installs the shared library and stylesheet.

## Shared base and portable installation

Uses the shared C/GTK4 base in `simple-common`. Python UI code calls the same native library through a thin adapter. Shared theme and keyboard adapters replace separate implementations; app-specific commands and content remain local.

Requires Linux and Python 3.11+ for the source installer. Building the shared base requires a C compiler, make, pkg-config and GTK4 >= 4.12 development files. Install dependencies using your distribution’s package manager; package names can differ.

- Libraries / pkg-config modules: `gtk4 >= 4.12`, `json-c`, `libcurl`.
- Python imports: none beyond the standard library for the base app.
- Required commands: `cc`, `make`, `pkg-config`, `transmission-daemon`.
- Desktop requirements: GTK desktop.

From the suite checkout (no pacman or distro detection on this path):

```sh
./install --dependencies simpletorrent
./install --check simpletorrent
./install --no-packages --install simpletorrent
```

To build a relocatable staging tree without changing your installation:

```sh
./install --install simpletorrent --stage "$PWD/package-simpletorrent"
```

Keep `simple-common` alongside the app sources. Staged files are under `.local/`; move that prefix as a unit so executables, shared libraries and resources stay together. Individual C Makefiles also accept `PREFIX`/`DESTDIR` where documented. See [portable builds](../docs/portability.md) for Debian/Arch dependency examples and limitations.

## License

Original Simpleapps code is licensed under GPL-3.0-or-later (GNU GPL version 3 or any later version). See the repository’s LICENSE and COPYING files. Third-party components retain their own licenses and notices.

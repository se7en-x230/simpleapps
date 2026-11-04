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

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

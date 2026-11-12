# Simplebookmarks

A small GTK4 bookmark manager with instant search, Vim navigation and keyboard-accessible add, edit and remove dialogs. Opens links in your default browser; no Simplepicker or Yazi dependency.

Install from the repository: `./install --install simplebookmarks`.
Requires Python 3.11+, PyGObject and GTK 4.12+.

Search is focused when opened. Enter opens the selected result. Ctrl+Enter switches to navigation; j/k move, g/G jump to first/last, l opens, / returns to search. Use a to add, e to edit, x to remove, y to copy a URL and r to reload. Esc closes; q closes from navigation. Tab/Shift+Tab move through dialogs, Ctrl+S saves; Enter activates Save or Cancel when focused, and saves from an input field. Esc cancels. Removal requires confirmation. `simplebookmarks --add` opens the add dialog; a URL on the clipboard is offered automatically.

Settings live in `$XDG_CONFIG_HOME/simplebookmarks/config.toml` (normally `~/.config/simplebookmarks/config.toml`):

```toml
bookmarks_file = "~/.local/share/simplebookmarks/bookmarks.json"
window_width = 760
window_height = 520
start_in_search = true
close_after_open = true
```

On first launch, the Simplebookmarks location is preferred. An existing Simplepicker bookmarks file is reused only when no new file exists, and its location is saved in the config. A new list uses `$XDG_DATA_HOME/simplebookmarks/bookmarks.json`. Relative paths resolve from the config folder; `~` and environment variables are supported. `--check-config` validates without changing anything.

The JSON list contains objects with `label` and `url`. Additional fields are preserved. Edits are atomic, the previous file is kept as `bookmarks.json.bak`, and concurrent changes are rejected until you reload. Browser/search history and other personal data are not imported. Web search remains a Simplepicker module.

Bookmarks are sorted by open count, most used first. Existing Simplepicker usage counts are reused from `bookmark-history.json` beside the bookmark file. Successful browser launches increment the count; ties keep the original file order. Category tags appear as orange badges and are included in search. The footer shows navigation keys once; add/edit/remove shortcuts appear on their buttons.

## Shared base and portable installation

Uses the shared C/GTK4 base in `simple-common`. Python UI code calls the same native library through a thin adapter. Shared theme and keyboard adapters replace separate implementations; app-specific commands and content remain local.

Requires Linux and Python 3.11+ for the source installer. Building the shared base requires a C compiler, make, pkg-config and GTK4 >= 4.12 development files. Install dependencies using your distribution’s package manager; package names can differ.

- Libraries / pkg-config modules: `gtk4 >= 4.12`.
- Python imports: `gi`.
- Required commands: `python3`, `cc`, `make`, `pkg-config`.
- Desktop requirements: GTK desktop; default browser for opening URLs.

From the suite checkout (no pacman or distro detection on this path):

```sh
./install --dependencies simplebookmarks
./install --check simplebookmarks
./install --no-packages --install simplebookmarks
```

To build a relocatable staging tree without changing your installation:

```sh
./install --install simplebookmarks --stage "$PWD/package-simplebookmarks"
```

Keep `simple-common` alongside the app sources. Staged files are under `.local/`; move that prefix as a unit so executables, shared libraries and resources stay together. Individual C Makefiles also accept `PREFIX`/`DESTDIR` where documented. See [portable builds](../docs/portability.md) for Debian/Arch dependency examples and limitations.

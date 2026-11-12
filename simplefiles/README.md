# Simplefiles

A small graphical file chooser with Yazi-style navigation and the shared Simpleapps theme. Folder scanning runs in the background; a virtualized list keeps large directories responsive. The right panel lists the hovered folder’s contents, with folders first and the same hidden-file setting as the main list. Image and text previews load after a short navigation pause.

Requires Python 3.11+, PyGObject and GTK 4.12+. No terminal or ImageMagick dependency.

```sh
./install --install simplefiles
simplefiles ~/Pictures
simplefiles --multiple ~/Downloads
simplefiles --directory ~
simplefiles --save ~/Downloads/example.txt
```

The chooser writes selected absolute paths to stdout, or to `--output FILE`. Cancel returns no paths. Choosing a save destination does not create or alter it; an existing destination requires confirmation. Newlines in filenames cannot be returned through the line-based portal protocol.

## Keys

| Key | Action |
| --- | --- |
| h / j / k / l | Parent / down / up / enter folder or choose file |
| gg / G | First / last entry |
| Ctrl+u / Ctrl+d | Jump ten entries |
| Ctrl+o / Ctrl+i | Back / forward |
| Space | Toggle file selection in multiple-file dialogs |
| / or f | Filter current folder |
| . | Show hidden files |
| Ctrl+l | Edit location |
| g + key | Folder bookmark |
| md | Create folder |
| Ctrl+j / Ctrl+k | Scroll preview |
| i | Edit save filename |
| Enter | Enter folder, choose files/folder, or confirm save |
| Esc | Leave typing, clear filter/selection, then cancel |
| q | Cancel outside text fields |
| ? | Key help |

Type normally in location, filter and filename fields. Escape returns to navigation. Tab moves between controls. Mouse selection and double-click navigation also work. Single-step navigation wraps: k/Up on the first item goes to the last, and j/Down on the last goes to the first.

Default folder shortcuts include `gh` home, `gd` downloads, `gD` documents, `gm` music, `gc` config and `g/` root. Simplefiles imports literal two-key `g` → `cd PATH` bookmarks from `$XDG_CONFIG_HOME/yazi/keymap.toml`, without executing Yazi shell commands. Optional overrides belong in `$XDG_CONFIG_HOME/simplefiles/config.json`:

```json
{"bookmarks": {"p": "~/Pictures", "s": "~/Sync"}}
```

Shared colours come from `simple/aliases.css` or `simple/theme.css` in the XDG config/data directories. Filesystem management, shell actions and Yazi plugins remain in Yazi.

## File dialog portal

`simplefiles-portal` accepts the existing `xdg-desktop-portal-termfilechooser` wrapper arguments: multiple, directory, save, initial path, output file, debug. Set the portal's `[filechooser] cmd` to its installed absolute path. The standard installer does **not** switch your portal automatically. Keep your previous wrapper/config to switch back.

Only applications that use this portal are affected. Native app dialogs may bypass it. The wrapper protocol does not expose application file-type filters or custom chooser controls; Simplefiles cannot enforce those through this adapter.

Keyboard confirmation: `Ctrl+Enter` opens, chooses or saves from any field.
`Esc` cancels immediately; `q` cancels outside text fields. `Tab` / `Shift+Tab`
moves through controls, and `Enter` or `Space` presses the focused button.
The file list retains its Yazi-style navigation and selection keys.

## Shared base and portable installation

Uses the shared C/GTK4 base in `simple-common`. Python UI code calls the same native library through a thin adapter. Shared theme and keyboard adapters replace separate implementations; app-specific commands and content remain local.

Requires Linux and Python 3.11+ for the source installer. Building the shared base requires a C compiler, make, pkg-config and GTK4 >= 4.12 development files. Install dependencies using your distribution’s package manager; package names can differ.

- Libraries / pkg-config modules: `gtk4 >= 4.12`.
- Python imports: `gi`.
- Required commands: `python3`, `cc`, `make`, `pkg-config`.
- Desktop requirements: GTK desktop; optional termfilechooser portal adapter.

From the suite checkout (no pacman or distro detection on this path):

```sh
./install --dependencies simplefiles
./install --check simplefiles
./install --no-packages --install simplefiles
```

To build a relocatable staging tree without changing your installation:

```sh
./install --install simplefiles --stage "$PWD/package-simplefiles"
```

Keep `simple-common` alongside the app sources. Staged files are under `.local/`; move that prefix as a unit so executables, shared libraries and resources stay together. Individual C Makefiles also accept `PREFIX`/`DESTDIR` where documented. See [portable builds](../docs/portability.md) for Debian/Arch dependency examples and limitations.

## License

Original Simpleapps code is licensed under GPL-3.0-or-later (GNU GPL version 3 or any later version). See the repository’s LICENSE and COPYING files. Third-party components retain their own licenses and notices.

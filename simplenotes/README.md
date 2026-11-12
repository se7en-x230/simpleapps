# Simplenotes

Plain-text notes with a searchable list, an integrated editor, clipboard capture and the shared Simpleapps theme. Files stay ordinary UTF-8 Markdown/text files in a configurable folder. Existing folder sync continues to work; Simplenotes does not provide its own sync service.

```sh
./install --install simplenotes
simplenotes
simplenotes --notes-dir ~/Documents/Notes
simplenotes --check-config
```

Requires Python 3.11+, PyGObject and GTK 4.12+. No Yazi, terminal, external editor or clipboard utility is required. Markdown remains source text; the preview is not rendered HTML. The editor offers normal text editing with Vim-style navigation modes, not a complete Vim implementation.

## Your files

Folder precedence:

1. `--notes-dir PATH`
2. `$XDG_CONFIG_HOME/simplenotes/config.toml`
3. Existing `$XDG_CONFIG_HOME/notesmanager/config.toml`
4. The standard Documents folder, in a new `Notes` subfolder

`XDG_CONFIG_HOME` defaults to `~/.config`. A configured folder must exist; Simplenotes does not silently recreate a missing sync folder. Only the default Documents/Notes folder is created automatically.

On first launch, Simplenotes creates its own config with the resolved notes path and these settings. Existing files are preserved. Restart after changing settings.

```toml
notes_dir = "~/Documents/Notes"
start_in_search = true
autosave = true
autosave_delay_ms = 900
search_contents = true
font_size = 12
wrap_text = true
window_width = 1100
window_height = 760
sidebar_width = 310
```

`autosave = false` disables saving after typing pauses; switching notes, closing, and Ctrl+s still save. `search_contents = false` searches names only. Window and sidebar dimensions are initial pixel sizes; font size is in points. The config validates values and reports unknown setting names.

Relative paths resolve against the config file. `~` and environment variables work. Existing notes are never moved when changing this setting.

## Keyboard workflow

Search is focused on startup. Ctrl+J/K select notes while you type; Enter edits the selected note. Ctrl+Enter focuses the list for j/k navigation; `/` returns to search. Escape closes. Shared defaults and per-app overrides are documented in [the framework](../simple-common/FRAMEWORK.md#navigation-defaults).

| Key | Action |
| --- | --- |
| j / k, arrows | Select notes |
| gg / G | First / last note |
| Ctrl+u / Ctrl+d | Jump through notes or page through preview |
| / | Search filenames and contents |
| l / h | Preview / return to list (h at start of preview) |
| i / Enter | Edit the selected note |
| Escape | Save and close |
| Ctrl+Enter | Save and return to note navigation |
| n | New note; enter `Folder/Title.md` for an existing subfolder |
| Shift+n | New folder |
| p | Create a note from clipboard text |
| a | Append clipboard text to current note |
| y / Shift+y | Copy note text / file reference |
| Ctrl+s | Save now |
| Ctrl+Shift+s | Save current text as a new note |
| Ctrl+r | Refresh note list |
| Shift+r | Recover an available draft as a new note |
| ? | Key help |
| q | Close outside text fields |

In edit mode, type normally. Standard Ctrl+a/c/x/v and undo/redo work. Ctrl+Enter returns to navigation; in preview, h/j/k/l and gg/G move the cursor. Search and name fields accept ordinary text. Tab and mouse controls remain available.

## Saving and recovery

Edits save after a 900 ms pause and before switching notes or closing. Saves use the file's version token, so a note changed by another editor or sync is not silently overwritten. Clean notes reload external modifications. New or removed notes appear after Ctrl+r.

A failed save keeps the editor open and offers Ctrl+Shift+s to save a separate copy. Recovery text is stored privately under `$XDG_STATE_HOME/simplenotes/drafts` (`~/.local/state` by default) before attempting a save; it is removed after a successful save. A surviving draft is indicated when its note is opened. Drafts protect attempted saves, not keystrokes entered immediately before a crash.

Hidden files, symlinks below the notes root, binary files and notes larger than 2 MiB are excluded. This app edits text; existing image/file attachment actions remain available in the old notes manager.

## Checks

`python3 check.py` checks file safety and configuration. `python3 check-gui.py` exercises the real GTK editor in a graphical test session, using temporary notes only.

## Shared base and portable installation

Uses the shared C/GTK4 base in `simple-common`. Python UI code calls the same native library through a thin adapter. Shared theme and keyboard adapters replace separate implementations; app-specific commands and content remain local.

Requires Linux and Python 3.11+ for the source installer. Building the shared base requires a C compiler, make, pkg-config and GTK4 >= 4.12 development files. Install dependencies using your distribution’s package manager; package names can differ.

- Libraries / pkg-config modules: `gtk4 >= 4.12`.
- Python imports: `gi`.
- Required commands: `python3`, `cc`, `make`, `pkg-config`.
- Desktop requirements: GTK desktop; local UTF-8 text files and optional existing sync folder.

From the suite checkout (no pacman or distro detection on this path):

```sh
./install --dependencies simplenotes
./install --check simplenotes
./install --no-packages --install simplenotes
```

To build a relocatable staging tree without changing your installation:

```sh
./install --install simplenotes --stage "$PWD/package-simplenotes"
```

Keep `simple-common` alongside the app sources. Staged files are under `.local/`; move that prefix as a unit so executables, shared libraries and resources stay together. Individual C Makefiles also accept `PREFIX`/`DESTDIR` where documented. See [portable builds](../docs/portability.md) for Debian/Arch dependency examples and limitations.

## License

Original Simpleapps code is licensed under GPL-3.0-or-later (GNU GPL version 3 or any later version). See the repository’s LICENSE and COPYING files. Third-party components retain their own licenses and notices.

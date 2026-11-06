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

Search is focused on startup: type immediately, then Enter to navigate the notes. Set `start_in_search = false` to start in the note list instead.

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

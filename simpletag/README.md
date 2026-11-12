# Simpletag

A small keyboard-driven folder-tagging frontend. Picard remains the backend and
owns metadata lookup, fingerprints, artwork, renaming, destination folders and
all tagging settings. Simpletag uses the shared Simpleapps C/GTK framework and
theme, plus the existing Simplefiles directory chooser. No new tagging database,
HTTP service, background daemon or copied UI framework.

## Install

Requires Linux, Python 3.11+, GTK 4.12+, PyGObject, Picard **3.x** with its Python
plugin API and `picard-cli`, and Chromaprint (`fpcalc`) for scanning. Building the
shared library requires a C compiler, make and pkg-config. On Debian install the
GTK development/Python GI packages and a Picard 3 distribution; older distro
Picard 2 packages are not compatible with this bridge. On Arch the installer can
use `picard`, `chromaprint`, `python-gobject`, `gtk4`, `base-devel`, and `pkgconf`.

From the suite root:

```
./install --dependencies simpletag
./install --no-packages --install simpletag --yes
simpletag --setup
simpletag
```

Simplefiles is bundled from its existing source and shares the same framework.
Setup registers/enables the included local plugin through Picard's own CLI.
Close Picard before setup, then reopen it. The installer never changes Picard's
tagging settings. Packaged files live under ~/.local/share/simpletag; editable
settings are ~/.config/simpletag/config.toml and keys.ini. XDG paths are respected.

## Workflow

- o / Ctrl+O: choose a folder (never a file) using Simplefiles.
- l / Ctrl+L: cluster and look up all unmatched files using existing tags.
- a / Ctrl+A: fingerprint/scan the selected remaining unmatched files.
- Enter: focus the selected album's current/proposed tags for review.
- s / Ctrl+S: save the selected album's unambiguous matches, then remove only
  successfully saved files from the work list. Nothing is deleted from disk.
- r / Ctrl+R: remove the selected folder/album without saving. Audio files remain
  on disk; unsaved proposed tag changes are discarded.
- p / Ctrl+P: open Picard for settings, alternate releases, duplicates or errors.
Plain-letter actions work outside text entry; Ctrl shortcuts also work while searching.

- `/`: search; j/k: select; first Esc leaves search, next Esc closes.

All action keys use the shared framework's per-app keys.ini overrides. Global
style and navigation live in ~/.config/simple. Set `[interaction]
start_in_search=true` in the app keys.ini to open with search visible.

Matches are proposals, not a guarantee of the right release: inspect the tags
before saving. Save uses **current Picard settings**, including moving/renaming
files if enabled there. Failed saves, duplicate track matches and unmatched files
remain. Scan is explicit; lookup never automatically saves. The frontend polls
only while open. Closing Simpletag waits for active work, then clears Picard’s work list without
saving and closes the frontend. The next opening starts empty. Picard remains
running; its normal close action still uses its own unsaved-work handling. Set
`clear_on_close = false` in Simpletag’s config.toml to retain the work list instead. Picard remains a full process,
so this is a small additional frontend, not a replacement for Picard's memory use.

## Bridge

The included Picard 3 plugin listens on a private local Unix socket under
$XDG_RUNTIME_DIR/simpletag-UID (private /tmp fallback). It accepts a small fixed
set of operations; all Picard model access is on its Qt main thread. Requests run
off the GTK thread. No credentials or external network listener are introduced.
Picard itself contacts MusicBrainz/AcoustID as usual. The bridge can be disabled
in Picard's Plugins settings. Upgrades of Picard may require bridge updates.

References: https://picard-docs.musicbrainz.org/en/latest/usage/exec_commands.html
and https://picard.musicbrainz.org/docs/plugins/

## Checks

`python3 tests/check.py` checks save completion, errors, matching scope and idle
state with fixtures. `python3 tests/gui.py` checks keyboard interaction using fake
entries. `python3 tests/live.py` exercises real Picard loading and tag saving on a
generated FLAC in an isolated temporary profile (requires ffmpeg and mutagen).
It does not test online MusicBrainz or AcoustID results.

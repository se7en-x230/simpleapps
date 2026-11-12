# Simplecapture

A portable screenshot workflow around grim, slurp, Swappy and wl-clipboard. Select a region, annotate, and copy the resulting PNG. It reuses those tools rather than maintaining a second annotation editor.

```sh
./install --install simplecapture
simplecapture                 # configured default (region + editor)
simplecapture --fullscreen
simplecapture --no-edit       # quick region capture
simplecapture --menu          # small keyboard-controlled mode menu
simplecapture --save --delay 3
simplecapture --check-config
```

Requires Python, grim, slurp, Swappy and wl-clipboard on a compatible Wayland compositor. The optional menu uses PyGObject/GTK4. No Mango, Yazi or Simplepicker dependency.

On first run, `$XDG_CONFIG_HOME/simplecapture/config.toml` is created (`~/.config` by default). It imports an existing Swappy save directory if available; otherwise it uses the standard Pictures/Screenshots folder. Configure:

```toml
save_dir = "~/Pictures/Screenshots"
mode = "region"
edit = true
copy = true
save = false
delay_seconds = 0
settle_ms = 300
notify = true
cancel_action = "cancel"
```

Paths support `~` and environment variables; relative paths resolve against the config folder. `save=true` saves the final image automatically. Swappy's Save button saves to the configured directory even when automatic saving is off. Temporary editor settings do not change your global Swappy config.

The menu offers r region, f full desktop, c quick region, a quick desktop; Esc/q close. Slurp's Escape cancels by default. Set `cancel_action="fullscreen"` to retain the old capture-full-desktop-on-cancel behaviour. Swappy retains its annotation shortcuts; closing Swappy returns its final image for clipboard copying, as in the previous Print workflow.

The installer adds an application-menu entry but does not change Print or any other shortcut. No screenshots or original files are overwritten by automatic saving.

## Screen recording

`simplecapture --record` toggles recording: select a region, then run it again to stop. `--record --fullscreen` starts a full-desktop recording. The capture menu also provides **Record / stop [v]**.

```toml
record_dir = "~/Videos/Recordings"
record_mode = "region"
recorder = "wf-recorder"
record_audio = true
record_audio_device = ""
record_copy = true
```

An empty audio device uses the default output's monitor (desktop sound). Set `record_audio = false` for silent video, or specify an audio device explicitly. Supported recorders are `wf-recorder` and `wl-screenrec`. `record_copy` copies the completed video as a file URI so it can be pasted as an attachment.

The recorder receives a graceful stop and finishes its video trailer before the clipboard is updated. A lock and process-start-time check prevent duplicate recordings and avoid signalling a reused PID. Cancelling region selection starts no recording. Recording state lives under `$XDG_RUNTIME_DIR`.

The optional `--capture-recording` installer feature supplies wf-recorder and PulseAudio tools; `wl-screenrec` can be installed separately. Neither recorder is needed for screenshots. Screen recording keeps the previous script's lifecycle logic in a packaged helper with configurable paths.

## Shared base and portable installation

Uses the shared C/GTK4 base in `simple-common`. Python UI code calls the same native library through a thin adapter. Shared theme and keyboard adapters replace separate implementations; app-specific commands and content remain local.

Requires Linux and Python 3.11+ for the source installer. Building the shared base requires a C compiler, make, pkg-config and GTK4 >= 4.12 development files. Install dependencies using your distribution’s package manager; package names can differ.

- Libraries / pkg-config modules: `gtk4 >= 4.12`.
- Python imports: `gi`.
- Required commands: `python3`, `grim`, `slurp`, `swappy`, `wl-copy`, `cc`, `make`, `pkg-config`.
- Optional Screen recording with desktop audio: `wf-recorder`, `pactl`, `flock`, `bash`.
- Desktop requirements: Wayland compositor supporting grim capture; optional GTK capture menu.

From the suite checkout (no pacman or distro detection on this path):

```sh
./install --dependencies simplecapture
./install --check simplecapture
./install --no-packages --install simplecapture
```

To build a relocatable staging tree without changing your installation:

```sh
./install --install simplecapture --stage "$PWD/package-simplecapture"
```

Keep `simple-common` alongside the app sources. Staged files are under `.local/`; move that prefix as a unit so executables, shared libraries and resources stay together. Individual C Makefiles also accept `PREFIX`/`DESTDIR` where documented. See [portable builds](../docs/portability.md) for Debian/Arch dependency examples and limitations.

## License

Original Simpleapps code is licensed under GPL-3.0-or-later (GNU GPL version 3 or any later version). See the repository’s LICENSE and COPYING files. Third-party components retain their own licenses and notices.

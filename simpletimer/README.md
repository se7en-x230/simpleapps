# Simpletimer

A small GTK4 countdown, stopwatch, Pomodoro and fasting tracker. Dark Simpleapps theme, gold title and dark red mode selection. Python 3.11+, PyGObject and GTK4; no Yazi, compositor-specific tools or shell-script dependency.

```sh
./install --install simpletimer
simpletimer
simpletimer --mode fasting
simpletimer --check-config
```

Settings are created at `$XDG_CONFIG_HOME/simpletimer/config.toml` (normally `~/.config/simpletimer/config.toml`):

```toml
countdown_minutes = 5
focus_minutes = 25
break_minutes = 5
fasting_hours = 16
fasting_state_dir = ""
notify = true
```

The fasting target is a display preference, not a health recommendation. The tracker reports elapsed time without predicting weight loss. Enter hours ago to start a fast retrospectively. Start/Stop shares the existing `fasting-tracker` start-file format, so a running fast appears automatically. An empty state directory respects `FASTING_STATE_DIR`, falling back to `$XDG_STATE_HOME/fasting-tracker`. Custom paths support `~`, environment variables and paths relative to the config directory. The original script remains usable.

Countdown, stopwatch and Pomodoro state is saved privately under `$XDG_STATE_HOME/simpletimer`. Timers use elapsed wall time, including suspend. Pause freezes elapsed/remaining time. Pomodoro waits for Start before moving from focus to break or back again.

Closing the window leaves the lightweight app running for countdown notifications. Launching it again reopens the window. Notifications require a desktop notification service. Timers survive restarting the app; overdue notifications appear when it next runs. The installer does not add an autostart service, so notifications cannot fire after logout until the app is launched again.

Keyboard controls: **1–4** choose modes; **h/l** or **j/k** cycle modes; **Space** starts/pauses (starts/stops fasting); **r** resets the selected non-fasting timer; **i** edits minutes/hours ago; **Enter** applies; **Esc/q** closes. Text entries keep normal typing; Escape closes from anywhere. Reset never clears a fast: use Stop explicitly.

Run `python3 simpletimer/check.py` for persistence and lifecycle tests. `check-gui.py` exercises actual GTK controls in an isolated graphical session. The standard installer supports source bundles and uninstall receipts.

# Simpletimer

A small GTK4 countdown, stopwatch, Pomodoro, fasting tracker and meditation timer. Dark Simpleapps theme, gold title and dark red mode selection. Python 3.11+, PyGObject and GTK4; no Yazi, compositor-specific tools or shell-script dependency.

```sh
./install --install simpletimer
simpletimer
simpletimer --mode fasting
simpletimer --mode meditation
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
meditation_minutes = 30  # 0 = open end
```

The fasting target is a display preference, not a health recommendation. The tracker reports elapsed time without predicting weight loss. Enter hours ago to start a fast retrospectively. Start/Stop shares the existing `fasting-tracker` start-file format, so a running fast appears automatically. An empty state directory respects `FASTING_STATE_DIR`, falling back to `$XDG_STATE_HOME/fasting-tracker`. Custom paths support `~`, environment variables and paths relative to the config directory. The original script remains usable.

Countdown, stopwatch, Pomodoro and meditation state is saved privately under `$XDG_STATE_HOME/simpletimer`. Timers use elapsed wall time, including suspend. Pause freezes elapsed/remaining time. Pomodoro waits for Start before moving from focus to break or back again.

Esc/q or the Close [Esc] button hides the window and leaves the lightweight app running for notifications. Quit [Q] or the window manager close action (Super+Q in this setup) asks for confirmation before quitting the app. The warning explains that all alarms and bells stop until reopening; saved timers and elapsed time are preserved. Launching it again reopens the window. Notifications require a desktop notification service. Timers survive restarting the app; overdue notifications appear when it next runs. The installer does not add an autostart service, so notifications cannot fire after logout until the app is launched again.

Keyboard controls: **1–5** choose modes; **h/l** or **j/k** cycle modes; **Space** starts/pauses (starts/stops fasting); **r** resets the selected non-fasting timer; **i** edits minutes/hours ago; **m** mutes/unmutes meditation waypoints; **f** finishes meditation; **Enter** applies; **Esc/q** hides; **Q** quits. Text entries keep normal typing; Escape closes from anywhere. Reset never clears a fast: use Stop explicitly.

Run `python3 simpletimer/check.py` for persistence and lifecycle tests. `check-gui.py` exercises actual GTK controls in an isolated graphical session. The standard installer supports source bundles and uninstall receipts.

## Meditation

Choose **Meditate [5]**, enter the session length in minutes, press Enter to set it,
then Space to start. Enter **0** for an open-ended session. That is the only timing
setting: waypoint bells always occur every **10 minutes**. A 30-minute session
rings at the start, 10 minutes, 20 minutes and the finish. An open-ended session
counts elapsed time until you press **f / Finish**. Space pauses/resumes either mode.

**Mute 10-minute bells [m]** silences only waypoint sounds; the beginning and ending
bells still play. The mute preference and session length are saved with timer state.
Reset keeps the chosen length and mute preference. Setting a new length prepares a
paused session. The config supplies the default duration for a new session.

There are two softly synthesized bells: a warm, six-second beginning/ending bell
and a quieter, 3.2-second waypoint bell. Both are generated locally; there are no
online services or sound downloads. Listen to the samples:

- [Beginning / ending bell](../docs/audio/meditation-begin-end.wav)
- [10-minute waypoint bell](../docs/audio/meditation-waypoint.wav)

Sound uses an available `paplay`, `pw-play` or `aplay`; the installer offers the
optional `libpulse` package for `paplay`. Without a player the timer and desktop
notifications still work, and the window reports the unavailable sound.

Bells continue with the window hidden or another mode shown. After sleep/restart,
missed intervals produce one current cue rather than a burst of old bells. A finish
rings once. The app must be running for timely alerts; existing timer/fasting state
is preserved.

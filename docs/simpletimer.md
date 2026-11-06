# Simpletimer

Countdown, stopwatch, Pomodoro, fasting and meditation timer.

**Meditate [5]**: choose a duration or **0 for open end**. Soft bells mark the start,
each 10 minutes and the finish. **m** mutes waypoint bells; **f** finishes the session.

[Start/end bell](audio/meditation-begin-end.wav) · [Waypoint bell](audio/meditation-waypoint.wav)

![simpletimer screenshot](screenshots/simpletimer.png)

```sh
./install --install simpletimer
simpletimer
./install --uninstall simpletimer
```

See [features, configuration, dependencies and keyboard controls](../simpletimer/README.md).


Quit (Q or the window close shortcut) asks for confirmation: all alarms and bells stop while the app is closed. Saved timers are retained and elapsed time continues. Esc/q only hide the window and keep alerts running.

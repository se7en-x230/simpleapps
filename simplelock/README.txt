Simplelock
==========
A separate C/GTK4 Wayland session locker using ext-session-lock-v1 and PAM.
The card design and artwork match Simplepicker. It does not launch the picker
or use its dmenu, dismissal keys, IPC socket, or benchmark mode.

Build/install: make && make install PREFIX="$HOME/.local"
Run: simplelock                 # stays in foreground until unlocked
     simplelock -f              # returns only after compositor confirms locking
     simplelock --check-config  # checks TOML and PAM service without locking

Config: $XDG_CONFIG_HOME/simplelock/config.toml (normally ~/.config/simplelock).
An example is installed in ~/.local/share/simplelock/lock.toml.
Simplelock has its own configuration and artwork; Simplepicker is not required.
The default PAM service is login. Password-only PAM conversation; separate
OTP/multi-step prompts are not supported. Failed authentication never unlocks.

Appearance: style.css is the base theme, dashboard.css styles the cards, and
optional lock.css overrides the locker. All are beside config.toml.
[lock] playing_image sets the calendar-side profile while music plays;
idle_image sets it when paused/stopped/idle; album_idle_image sets the large
idle album card. Defaults are in images/. Paths may be relative, absolute or ~/.
idle.toml contains the idle card's title and subtitle.
The Cava gradient uses .dash-visualizer and .dash-visualizer-high text colors.
Missing optional art is replaced by an icon; missing Cava hides the visualizer.
The full card layout scales down to fit smaller outputs. Each output gets its
own lock surface, including outputs enabled or connected while locked.

Portability: no Mango/Hyprland IPC or compositor configuration is used. Requires
a Wayland compositor supporting ext-session-lock-v1 and gtk4-layer-shell >=1.2.
Other desktops can invoke the same binary from their shortcuts/idle manager.
This is not an X11 locker. PAM service names may differ across distributions.
The backdrop is a charcoal/dark-red gradient with mirrored red glows and subtle
layered contours for depth.
It does not capture the desktop or apply blur; every output uses the same theme.
Optional Cava uses the PulseAudio interface (also supported by PipeWire).
Optional NetworkManager improves connection labels; IPs still use getifaddrs.
MPRIS provides track information. Missing optional services do not prevent locking.

Security/lifecycle: only PAM_SUCCESS invokes the protocol unlock request.
Escape clears the password when its field has focus; from the calendar it
returns to the password. Clicks, motion and other keys cannot dismiss the lock.
The compositor retains the lock if the locker crashes. Recovery from a crash
is compositor-dependent; Mango supports launching a replacement locker.
The process disables core dumps; password entries use GTK's password buffer,
and authentication copies are memory-locked when possible and explicitly wiped.
No password is logged or supplied through command-line arguments/environment.
A -f caller receives success only after the compositor acknowledges the lock.

Sources: view.c adapts the local Simplepicker dashboard renderer. util.c keeps
only subprocess helpers; fit.c handles output-size fitting. Authentication and
session ownership are isolated in auth.c and lock.c. No launcher code is linked.
The vendored tomlc99 license is in vendor/LICENSE.tomlc99.

Development: SIMPLELOCK_TEST builds use a private PAM config directory. This
code path is absent from the installed binary. Never install simplelock-test.
The installed target is always simplelock. Automated tests must use a separate
compositor socket and a private D-Bus session, never the user's active desktop.

Calendar annotations: shared with the Simple family. Build alongside
../simple-common/calendar.h; configuration and offline dates are in
~/.config/simple/calendar.ini. See ~/.config/simple/calendar-README.txt.

Calendar keys: Tab or Shift+Tab switches password/calendar focus. Password
focus is the default. h/l move one day; k/j move one week; Page Up/Down move
one month; Home returns to today. Escape from the calendar restores the
password insertion point without changing its text. Enter in the calendar
does not authenticate. Calendar movement inherits simple/keys.ini, with
simplelock/keys.ini overrides. See ~/.config/simple/navigation.txt.

Idle chant: the optional ~/.config/simple/idle-audio.py helper loops the shared
audio/namo-tassa.mp3 only while this view is open and no other audio/music plays.
One shared playback lock prevents duplicate audio across views/outputs. Playback
stops on close/unlock, parent exit, or other audio starting. No MPRIS registration
is made for the chant, so it does not replace track metadata or the idle layout.
Requires mpv, pactl, and Python GObject; failures leave the UI/lock functional.

Artwork sizing: the cover image is an unmeasured overlay inside its square
frame. Portrait/landscape image dimensions cannot enlarge the layout and
force LockFit to shrink all text. Images retain their original aspect ratio.

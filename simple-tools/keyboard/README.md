# Keyboard & shortcuts

Super+/ opens one shared-framework window with **Keybinds** and **Keyboard layout**
tabs. Ctrl+H selects Keybinds; Ctrl+L selects Keyboard layout. Click a tab or use Ctrl+Tab to switch; Tab moves between controls.

Keybinds starts with search hidden and the list focused. Press / to search.
The first Escape clears and hides search; Escape with search hidden closes. App/action names precede their opening shortcuts.
Search music, dashboard, system, simple, or an app name. Ctrl+J/K selects without
leaving search; Enter launches the selected app/action and closes the window. Ctrl+I opens More keys for Simple apps. Back to apps or
Alt+Left returns. Escape closes. App launchers use the existing Mango action; apps without bindings run their named command. The More keys view is reference-only. Failed launches show an error.

Key sorting is the default on opening. Sort by name with Ctrl+N or by key with
Ctrl+S. Sorting shortcuts and the current order appear in the footer; no sort buttons. Key sorting
groups Super+A, Super+Alt+A, Super+Ctrl+A, Super+Shift+A before B. Filtering and
sort state survive tab switches. No-shortcut entries show their opening route.

Keyboard layout retains the saved physical layer diagrams and PDF controls.
`--layout` starts on that tab; `--watch` and `--export` remain supported.
Search/navigation uses the shared C framework through its Python adapter.

## Optional configuration

Copy `config.example.ini` to `~/.config/simplepicker/keyboard/config.ini` if you
want to override detection. Your existing Vial `config.json` remains separate.
No background service, account or WM configuration edits are required.

```ini
[shortcuts]
environment = hyprland
config = ~/.config/hypr/hyprland.conf

[keyboard]
enabled = false

[names]
fleet-dashboard = Devices dashboard
```

Supported environments: `auto`, `mango`, `hyprland`, and `none`. `none` lists only
installed Simple apps. Config paths can be absolute, use `~`, or be relative to
this module's config directory. Both file readers follow `source` includes/globs
and substitute config variables; includes are resolved relative to their file.
Mango recognizes spawn/spawn_shell and named scratchpads. Hyprland's `.conf`
reader recognizes exec/execr bindings, descriptions, unbinds and the default submap.
Non-default submaps are omitted because they are not global opening shortcuts.

For Hyprland `.lua`, the module reads the **running session's** resolved bindings
using `hyprctl -j binds`; it does not evaluate Lua, and cannot preview an inactive
Lua configuration at another path. Missing files or compositor errors appear in
the window. Launching uses the selected WM's command, not a Mango command on Hyprland.
Readers do not execute config commands when browsing or searching.
See the official [Hyprland binding reference](https://wiki.hypr.land/0.54.0/configuring/binds/)
for the older file syntax and [current binding reference](https://wiki.hypr.land/configuring/core/binds/)
for Lua-based configurations.

`keyboard.enabled = auto` keeps the physical layout tab when its existing
`config.json` is present; `false` disables layout loading and polling entirely.
`true` explicitly enables it. The optional layout/PDF tools retain their existing
Vial source configuration. `[names]` overrides labels by command name; keep a
`Simpleclip — ...` prefix if you want automatic Simpleclip More keys matching.

Runtime: Python 3, PyGObject/GTK4 and the shared Simple UI library. Mango launches
require `mmsg`; Hyprland launches and live binding reads require `hyprctl`.
PDF export additionally uses Cairo/Pango. This desktop validates Mango live and
Hyprland through fixture tests; live Hyprland operation has not been tested here.

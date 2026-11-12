# Simple UI — C first

The shared GTK4 framework lives in `simple-ui.c` / `simple-ui.h`. Python apps use
`simple_ui.py`, a thin ctypes adapter to the same native library (ABI 1), rather
than reimplementing its theme or key logic. No extra daemon or runtime process.

Priorities: speed, simplicity, useful functionality, keyboard-first operation.
Keep app-specific features out of the core. Do not block the GTK thread on network
or disk-heavy work. Keep native GTK focus, activation and editing behavior intact.

## First migration

All native app builds link this library. Existing `simple-theme.h`,
`simple-keyboard.h`, `theme_loader.py` and `simple_keyboard.py` are compatibility
adapters to it, preserving app-specific editor commands. Python app windows use
the same palette and standard controls. Panel/lock protocol surfaces retain their
specialized rendering; wallpaper has no GTK UI and optionally invokes the picker. Simplepicker remains
a separate launcher/module host; modules are not being converted into standalone
apps. Shared infrastructure is unified; app-specific layouts and domain logic are not rewritten into a universal widget tree.

## API and ownership

Call `simple_ui_window(window)` after creating a GTK window. It loads shared theme
colors and the scoped `framework.css` component styles once per display. Only
windows with `simple-app` are affected. Widgets are borrowed, never retained by the
library. All API calls must run on the GTK main thread. Python uses PyGObject's
native pointer capsule while retaining its wrapper for the duration of each call.

Use the classes `title`, `heading`, `muted`, `status`, `card`, `value`, `simple-tabs`
and `root`. Palette values remain in `~/.config/simple/theme.css`; common spacing,
controls and selected-tab appearance live in `framework.css`. App CSS handles
specialized content only. Theme changes apply when reopening an app.

`simple_ui_control_key` returns -1 to continue app shortcuts, 0 to let GTK handle
native controls/text, and 1 when it activated a focused control. Bind search before handling app-specific shortcuts. q closes outside editable fields;
Escape dismisses a dialog or returns from an editing context before closing.
Applications own closing and async-work lifecycle; the library does not terminate
processes or decide whether unsaved edits should be discarded.

`simple_ui_key_matches` / `simple_ui_key_label` share defaults and load
`~/.config/simple/keys.ini`, followed by `<app>/keys.ini`. Each app/action is cached
after its first lookup, avoiding filesystem access while navigating. Restart to
apply changed keys. `simple_ui_key_label` returns owned memory; release it with
`simple_ui_free`. Python maps that ownership automatically.

## Build and install

`make -C simple-common` builds `libsimple-ui.so`. `make install` installs the
library and stylesheet into `~/.local/lib/simple-common`, and the public header
into `~/.local/include`. `PREFIX` and `DESTDIR` are supported; the Python adapter
and fallback palette are installed beside the library, so resource lookup does
not assume a particular home directory or install prefix. C apps link to `-lsimple-ui` with a relative runtime search
path; the Python adapter loads the checkout library or the installed library.
Source and adapter are retained in `~/.local/src/simple-common` on this desktop.

Next migrations should reuse this foundation, preserve each app's features, and
verify keyboard navigation, close behavior, errors and layout before installation.
New core features belong in C first, with Python bindings only where needed.

## Install once, share across apps

The first selected GTK app brings in the base automatically. Later app installs
reuse the existing library when its source/toolchain identity and file digest
match; no recompilation or rewrite is needed. A base update replaces the one
shared runtime, not a separate copy per app. Apps require no background framework
service. Only selected apps and their required helpers are installed.

Installer receipts track all apps owning each shared file. Removing one app keeps
files needed by another; removing the final dependent app removes the unmodified
shared runtime. Personal settings and maintained source snapshots are retained.
Headless wallpaper operation does not require a GTK library; its optional picker
UI uses the same base through Simplepicker.

## Navigation defaults

Search lists open ready to type. Ctrl+J/K (or arrows) changes the selected result
without leaving search; Enter activates it. Ctrl+Enter focuses the results for
j/k navigation and app commands; `/` returns to search. Esc closes the window;
q closes in navigation mode and types normally in search. Editors and dialogs
retain their save/cancel handling. Apps without search use Ctrl+J/K between controls.

Defaults live in the C library, with no configuration required. Optional
`~/.config/simple/keys.ini` applies globally; `~/.config/simplexy/keys.ini`
overrides only that app (replace simplexy with its name). For example:

```ini
[interaction]
start_in_search = false
escape_closes = false

[navigation]
down = Down,j,<Control>n
up = Up,k,<Control>p
```

This example starts in navigation and makes Esc leave search before closing.
Omitted settings inherit the common default. Reopen the app after changes.
Simplepicker modules additionally support `~/.config/simplepicker/MODULE/keys.ini`.

Apps bind their search, results widget and move/activate callbacks using
`simple_ui_bind_search`, then call `simple_ui_search_start` after presentation.
Python uses `bind_search` / `start_search` from `simple_ui`. The framework owns
key dispatch and focus retention; apps provide only their result actions.

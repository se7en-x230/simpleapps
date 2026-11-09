# Keyboard controls

Use `Tab` / `Shift+Tab` to reach buttons and other controls. `Enter` / `Space`
activates the focused button; arrow keys adjust focused sliders and selectors.
An orange outline identifies the focused control. Vim shortcuts remain available
in each application's main content area. Text fields retain normal editing keys.

- **Simplefiles:** `Ctrl+Enter` confirms Open/Choose/Save from any field; `Esc`
  cancels immediately. `q` cancels outside text fields. `Enter` in the file list
  enters a folder or chooses a file. Save-overwrite confirmation initially focuses No.
- **Simplecontacts:** `/` searches; `Ctrl+j/k` selects results while search keeps
  focus; `Enter` moves focus to results. Plain `j/k` navigates outside typing.
- **Simplepdf:** `t` opens contents; Tab now navigates controls. Existing page,
  search, export, bookmark and print keys remain available.
- **Simplephoto:** adjustments and crop retain Vim keys. Blur has an arrow-key
  cursor, `Ctrl+arrows` for precision, `p/P` paint/erase and `u` undo.
- **Simpleimage, Simplenotes, Simpletimer, Simplebookmarks, Simplecapture:**
  focused buttons no longer lose Enter/Space to window-level commands.
- **Simplecalendar, Simplemail, Simpleplayer, Simpletorrent:** native GTK controls
  take priority over main-view navigation keys. Dialog controls support Tab and
  button activation; app-specific save/confirmation shortcuts remain in place.
- **Simplepicker / Simpleclip:** footer buttons can be reached and activated from
  the keyboard. Power actions retain their existing direct keys and confirmation.
- **Simple-tools:** focused sliders, selectors and buttons accept normal control
  keys; Vim card navigation remains available elsewhere.
- **Simplewallpaper:** configuration uses the keyboard-operated picker; the
  wallpaper surface itself is not an interactive window.
- **Simplepanel / dashboard:** the panel deliberately does not take typing focus.
  Open `simplepanel --system-dashboard`, `simpleplayer`, `simple-sound`,
  `simple-network bt` or `simple-calendar` using your launcher/key bindings.
  The dashboard calendar retains its keyboard navigation.
- **Simplelock:** password entry/unlock already uses the keyboard. Authentication
  behavior has not been changed by this control-navigation update.

The external region selector used by Simplecapture still uses a pointer for drawing
a rectangle; full-screen capture is available directly from its keyboard menu.
Third-party browser authorization and external editors retain their own shortcuts.

Verification includes real GTK focus/activation tests for eight Python apps,
Simplefiles Open/Cancel/search/save/multiple-selection flows, Contacts search
navigation, keyboard brush paint/erase/undo, native control tests and native builds.
This is not a claim that every external service or account operation was exercised.

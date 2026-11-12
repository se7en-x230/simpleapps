# Passwords

`simple-passwords` is a Simplepicker overlay for the running KeePassXC vault.
Dependencies: Simplepicker/shared framework, Python 3, python-dbus (Debian:
python3-dbus), PyGObject and wl-clipboard with `wl-copy --sensitive` support.
No separate database, master-password prompt, background service or mail dependency.

`/` searches title/username; Ctrl+J/K moves; Enter copies the selected password;
Ctrl+O opens KeePassXC. First Esc hides search; next Esc closes. Navigation can
be overridden in ~/.config/simplepicker/passwords/keys.ini.

Only entries in KeePassXC's exposed Secret Service group are available. Existing
Applications-group exposure is unchanged. Unlock/manage the vault in KeePassXC;
reopen the overlay afterward. Multiple exposed databases are shown with their
collection label. It does not modify entries, vault settings or login integration.

Only titles/usernames reach the UI. A secret is fetched after explicit selection,
passed to wl-copy through stdin and offered for 30 seconds with the sensitive
clipboard hint. The clipboard owner then exits without clearing newer clipboard
contents. Clipboard managers must honor that hint (cliphist does); applications
that paste a password can retain it. Core dumps are disabled. No secret logging,
files, previews or command-line arguments. This module currently requires Wayland.

KeePassXC integration: https://keepassxc.org/docs/KeePassXC_UserGuide#_secret_service_integration

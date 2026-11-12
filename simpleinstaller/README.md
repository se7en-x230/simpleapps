# Simpleinstaller

Install individual Simple apps on Linux, keeping your current desktop and personal settings. Run as your normal user with Python 3.11 or newer. Automatic package installation supports Arch/Artix through pacman. On Debian 13 and other distributions, install dependencies with your package manager, then use `--no-packages`; see the [Linux installation and source-build guide](../docs/portability.md). Builds use native libraries and distribution Python packages rather than Newinit or pip.

## Start

Unpack the source archive, enter its `simpleinstaller` folder, then run:

```sh
./simpleinstaller
```

Apps tracked by Simpleinstaller start checked. Leave them checked to keep them, check additional apps to install them, or uncheck installed apps to uninstall them. Space toggles an app; j/k or arrows move, a toggles all, Enter reviews the changes, and q cancels. Leaving everything unchanged does nothing. The list scrolls in smaller terminals. A second screen offers optional features only for newly selected apps.

The review lists installs, removals, and apps to keep before confirmation. New apps install first; a failed or cancelled install does not remove existing apps. Uninstall retains settings, personal data, modified files, and shared resources needed by remaining apps. Detection uses installer receipts; older/manual installations need one explicit `--install APP` to register their files. Use `--install APP` to update or repair an already installed app. New installations ask for shared terminal/browser/file-manager/media/mail commands; Enter keeps desktop defaults. Existing preferences are retained.

Review packages and compatibility before continuing. If packages are missing, the installer invokes `sudo pacman -Syu --needed` with a separate pacman confirmation. It uses only configured repositories and does not run an AUR helper. The full upgrade avoids partial upgrades. No package transaction happens for --plan or --check.

```sh
./simpleinstaller --list
./simpleinstaller --plan simplepicker simpleplayer --youtube --visualizer
./simpleinstaller --check all
./simpleinstaller --install simpleplayer --youtube --visualizer
./simpleinstaller --install simplecalendar --calendar-google
./simpleinstaller --install simplewallpaper --daylight
./simpleinstaller --plan all
```

`--no-packages` requires dependencies to be supplied already. `--yes` accepts app-file changes; pacman retains its own confirmation. `--source-root DIRECTORY` builds from maintained sources instead of the bundled snapshot. A normal install checks required commands, libraries and Python modules before building.

## Components

| Selection | Included | Requirements / first use |
| --- | --- | --- |
| Simplepicker | Launcher, search, keyboard menus | Standard GTK fallback; layer-shell where supported. Qalculate is optional. |
| Simpleplayer | Local music, mpv, radio, artwork, controls | Local remains the default. Cava and YouTube/yt-dlp are optional. |
| Simplecalendar | Calendar, recurrence, CalDAV sync | Connect your own account. Google support is optional; it needs your Desktop OAuth client. |
| Simplecontacts | Google Contacts and offline snapshot | Connect with your own Google Desktop OAuth client. |
| Simplemail | IMAP/SMTP frontend and account setup | Run `simplemail --setup`. Optional KeePassXC integration is not activated automatically. |
| Simpletag | Picard frontend and Simplefiles folder chooser | Requires Picard 3. Run `simpletag --setup` with Picard closed to enable the local bridge; Picard retains tagging settings. |
| Simpletorrent | Transmission frontend and backend package | Start/configure your local daemon separately. Password-authenticated RPC is not supported yet. |
| Simplewallpaper | Static or sunrise-aware wallpaper | Wayland layer-shell; not Plasma wallpaper. Generated packs are optional; configure location first. |
| Simplepanel | Status panel and system dashboard | The menu entry opens the normal GTK dashboard. The panel needs Wayland layer-shell; workspace/title controls need Mango. Install Simple tools for detail controls. |
| Simplelock | Session locker, music and calendar cards | Requires Wayland ext-session-lock-v1 and layer-shell. Uses existing `login` PAM; never auto-activated. Not an X11 or Plasma lock replacement. |
| Simple tools | Sound, network, Bluetooth, disk, CPU, memory, display and service controls | Reuses existing PulseAudio/PipeWire, NetworkManager, BlueZ, systemd/dinit and wlr-output-management capabilities. Includes the shared Picker menu engine; the Picker launcher is optional. |

Optional flags: `--calculator`, `--visualizer`, `--youtube`, `--daylight`, `--calendar-google`, `--mail-keepassxc`, `--panel-visualizer`, `--lock-visualizer`. Each requires its owning app. Optional services may need enabling/configuring through your existing distribution tools; the installer does not switch service managers.

For background calendar reminders and sync, run `simple-calendar --watch` through your own autostart/service manager. Start the panel explicitly with `simplepanel-session`. Validate Lock using `simplelock --check-config` before assigning a shortcut. No existing panel, locker or session is replaced.

## Files and settings

- Commands: `~/.local/bin`; desktop entries: `$XDG_DATA_HOME/applications`.
- Runtime resources: `$XDG_DATA_HOME/<app>`; shared themes/artwork: `$XDG_DATA_HOME/simple`.
- Preferences: `$XDG_CONFIG_HOME/simple/preferences.toml`; empty command arrays use desktop defaults. Commands are argument arrays, never shell strings.
- Artwork: `$XDG_CONFIG_HOME/simple/images.ini`. Wallpaper is optional; bundled neutral profile/idle images work without it.
- App settings: `$XDG_CONFIG_HOME/<app>`. Only missing defaults are created. Your theme, library, accounts, favourites and app choices are retained.
- Source trees: `~/.local/src`; existing maintained source trees are left alone.
- File receipts/backups: `$XDG_STATE_HOME/simpleinstaller/install-*`.

Default XDG paths are `~/.config`, `~/.local/share`, `~/.local/state` and `~/.cache`. Launchers work when `~/.local/bin` is absent from the session PATH; add it to your shell PATH for convenient terminal commands. Desktop entries use absolute command paths.

Builds are staged before app files are installed. Changed files are backed up and replaced atomically; a file-install failure restores changes from that transaction. Package-manager operations have their own lifecycle and are not rolled back by this tool. System packages remain managed by pacman.

## Uninstall

Run `./simpleinstaller`, uncheck the installed apps you want to remove, and review the plan. Alternatively:

```sh
./simpleinstaller --uninstall simpleplayer --dry-run
./simpleinstaller --uninstall simpleplayer
./simpleinstaller --uninstall all
```

Uninstall removes only tracked program/resource files whose checksums still match.
It preserves settings, accounts, personal data, modified files, maintained sources,
and system packages. Shared files stay while another tracked app needs them.
Removed files are backed up with a receipt under `$XDG_STATE_HOME/simpleinstaller`.
Apps installed by an older installer must be installed again with this version
once to register their files. Close selected apps before uninstalling; any custom
autostart entries or shortcuts you added remain yours to remove.

No personal passwords, OAuth clients/tokens, mail, calendar/contact databases, music, favourite stations, wallpaper location or hardware addresses are copied into the source bundle. It contains the original generated wallpaper image packs, not personal photos. Installation does not connect accounts, change MIME defaults, start daemons, edit PAM, modify compositor bindings or add autostart entries.

## Source bundle

```sh
./simpleinstaller --bundle simpleinstaller-source.tar.gz --source-root ~/.local/src
```

Bundling produces a small app archive and a separate archive for each daylight
theme. Share only the app archive for ordinary app tests. For daylight themes,
also put the chosen `simpleinstaller-wallpaper-THEME.tar.gz` archives beside the
extracted `simpleinstaller/` folder (for example in Downloads). Leave theme archives
compressed. The installer offers a multi-select theme menu and verifies/extracts
only selected packs before any package transaction. Static Simplewallpaper and
other apps do not require theme packs. Missing packs give instructions without
changing the system. Existing installed themes remain when adding new ones.

```sh
./simpleinstaller --list-wallpapers
./simpleinstaller --install simplewallpaper --daylight --wallpaper-themes matrix-monk sea-monk
```

Use `--wallpaper-themes all` for every theme. Use `--wallpaper-pack DIRECTORY` for
archives stored elsewhere (or a single archive path when selecting one theme).
Theme downloads are currently local archives; automatic hosted downloads are not
yet configured. Future themes can be published as separate release assets without
adding large image files to the app Git repository.

The app bundle includes current source, shared resources, neutral defaults and recipes. Compiled binaries, objects, caches and version-control data are excluded. `SHA256.json` is checked before using a bundle; it detects changed/corrupt files, not publisher identity. Keep the unpacked folder to run the installer again.

Maintainers can run `python3 tests/check.py` and `python3 tests/suite.py` from a source checkout containing `sources/`. GUI and fresh-home integration checks are run separately and never activate the user's lock screen or connect personal accounts.

## Individual app installers

Export a standalone installer containing only one app and its shared dependencies:

```sh
./simpleinstaller --bundle simpleplayer-installer.tar.gz --bundle-app simpleplayer
```

The archive extracts to `simpleplayer-installer/`. Run `./install` there to select
optional features and install the app, or `./uninstall` to remove only this app.
The full suite installer continues to support selecting several apps. All bundles
share the installation registry so shared components are retained when needed.
Only the Simplewallpaper bundle exports optional theme archives.

## License

Original Simpleapps code is licensed under GPL-3.0-or-later (GNU GPL version 3 or any later version). See the repository’s LICENSE and COPYING files. Third-party components retain their own licenses and notices.

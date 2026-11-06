# Simple apps

Small Linux desktop applications with a shared visual style. Install the apps you want individually.

All apps support Vim-style key bindings, and almost every function can be used from the keyboard. See each app’s page for its shortcuts.

## Apps and screenshots

Click a screenshot or app name for features, installation and keyboard controls.

| [Simplelock](docs/simplelock.md) | [Simplewallpaper](docs/simplewallpaper.md) |
| :---: | :---: |
| [![Simplelock screenshot](docs/screenshots/simplelock.png)](docs/simplelock.md) | [![Simplewallpaper screenshot](docs/screenshots/simplewallpaper-matrix-afternoon.png)](docs/simplewallpaper.md) |
| Wayland session lock with music and calendar | Static and sunrise-aware Wayland wallpaper |

| [SimplePhoto](docs/simplephoto.md) | [Simpleplayer](docs/simpleplayer.md) |
| :---: | :---: |
| [![SimplePhoto screenshot](docs/screenshots/simplephoto-landscape.png)](docs/simplephoto.md) | [![Simpleplayer screenshot](docs/screenshots/simpleplayer.png)](docs/simpleplayer.md) |
| Photo adjustments, cropping and Vim-style controls | Music library, artwork and mpv playback |

| [Simplecalendar](docs/simplecalendar.md) | [Simplepicker](docs/simplepicker.md) |
| :---: | :---: |
| [![Simplecalendar screenshot](docs/screenshots/simplecalendar.png)](docs/simplecalendar.md) | [![Simplepicker screenshot](docs/screenshots/simplepicker.png)](docs/simplepicker.md) |
| Calendar, recurring events and CalDAV sync | Application launcher, search and keyboard menus |

| [System dashboard](docs/simplepanel.md) | [Simplepanel](docs/simplepanel.md) |
| :---: | :---: |
| [![System dashboard screenshot](docs/screenshots/simplepanel.png)](docs/simplepanel.md) | [![Simplepanel screenshot](docs/screenshots/simplepanel-bar.png)](docs/simplepanel.md) |
| System resources, world clocks and market prices | Compact desktop status panel |

| [Simplemail](docs/simplemail.md) | [Simplecontacts](docs/simplecontacts.md) |
| :---: | :---: |
| [![Simplemail screenshot](docs/screenshots/simplemail.png)](docs/simplemail.md) | [![Simplecontacts screenshot](docs/screenshots/simplecontacts.png)](docs/simplecontacts.md) |
| Native IMAP/SMTP mail and account setup | Google contacts with an offline local copy |

| [Simpletorrent](docs/simpletorrent.md) | [Simple tools](docs/simple-tools.md) |
| :---: | :---: |
| [![Simpletorrent screenshot](docs/screenshots/simpletorrent.png)](docs/simpletorrent.md) | [![Simple tools screenshot](docs/screenshots/simple-tools.png)](docs/simple-tools.md) |
| Transmission download controls | Sound, network, disks, displays and services |

| [Simpleimage](docs/simpleimage.md) | [Simplepdf](docs/simplepdf.md) |
| :---: | :---: |
| [![simpleimage screenshot](docs/screenshots/simpleimage.png)](docs/simpleimage.md) | [![simplepdf screenshot](docs/screenshots/simplepdf.png)](docs/simplepdf.md) |
| Image viewing, thumbnails, printing and Simplephoto editing | PDF reading, search, bookmarks and export tools |

| [Simplefiles](docs/simplefiles.md) | [Simplenotes](docs/simplenotes.md) |
| :---: | :---: |
| [![simplefiles screenshot](docs/screenshots/simplefiles.png)](docs/simplefiles.md) | [![simplenotes screenshot](docs/screenshots/simplenotes.png)](docs/simplenotes.md) |
| Portable file picker with previews and Vim keys | Plain-text notes with instant search and autosave |

| [Simpleclip](docs/simpleclip.md) | [Simplecapture](docs/simplecapture.md) |
| :---: | :---: |
| [![simpleclip screenshot](docs/screenshots/simpleclip.png)](docs/simpleclip.md) | [![simplecapture screenshot](docs/screenshots/simplecapture.png)](docs/simplecapture.md) |
| Searchable cliphist history with previews | Screenshots, annotation and optional screen recording |

| [Simpletimer](docs/simpletimer.md) | [Simplebookmarks](docs/simplebookmarks.md) |
| :---: | :---: |
| [![Simpletimer screenshot](docs/screenshots/simpletimer.png)](docs/simpletimer.md) | [![Simplebookmarks screenshot](docs/screenshots/simplebookmarks.png)](docs/simplebookmarks.md) |
| Countdown, stopwatch, Pomodoro, fasting and meditation with soft bells | Search, open and manage bookmarks with Vim keys |

## Install from this checkout

The installer currently supports **Arch-based Linux with Python 3 and pacman**. GTK apps can run on other desktops; wallpaper, panel and lock features need the Wayland protocols listed on their app pages.

```sh
./install --plan simpleplayer
./install --install simpleplayer
```

Run as your normal user; package installation uses sudo. The installer builds sources locally. Commands go into `~/.local/bin`; add that directory to PATH if needed. Installation does not replace your desktop or enable services, account sync, autostart or key bindings.

```sh
./install --uninstall simpleplayer
```

Uninstallation retains settings, personal data, modified files and shared resources used by remaining apps. System packages and source copies are retained.

## Individual installer archives

Create a portable source installer for one app:

```sh
mkdir -p releases
./install --bundle releases/simpleplayer-installer.tar.gz --bundle-app simpleplayer
```

The archive includes required shared code, `install` and `uninstall`. Generated release archives are excluded from Git. Wallpaper theme packs are optional and separate; this checkout includes no large theme collection. You can use your own wallpaper images. See [Simplewallpaper](docs/simplewallpaper.md).

## How the apps are built

These are native Linux desktop apps, primarily using GTK, with C and Python implementations. Python apps use PyGObject to access GTK; C components call native libraries directly. Simpleclip combines a Python launcher with the shared C clipboard interface. Simplecapture combines Python and a shell recording helper.

Established libraries and tools handle the heavy work: Poppler renders PDFs, GdkPixbuf loads images, Pillow/NumPy process photos, mpv plays media, and grim/Swappy/wf-recorder handle capture. Dependencies vary by app; installing one does not require the whole suite.

The apps share visual and keyboard conventions and a common installer. They do not yet use one uniform UI codebase or configuration format. Runtime settings live under XDG config directories, normally `~/.config`; installed source snapshots live under `~/.local/src`. See each app’s page for its settings and portability limits.

## Source layout

Each app has its own directory. `simple-common` holds shared code and small fallback images. `simpleinstaller` contains package recipes, default configuration and uninstall tracking. Keep sibling source directories together when building manually; individual archives include the siblings they require.

Existing component README files describe developer details and may mention shortcuts from the original desktop setup. Those shortcuts are not assigned by installation.

## Licensing

Existing third-party copyright and license notices are retained in the source files. A project-wide distribution license has not yet been selected.

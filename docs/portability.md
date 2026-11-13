# Install and build on Linux

Simpleapps is a collection of independent Linux desktop tools built with C, Python
and GTK4. Install just the apps you need. Their shared Simple UI library supplies
consistent colors, controls and keyboard navigation without running a background
framework service.

The source installer requires **Python 3.11 or newer**. GTK apps require **GTK 4.12
or newer**, a C compiler, Make and pkg-config, including the Python apps: their
shared UI base is compiled locally. Use a graphical session to run the apps.

## Debian 13 (Trixie)

Debian 13 supplies suitable [GTK4 development files](https://packages.debian.org/trixie/libgtk-4-dev).
Stock Debian 12 has GTK 4.8 and does not meet the current minimum. Do not mix
Debian releases to satisfy dependencies; use a supported newer system or an
isolated development environment.

### Get the source and install the common dependencies

```sh
sudo apt update
sudo apt install git build-essential pkg-config python3 python3-gi \
  python3-gi-cairo python3-cairo libgtk-4-dev gir1.2-gtk-4.0 \
  libglib2.0-dev xdg-utils libnotify-bin

git clone https://github.com/se7en-x230/simpleapps.git
cd simpleapps
```

### Install a few standalone apps

These apps use the common dependencies above:

```sh
./install --check simpletimer simplenotes simplefiles simplebookmarks
./install --no-packages --install simpletimer simplenotes simplefiles simplebookmarks
export PATH="$HOME/.local/bin:$PATH"
simpletimer
```

Run the installer as your normal user. `--no-packages` uses dependencies already
installed by apt; it does not call pacman or change your package manager. Add the
PATH line to your shell configuration if `~/.local/bin` is not already present.

### Add the picker and clipboard tools

```sh
sudo apt install libjson-c-dev libgtk4-layer-shell-dev wl-clipboard cliphist file
./install --check simplepicker simpleclip
./install --no-packages --install simplepicker simpleclip
simplepicker --apps
```

The picker requires gtk4-layer-shell >= 1.0; Debian 13 provides
[version 1.0.4](https://packages.debian.org/trixie/libgtk4-layer-shell-dev).
Clipboard features require a Wayland session and a cliphist history populated by
your desktop. Optional picker features need their helpers, such as `qalc`,
`wtype` and `ffmpeg`; see `./install --dependencies simplepicker`.

### Dependencies for additional apps

Install only the rows you need, then run `./install --check APP` followed by
`./install --no-packages --install APP`. This table lists additions to the common
packages above. Package names in `--dependencies` are currently Arch names;
its module, command and Python checks are useful on every distribution.

| App | Additional Debian packages / requirements |
| --- | --- |
| Simpleimage | `libgdk-pixbuf-2.0-dev`, `gir1.2-gdkpixbuf-2.0` |
| Simplephoto | `python3-pil`, `python3-numpy` |
| Simplepdf | `libpoppler-glib-dev`, `gir1.2-poppler-0.18` |
| Simplecapture | `grim`, `slurp`, `swappy`, `wl-clipboard`; a compatible Wayland compositor |
| Simpleplayer | `libjson-c-dev`, `mpv`, `ffmpeg`, `util-linux`, `bash`, `coreutils`, `findutils` |
| Simplecalendar | `libjson-c-dev`, `python3-icalendar`, `python3-recurring-ical-events`, `python3-requests`, `vdirsyncer` |
| Simplecontacts | `libjson-c-dev`, `python3-google-auth`, `python3-requests`, `wl-clipboard` |
| Simplemail | `libjson-c-dev`, `python3-cryptography`; configure your mail account after installation |
| Simpletorrent | `libjson-c-dev`, `libcurl4-openssl-dev`, `transmission-daemon`; configure and start Transmission separately |
| Simplepanel | `libjson-c-dev`, `libgtk4-layer-shell-dev`, `libpulse-dev`, `curl`, `fastfetch` |
| Simple tools | `libjson-c-dev`, `libgtk4-layer-shell-dev`, `pulseaudio-utils`, `network-manager`, `bluez`, `util-linux`, `wlr-randr`, `wl-clipboard`, `sudo`, `iproute2` |
| Simplegarmin | Common dependencies; Garmin credentials are needed only to retrieve account data |
| Simpleslideshow | `ffmpeg`, `python3-gi`, `python3-cairo`, `python3-gi-cairo`, `libgtk-4-media-gstreamer`, `gstreamer1.0-plugins-base`, `gstreamer1.0-plugins-good` |
| Simpletag | MusicBrainz Picard, **`picard-cli`**, and `fpcalc` (Debian: `libchromaprint-tools`); verify that your Picard version supplies the CLI |
| Simplewallpaper | **`awww` and `awww-daemon`**, ImageMagick with **`magick`**; obtain compatible upstream builds if your distribution does not package those commands |
| Simplelock | `libjson-c-dev`, `libpam0g-dev`, and **gtk4-layer-shell >= 1.2**; Debian 13's stock 1.0.4 package is insufficient |

Some optional commands are not packaged in every distribution or release. Do not
assume that installing a similarly named package supplies the required version.
`./install --check APP` reports missing components before you install an app.
Simplelock also needs the compositor's `ext-session-lock-v1` protocol. Test it
carefully in your own session; installation never replaces your existing locker.

## Arch / Artix

Automatic system-package installation is implemented for pacman-based systems:

```sh
git clone https://github.com/se7en-x230/simpleapps.git
cd simpleapps
./install --plan simpletimer simplepicker
./install --install simpletimer simplepicker
```

The installer uses configured repositories and requests a full package upgrade
when packages are missing. It does not invoke an AUR helper. You can also manage
packages yourself and use `--no-packages`.

## Other distributions: build from source

Use your distribution's package manager to install:

1. A C toolchain, Make, pkg-config and Python >= 3.11.
2. GTK >= 4.12 **development headers and pkg-config files**.
3. PyGObject GTK4 bindings for Python apps, plus each app's runtime dependencies.
4. The additional libraries listed above for the apps you select.

Library names such as `gtk4`, `json-c`, `poppler-glib`, `libcurl`,
`libpulse-mainloop-glib` and `gtk4-layer-shell-0` are pkg-config module names;
your distribution may name the corresponding development packages differently
(`-dev` on Debian, often `-devel` elsewhere).

From the cloned checkout:

```sh
python3 --version
pkg-config --modversion gtk4
./install --dependencies simpletimer
./install --check simpletimer
./install --no-packages --install simpletimer
```

The source installer builds the shared library and app, installs launchers and
resources, and preserves existing settings. Keep the checkout's sibling
`simple-common` directory: copying an app directory alone is not sufficient.

### Direct Makefile builds

For native components, build without installing:

```sh
make -C simple-common
make -C simplepicker check-deps
make -C simplepicker
./simplepicker/simplepicker-native --apps
```

The shared library is found beside the source checkout. For a direct user install:

```sh
make -C simplepicker install PREFIX="$HOME/.local"
"$HOME/.local/bin/simplepicker-native" --apps
```

This Makefile also installs the shared library. It installs `simplepicker-native`,
not a `simplepicker` alias. For the complete launcher/resource setup of other apps,
prefer the source installer above rather than copying only the executable.

Custom prefixes and package staging are available through the native Makefiles:

```sh
make -C simplepicker install PREFIX=/usr DESTDIR="$PWD/package-root"
```

`DESTDIR` is a packaging staging directory, not the runtime prefix. The shared
library and styles are installed under `PREFIX/lib/simple-common`. Rebuild for
each target architecture/distribution; the resulting binary is not universal.

## Desktop compatibility

Normal GTK windows can run on compatible Linux graphical desktops. Layer-shell
panels and wallpaper, Wayland clipboard tools, screen capture, and session locking
need the respective compositor protocols. Mango workspace/window actions are
Mango-specific. Sound and networking tools use your existing PipeWire/PulseAudio,
NetworkManager and BlueZ services; the installer does not enable or replace them.

## Uninstall and verification

```sh
./install --uninstall simpletimer
```

Settings, personal data, modified files and shared resources still used by other
apps are retained. System packages stay under your distribution's package manager.

Verification includes building all 21 apps on the development host, isolated
staging, demo-profile screenshots, and repository checks. Debian package/version
references have been checked, but a full build/run on a real Debian installation
has not yet been verified.

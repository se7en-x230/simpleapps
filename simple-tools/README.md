# Simple tools

## Shared base and portable installation

Uses the shared C/GTK4 base in `simple-common`. Python UI code calls the same native library through a thin adapter. Shared theme and keyboard adapters replace separate implementations; app-specific commands and content remain local.

Requires Linux and Python 3.11+ for the source installer. Building the shared base requires a C compiler, make, pkg-config and GTK4 >= 4.12 development files. Install dependencies using your distribution’s package manager; package names can differ.

- Libraries / pkg-config modules: `gtk4 >= 4.12`, `gtk4-layer-shell-0`, `gio-unix-2.0`, `json-c`.
- Python imports: `gi`.
- Required commands: `python3`, `pactl`, `nmcli`, `lsblk`, `wlr-randr`, `cc`, `make`, `pkg-config`.
- Desktop requirements: Sound: PulseAudio/PipeWire; network: NetworkManager; displays: wlr-output-management; services: systemd/dinit..

From the suite checkout (no pacman or distro detection on this path):

```sh
./install --dependencies simple-tools
./install --check simple-tools
./install --no-packages --install simple-tools
```

To build a relocatable staging tree without changing your installation:

```sh
./install --install simple-tools --stage "$PWD/package-simple-tools"
```

Keep `simple-common` alongside the app sources. Staged files are under `.local/`; move that prefix as a unit so executables, shared libraries and resources stay together. Individual C Makefiles also accept `PREFIX`/`DESTDIR` where documented. See [portable builds](../docs/portability.md) for Debian/Arch dependency examples and limitations.

System menu search: the root menu searches all configured actions, including
actions inside categories. Results show their category and launch directly.
An empty query keeps the original category layout; submenu navigation is unchanged.

Optional [Passwords overlay](passwords/README.md): `simple-passwords` searches the
existing KeePassXC Secret Service group. Requires python-dbus and wl-clipboard;
it uses the same Simplepicker UI and never creates another password store.

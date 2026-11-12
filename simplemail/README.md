# Simplemail

## Shared base and portable installation

Uses the shared C/GTK4 base in `simple-common`. Python UI code calls the same native library through a thin adapter. Shared theme and keyboard adapters replace separate implementations; app-specific commands and content remain local.

Requires Linux and Python 3.11+ for the source installer. Building the shared base requires a C compiler, make, pkg-config and GTK4 >= 4.12 development files. Install dependencies using your distribution’s package manager; package names can differ.

- Libraries / pkg-config modules: `gtk4 >= 4.12`, `json-c`.
- Python imports: `gi`, `cryptography`.
- Required commands: `cc`, `make`, `pkg-config`, `python3`.
- Optional KeePassXC credential integration: `keepassxc`, `dbus`.
- Desktop requirements: GTK desktop.

From the suite checkout (no pacman or distro detection on this path):

```sh
./install --dependencies simplemail
./install --check simplemail
./install --no-packages --install simplemail
```

To build a relocatable staging tree without changing your installation:

```sh
./install --install simplemail --stage "$PWD/package-simplemail"
```

Keep `simple-common` alongside the app sources. Staged files are under `.local/`; move that prefix as a unit so executables, shared libraries and resources stay together. Individual C Makefiles also accept `PREFIX`/`DESTDIR` where documented. See [portable builds](../docs/portability.md) for Debian/Arch dependency examples and limitations.

# Simplewallpaper

Optional, standalone static and daylight wallpaper application for Linux/Wayland. No Newinit or Mango dependency. `wallpaper-set` remains a compatibility launcher for existing shortcuts and services.

## Commands

- `simplewallpaper` or `simplewallpaper --menu`: choose images, daylight mode, location or fade duration.
- `simplewallpaper /path/to/image`: set a static image.
- `simplewallpaper --location LAT LON --name NAME`: configure sunrise/sunset location explicitly.
- `simplewallpaper --theme-directory /path/to/folder`: enable daylight images from a personal folder containing `06.png` through `17.png` and `night.png`.
- `simplewallpaper --restore`: restore the configured wallpaper at login.
- `simplewallpaper --status`: read-only status. Daylight previews accept `--at` with an ISO timestamp and UTC offset.

Existing named theme packs remain usable if present. They are personal assets, not part of the distributable defaults. Daylight means scheduled still images with smooth fades; this is not a video wallpaper engine.

## Dependencies for the installer

| Capability | Requirements |
|---|---|
| Core CLI/configuration | Python 3, Linux |
| Static wallpaper | Wayland; `awww` + `awww-daemon`, or `swaybg`; ImageMagick for image import |
| Daylight scheduling/fades | `python-astral`, `awww` + `awww-daemon`; user-supplied location and theme images |
| Graphical selection menu | Optional Simplepicker |
| Terminal menu | No picker required; common `simple-open` can open the terminal when launched from a desktop entry |
| Default artwork | Shared Simple image resources; no wallpaper-specific package required by other apps |

Nothing installs/enables a service automatically. Existing wallpaper dinit/systemd user services can be reused. Otherwise the app starts a detached worker with a single-instance lock; it exits when its Wayland display disappears or changes. A login integration must invoke `--restore` on the next session. No compositor configuration is installed by this app.

## Layout and compatibility

Code: `~/.local/src/simplewallpaper` in the maintained development layout. The launcher also supports installation-relative `share/simplewallpaper`, XDG data resources, or `SIMPLEWALLPAPER_SOURCE`.

New accounts use `$XDG_CONFIG_HOME/simplewallpaper/config.json`, `$XDG_DATA_HOME/simplewallpaper`, and `$XDG_STATE_HOME/simplewallpaper`. Existing `wallpaper` configuration/data/state locations remain supported so upgrades preserve themes and the worker lock. Explicit overrides: `SIMPLEWALLPAPER_CONFIG`, `SIMPLEWALLPAPER_DATA`, `SIMPLEWALLPAPER_STATE`.

The app publishes the selected desktop image as `$XDG_DATA_HOME/simplewallpaper/current`. Consumers only read that file. They do not import the wallpaper app, start its worker or require a renderer.

Shared `simple/images.ini` controls fallback/profile artwork. Removing Simplewallpaper must retain personal configuration/data unless explicitly requested, and must not remove shared Simple image resources.

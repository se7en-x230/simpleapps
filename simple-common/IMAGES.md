# Shared image contract

Configuration: `$XDG_CONFIG_HOME/simple/images.ini` (normally `~/.config/simple/images.ini`).

```ini
[images]
profile =
idle =
use_wallpaper = true
```

Paths may be absolute, start with `~/`, or be relative to this `simple` configuration folder. Empty values use fallbacks. A missing file also falls back.

For idle artwork: configured idle image → optional published wallpaper → compatible legacy wallpaper → bundled default. `use_wallpaper = false` skips both wallpaper sources. For profile artwork: configured profile → bundled avatar. Real album artwork takes precedence during playback in Player and Lock.

Default PNGs live in `$XDG_DATA_HOME/simple/images` or a system XDG data directory. `SIMPLE_IMAGES_DIR` can override the asset directory. Their editable SVG sources are retained under `simple-common/assets/images`; PNG consumers need no SVG loader.

The small Python module `simple_images.py` and native `simple-images.h` implement the same lookup order. `daylight-art.h` caches decoded native images and refreshes when the selected image changes. These belong to common Simple resources, not the optional wallpaper application.

Installer requirements: ship the shared resources with every app that consumes them, track common ownership, and never bundle personal profile pictures or theme folders as defaults. Player's standalone install already includes its Python resolver and the two default PNGs. Native consumers need the two PNGs at the shared data location. No renderer, scheduler, Newinit or compositor-specific commands are needed to display fallback artwork.

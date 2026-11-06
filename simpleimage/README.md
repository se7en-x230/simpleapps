# Simpleimage

A small GTK4 image viewer with a clean Simpleapps theme, asynchronous image loading, a bounded memory cache and a virtualized thumbnail grid. Gold title, dark background and dark red thumbnail selection. No nsxiv, Yazi, X11 or ImageMagick dependency.

```sh
./install --install simpleimage
simpleimage photo.jpg
simpleimage /path/to/photos
simpleimage one.jpg two.png
simpleimage --check-config
```

Opening one image browses supported images in its folder in natural filename order, starting at that image. Passing multiple files preserves their order. Folder discovery and image decoding run outside the GTK thread; obsolete navigation results cannot replace the selected image. Thumbnails load as GTK binds visible grid cells, with cancellation when cells are recycled.

Requires Python 3.11+, PyGObject, Pycairo with GI integration, GTK4 >= 4.12 and GdkPixbuf. Format support follows installed GdkPixbuf loaders; animated files display a still frame. EXIF orientation is applied. This is not an HDR or colour-proofing viewer; embedded ICC profiles are not explicitly converted. Very large images are decoded down to max_dimension for bounded display size; originals remain unchanged. Some format loaders may still need full-resolution intermediate memory during decoding.

Settings: `$XDG_CONFIG_HOME/simpleimage/config.toml` (normally `~/.config/simpleimage/config.toml`). Created on first launch:

```toml
window_width = 1100
window_height = 760
browse_folder = true
show_hidden = false
slideshow_seconds = 5
cache_mb = 128
max_dimension = 8192
thumbnail_width = 174
thumbnail_height = 120
thumbnail_large_width = 300
thumbnail_large_height = 208
editor = ["simplephoto"]
```

The editor is an argument list executed without a shell. Programs resolve through PATH; `~` and environment variables expand in arguments. Simplephoto is optional and installed separately. Viewing works without it. The cache limit covers retained source images; the current display texture/rotation and a separate 16 MiB thumbnail cache use additional memory. No persistent thumbnail database or background service is created.

## Keys

- n/Space and p/Backspace: next/previous image; gg/G: first/last.
- h/j/k/l: pan; in the grid, move between thumbnails. Arrow keys also work.
- +/−: zoom; =: fit without enlarging small images; 1: decoded pixels at 100%.
- z in thumbnail view: toggle standard (174×120) / large (300×208). Each launch starts at standard size.
- Enter: thumbnail grid; Enter in the grid: open selected thumbnail; m: mark/unmark.
- Ctrl+p: print marked images (or the selected image) through the GTK print dialog, one image per page. Prints original resolution with EXIF orientation and fit-to-page; preview rotation/mirroring does not alter the print.
- e: open marked images (or the current image) in Simplephoto; r or the Refresh button: reload the image/folder. Simplephoto saves notify the viewer immediately: the saved copy appears and becomes selected, including in the thumbnail grid. Other configured editors refresh the folder when their process exits.
- R: rotate view; x: mirror view. Neither changes the file.
- f: fullscreen; b: hide/show bars; s: slideshow.
- y or Ctrl+x: copy marked/current paths; Y or Ctrl+c: copy the displayed image.
- i: basic file/image information; o: native Open dialog; ?: controls; Esc/q: close.

The native file chooser uses Simplefiles where the desktop portal is configured, otherwise the desktop's chooser. Clipboard image copies reflect the decoded view, including rotation/mirroring; keep the viewer open until pasted. Detailed EXIF editing, conversion, wallpaper setting and trash actions stay with existing external tools in this first version. It does not modify or delete originals.

The installer supplies a menu entry, sources and uninstall receipt without changing desktop associations. Run check.py for file ordering/cache tests and check-gui.py in an isolated graphical session for decoding and UI tests.

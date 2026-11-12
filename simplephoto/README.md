# SimplePhoto

A small GTK4 photo editor: one large image view, compact adjustments, crop, before/after and keyboard controls. Works independently of any file manager or compositor.

Run `./simplephoto [--crop] [FILE ...]`. Without a filename, an Open dialog appears. Requires Python, PyGObject/GTK4, Cairo, Pillow with LittleCMS, and NumPy. Install from the repository root with `./install --install simplephoto`; remove with `./install --uninstall simplephoto`.

Brightness, contrast, highlights, shadows, saturation, vibrance, warmth and tint start at zero. The baseline is the original photograph's existing processing, not a reproduction of Google's proprietary Pixel algorithms. Embedded colour profiles are converted to sRGB before editing and previewing. Unsupported or invalid profiles produce an error instead of silently being ignored.

Save creates a full-resolution copy alongside the source, numbered `photo~1.jpg`, `photo~2.jpg`, etc. Existing versions are skipped. Filesystems without hard-link support (such as cloud mounts) use an exclusive copy instead. The crop and adjustments are combined in one export. Originals are never overwritten. JPEG/WebP use quality 95; other supported stills save as PNG. These are SDR exports; HDR gain maps and Motion Photo video are not preserved. Basic EXIF and the working colour profile are retained; these can include location metadata. Files changed since opening are rejected when saving.

## Keys

| Key | Action |
| --- | --- |
| `j/k`, Down/Up | Select next/previous adjustment |
| `h/l`, Left/Right | Decrease/increase selected value |
| Shift + h/l | Change by 10 |
| `g/G` | First/last adjustment |
| `0` | Reset selected adjustment |
| `r` | Reset adjustments; crop mode: full image; brush mode: clear mask |
| `v` | Original/edited view |
| `b` | Fullscreen blur brush |
| `c` | Toggle crop mode |
| `t` / `Shift+t` | Rotate right/left 90° |
| `x` / `Shift+x` | Mirror left/right or top/bottom |
| Drag in crop mode | Select a crop |
| `h/j/k/l` in crop mode | Move crop by 1% of image width/height |
| Shift + movement in crop mode | Resize bottom/right edge |
| Ctrl + movement in crop mode | Precise one-source-pixel steps |
| `f` in crop mode | Toggle fast 5% steps |
| `z` / `Shift+z` in crop mode | Shrink/grow crop around its centre |
| `+` / `-` (including keypad) | Grow/shrink crop around its centre |
| Enter in crop mode | Apply crop to preview and return to adjustments |
| `s`, Ctrl+s | Save a separate copy with crop and adjustments |
| `o` | Open another photo |
| `n`, `]` | Next supplied photo |
| `q`, Escape | Close; Escape leaves crop mode first |
| `?` | Show key help |

Adjustments and crop reset for each new image. Saving always exports edits, even while viewing the original with `v`. Switching files or closing discards unsaved adjustments; the source is untouched.

Crop mode starts with a centred selection; no mouse is required. Holding a movement key updates only the selection overlay, keeping movement responsive.

## Manual blur brush

Press `b` or **Blur** to enter the fullscreen brush view. Only brush size and blur strength remain visible. Press `b`, Enter or Escape to return to the editor. `v` compares original and edited.

Drag over areas to blur; red is the selection overlay. Hold **Shift while painting to deselect** (erase blur). Hold **Space** to zoom 3× around the pointer; release Space to fit the whole image. Shift-erasing works while Space is held. Releasing Space ends the current stroke so it cannot jump across the image.

`[` / `]` or `j/k` adjust brush diameter. `h/l` adjusts blur strength (Shift steps by 10); `0` disables blur. `m` toggles the overlay, `u` or Ctrl+z undoes up to 20 mask edits, and `r` clears the selection.

Brush mode shows the full photograph so a mask remains aligned when the crop changes. Crop and mask are applied together on save, without the red overlay. Edges are feathered. The mask uses preview resolution and is scaled on export; zoom helps positioning but does not add mask detail. AI detection and its model are not included.

## Zoom and focused crop view

The main view has two rows of five sliders: eight tone/colour controls, blur amount, and Zoom. Zoom ranges from 100% (fit the image in the window) to 400% of that fitted view. It is view-only and never changes export dimensions. Drag the zoomed image to pan; `0` on Zoom restores fit.

`c` opens a dedicated fullscreen crop view with the adjustments hidden. It shows crop dimensions, Done and Full image buttons, and one crop-specific key-help line. `h/j/k/l` move, Shift resizes, `f` toggles fast steps, Ctrl gives pixel precision, and Enter/Escape returns to adjustments. Each mode displays its own relevant key hints.

Rotation and mirror shortcuts are listed in the bottom key guide. Crops, painted blur masks and mask-undo history follow each transform. Comparison (`v`) shows the original untransformed photo. Saving combines transforms and edits into a separate numbered copy.

## Shared base and portable installation

Uses the shared C/GTK4 base in `simple-common`. Python UI code calls the same native library through a thin adapter. Shared theme and keyboard adapters replace separate implementations; app-specific commands and content remain local.

Requires Linux and Python 3.11+ for the source installer. Building the shared base requires a C compiler, make, pkg-config and GTK4 >= 4.12 development files. Install dependencies using your distribution’s package manager; package names can differ.

- Libraries / pkg-config modules: `gtk4 >= 4.12`.
- Python imports: `gi`, `cairo`, `PIL`, `numpy`.
- Required commands: `python3`, `cc`, `make`, `pkg-config`.
- Desktop requirements: GTK desktop; local SDR editing.

From the suite checkout (no pacman or distro detection on this path):

```sh
./install --dependencies simplephoto
./install --check simplephoto
./install --no-packages --install simplephoto
```

To build a relocatable staging tree without changing your installation:

```sh
./install --install simplephoto --stage "$PWD/package-simplephoto"
```

Keep `simple-common` alongside the app sources. Staged files are under `.local/`; move that prefix as a unit so executables, shared libraries and resources stay together. Individual C Makefiles also accept `PREFIX`/`DESTDIR` where documented. See [portable builds](../docs/portability.md) for Debian/Arch dependency examples and limitations.

## License

Original Simpleapps code is licensed under GPL-3.0-or-later (GNU GPL version 3 or any later version). See the repository’s LICENSE and COPYING files. Third-party components retain their own licenses and notices.

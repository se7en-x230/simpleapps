# Simplepdf

A portable GTK4 PDF reader with the Simpleapps theme and familiar Zathura/Vim controls. Uses Poppler for PDF rendering; no Zathura or Yazi dependency. One page at a time, rendered at the chosen zoom, without loading a document full of image thumbnails.

```sh
./install --install simplepdf
simplepdf document.pdf
simplepdf --check-config
```

Requires Python 3.11+, PyGObject, Pycairo (including GI Cairo integration), GTK4 and Poppler's introspection bindings. `--pdf-tools` adds pdftotext and qpdf for exports. `--pdf-ocr` adds OCRmyPDF and English Tesseract data; install other Tesseract languages separately.

The Open and Save dialogs use the native file chooser/desktop portal, so they use Simplefiles where configured, and the platform chooser elsewhere.

Settings are created in `$XDG_CONFIG_HOME/simplepdf/config.toml`, normally `~/.config/simplepdf/config.toml`:

```toml
window_width = 900
window_height = 760
fit = "page"
remember_position = true
scroll_step = 60
ocr_language = "eng"
state_dir = ""
```

An empty state_dir uses `$XDG_STATE_HOME/simplepdf`. Custom paths support tilde/environment expansion; relative paths resolve against the config folder. Private state records the last page, zoom, fit, rotation and named bookmarks per document path. No personal paths are bundled.

## Keys

- h/j/k/l scroll; d/u half-page; Ctrl+d/u, PageDown/PageUp or Space/Backspace change pages.
- gg/G first/last page; a number then G or `:` jumps to a page.
- J/K or −/+ zoom; ;w fits width; ;p fits the page.
- / searches; n/N selects the next/previous highlighted match.
- R rotates the view; i inverts colours; r reloads; p prints.
- ;b adds a named bookmark; ;l lists bookmarks; Tab opens the PDF contents; f lists links for keyboard selection.
- o opens; y copies the current page's text; ? lists controls.
- ;t extracts text; ;e extracts page ranges; ;c compresses; ;o runs OCR.
- Esc dismisses an input/prefix, otherwise closes; q closes. Popup lists use j/k and Enter.

PDF tools run in the background with a completion/error message. Closing is blocked while an export is active. Outputs must use new filenames, published atomically without replacing an existing file. Compression is lossless and may not reduce every PDF. Export tools can be installed separately; missing tools produce an error without affecting reading.

This first version focuses on reading and export. It does not yet edit annotations, fill forms, select text with the mouse, or show continuous/two-page spreads. Internal links are clickable in the unrotated view; external web/mail links ask before opening. Rotation and colour inversion affect the view, not the saved PDF. Password-protected documents can be opened; external exports may require a decrypted copy. Printing uses GTK's print dialog.

Install/uninstall uses the standard Simpleinstaller receipts. It does not change default PDF associations or compositor keys.

## Shared base and portable installation

Uses the shared C/GTK4 base in `simple-common`. Python UI code calls the same native library through a thin adapter. Shared theme and keyboard adapters replace separate implementations; app-specific commands and content remain local.

Requires Linux and Python 3.11+ for the source installer. Building the shared base requires a C compiler, make, pkg-config and GTK4 >= 4.12 development files. Install dependencies using your distribution’s package manager; package names can differ.

- Libraries / pkg-config modules: `gtk4 >= 4.12`, `poppler-glib`.
- Python imports: `gi`, `cairo`.
- Required commands: `python3`, `cc`, `make`, `pkg-config`.
- Optional PDF text/page extraction and lossless compression: `pdftotext`, `qpdf`.
- Optional Searchable PDF OCR: `ocrmypdf`.
- Desktop requirements: GTK desktop; Poppler PDF rendering.

From the suite checkout (no pacman or distro detection on this path):

```sh
./install --dependencies simplepdf
./install --check simplepdf
./install --no-packages --install simplepdf
```

To build a relocatable staging tree without changing your installation:

```sh
./install --install simplepdf --stage "$PWD/package-simplepdf"
```

Keep `simple-common` alongside the app sources. Staged files are under `.local/`; move that prefix as a unit so executables, shared libraries and resources stay together. Individual C Makefiles also accept `PREFIX`/`DESTDIR` where documented. See [portable builds](../docs/portability.md) for Debian/Arch dependency examples and limitations.

## License

Original Simpleapps code is licensed under GPL-3.0-or-later (GNU GPL version 3 or any later version). See the repository’s LICENSE and COPYING files. Third-party components retain their own licenses and notices.

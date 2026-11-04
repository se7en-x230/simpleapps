# Simpleplayer

Standalone native GTK4 player. Sources live alongside the other Simple apps in
`~/.local/src/simpleplayer`; run `make install` after editing.

Super+Ctrl+N and Super+Shift+Q open the wide, low player window. The cover is the
largest element, with centered artist, year/album, title and controls beside it. The library
stays visible on the right and Cava runs across the bottom. Missing album art and
the idle state use the current wallpaper; it follows saved static/daylight changes.
Closing the window keeps mpv playing.

Search ranks exact names first, then prefixes and partial names, before matches
in parent paths. The best result is selected automatically. Enter shuffles and
plays the selected collection; Shift+Enter plays it in order, including when pressed while typing. Ctrl+J/K
changes selection without leaving search. The Shuffle/In order buttons play the
currently browsed folder. The red button follows the current playback order,
including keyboard playback and reopening the player; click a row or use l to browse into a collection.

Search is hidden by default; only / reveals and focuses it. Escape hides search
and clears the filter. j/k selects, h/l browses,
gg/G selects first/last; gh returns to the main music folder. Space pauses, n/p skips tracks, q closes. In search, letters
type normally. Ctrl+R refreshes the cached library index explicitly.

Album art comes from cover files beside the current track or embedded artwork,
extracted once and cached off the UI thread. Cava runs only while the window is
open. There are no online lookups or automatic library scans. Styling uses the
shared Simple theme. Missing metadata is left blank.

`native.c`, `visualizer.h` and `app.css` provide the UI; `bridge.py` handles data
and mpv IPC. `playback.sh` and `scripts/` retain existing playback-session handling.
Assets install into `~/.config/simpleplayer`; settings and compatibility helpers
remain in `~/.config/simplepicker/music`. Installation preserves `config.toml`.

Build: C compiler, make, pkg-config, GTK4, json-c, `../simple-common` headers.
Runtime: Python, Bash, mpv, flock, Cava, ffmpeg and the existing audio session.
`make check` verifies cached search, metadata, artwork and repeatable installation.

## Optional streaming

Local music remains the startup source. Choose Local, Radio or YouTube with the source buttons or 1/2/3. Press / to reveal search; Enter plays, Ctrl+J/K selects results, f toggles a favourite. Local keeps Enter shuffle / Shift+Enter ordered. Source switching does not stop playback and remembers each source's folder and query during the session.

Radio uses the free Radio Browser directory: search a station name or paste an HTTP(S) stream URL. YouTube searches public videos or accepts video/playlist links, using optional yt-dlp; all audio plays in the existing mpv session. No accounts, embedded browser or Spotify client. Public services may reject unavailable, restricted or region-blocked content; keep yt-dlp current.

Blank online search shows favourites from `$XDG_CONFIG_HOME/simpleplayer/streams.json`. Network calls happen only for online search/playback/artwork. Cached artwork uses XDG_CACHE_HOME, playback state uses XDG_RUNTIME_DIR (or the cache fallback). No service keys or machine paths required. Radio needs no new package; Simpleinstaller offers `--youtube` for yt-dlp.

Provider references: https://docs.radio-browser.info/ and https://github.com/yt-dlp/yt-dlp .

Online search results never start playback automatically: select a result, then press Enter, click Play or double-click. A single click only selects; Enter while a search is still pending requests results without queuing playback. Artwork is decoded before display; unavailable images retain the configured idle/default image. YouTube playlist tracks can recover their thumbnail after restarting the app.

Ctrl+H / Ctrl+L switch to the previous / next source, wrapping between Local, Radio and YouTube. They also work while searching; switching sources does not change playback.

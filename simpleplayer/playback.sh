#!/usr/bin/env bash

# simpleplayer: select a directory in the configured library and play supported audio.

set -o pipefail
umask 077

mDIR="${SIMPLEPLAYER_MUSIC_DIR:-${WALKERBEATS_MUSIC_DIR:-$HOME/Music}}"
CACHE_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/simpleplayer"
FOLDER_INDEX="$CACHE_ROOT/folders.index"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/scripts"
[[ -d "$SCRIPT_DIR" ]] || SCRIPT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/simplepicker/music/scripts"
SESSION_HELPER="$SCRIPT_DIR/simpleplayer-session.py"

AUDIO_FIND_EXPR=(
    \( -iname '*.mp3' -o -iname '*.flac' -o -iname '*.ogg' -o
       -iname '*.opus' -o -iname '*.m4a' -o -iname '*.wav' \)
)

notification() {
    command -v notify-send >/dev/null 2>&1 || return 0
    notify-send -u normal "$@" 2>/dev/null || true
}

fail() {
    notification "$1"
    printf '%s\n' "$1" >&2
    exit 1
}

load_config() {
    local value
    value=$(python3 "$SCRIPT_DIR/simpleplayer-config.py" 2>&1) || fail "$value"
    mDIR=$value
    [[ -d "$mDIR" ]] || fail "Music directory not found: $mDIR"
}

check_dependencies() {
    local cmd
    for cmd in mpv simplepicker flock python3; do
        command -v "$cmd" >/dev/null 2>&1 || fail "Missing dependency: $cmd"
    done
}

populate_local_music() {
    local folder="$1" file
    local_music=()
    while IFS= read -r -d '' file; do
        local_music+=("$file")
    done < <(
        find "$folder" -mindepth 1 \( -type d \( -name '.*' -o -iname 'convert*' -o -name 'Backups' \) -prune \) -o \
            \( -type f "${AUDIO_FIND_EXPR[@]}" -not -name '.*' -print0 \) | /usr/bin/sort -z
    )
}

refresh_folder_index() (
    local temp
    mkdir -p -- "$CACHE_ROOT" || return 1
    exec 9>"$CACHE_ROOT/folders.lock" || return 1
    flock 9 || return 1
    temp=$(mktemp "$CACHE_ROOT/.folders.XXXXXX") || return 1
    trap 'rm -f -- "$temp"' EXIT
    # Ranking belongs to the picker; the index only stores directory names.
    if ! find "$mDIR" -mindepth 1 \
        \( -type d \( -name '.*' -o -iname 'convert*' -o -name 'Backups' \) -prune \) -o \
        \( -type d -printf '%P\n' \) >"$temp"; then return 1; fi
    mv -f -- "$temp" "$FOLDER_INDEX" || return 1
    printf '%s\n' "$mDIR" >"$CACHE_ROOT/folders.root"
)

load_library() {
    notification 'Simpleplayer' 'Loading music library…'
    if refresh_folder_index; then
        notification 'Simpleplayer' 'Music library ready.'
    else
        fail 'Unable to scan music folders.'
    fi
}

select_music_folder() {
    local selected root='' refresh='↻ Refresh library'
    [[ -r "$CACHE_ROOT/folders.root" ]] && IFS= read -r root <"$CACHE_ROOT/folders.root"
    # Instant cached launch. Rescan only on first use, a new library root,
    # or an explicit Ctrl+R refresh; no background filesystem walk.
    if [[ ! -f "$FOLDER_INDEX" || "$root" != "$mDIR" ]]; then load_library; fi
    while true; do
        selected=$(python3 "$SCRIPT_DIR/simpleplayer-picker.py" "$FOLDER_INDEX") || return 1
        [[ -n "$selected" ]] || return 1
        if [[ "$selected" == "$refresh" ]]; then load_library; continue; fi
        [[ -d "$mDIR/$selected" ]] || { notification 'Simpleplayer' 'Folder no longer exists. Refresh the library.'; continue; }
        printf '%s\n' "$mDIR/$selected"
        return 0
    done
}

folder_playlist() {
    local folder="$1" name
    name=$(basename -- "$folder")
    printf '%s/playlist.%s\n' "$folder" "${name,,}"
}

play_music_from_folder() {
    local folder="$1" order="${2:-shuffle}" playlist
    playlist=$(folder_playlist "$folder")
    local -a options=()
    [[ "$order" == shuffle ]] && options+=(--shuffle)
    # A folder playlist preserves a curated collection without copying its songs.
    if [[ -f "$playlist" ]]; then
        python3 "$SESSION_HELPER" play --playlist-file "$playlist" \
            --no-video --vo=null --audio-display=no --force-window=no --no-terminal \
            "${options[@]}" --loop-playlist
        return $?
    fi
    populate_local_music "$folder"
    ((${#local_music[@]})) || fail "No music files found in: $(basename -- "$folder")"
    # A genre can exceed ARG_MAX. Stream NUL-separated filenames to the helper,
    # which makes a temporary playlist before replacing existing playback.
    printf '%s\0' "${local_music[@]}" | python3 "$SESSION_HELPER" play --files-from-stdin \
        --no-video --vo=null --audio-display=no --force-window=no --no-terminal \
        "${options[@]}" --loop-playlist
}

main() {
    load_config
    [[ -r "$SCRIPT_DIR/simpleplayer-picker.py" ]] || fail 'Missing music folder picker.'
    check_dependencies
    # Keep current playback until a folder and play order have been selected.
    local picker="$SCRIPT_DIR/simpleplayer-picker.py"
    local current_folder choice selected
    current_folder=$(select_music_folder) || return 0
    while true; do
        if [[ -f "$(folder_playlist "$current_folder")" ]]; then
            play_music_from_folder "$current_folder" shuffle; return
        fi
        choice=$(python3 "$picker" --folder "$current_folder" --library "$mDIR") || return 0
        case "$choice" in
            shuffle|ordered) play_music_from_folder "$current_folder" "$choice"; return ;;
            browse)
                selected=$(python3 "$picker" --folder "$current_folder" --library "$mDIR" --subfolders) || continue
                [[ "$selected" == back ]] || current_folder=$selected ;;
            library|back) current_folder=$(select_music_folder) || return 0 ;;
            *) return 0 ;;
        esac
    done
}

# Ignore callbacks from an mpv process that loaded the retired Lua helper before
# this update. No extraction or menu launch; existing playback can continue.
if [[ ${1:-} == --play-folder ]]; then
    load_config
    mDIR=$(realpath -- "$mDIR") || exit 1
    folder=$(realpath -- "${2:-}") || exit 1
    case "$folder/" in "$mDIR/"*) ;; *) fail 'Folder is outside the music library.' ;; esac
    [[ ${3:-} == shuffle || ${3:-} == ordered ]] || fail 'Unknown play order.'
    play_music_from_folder "$folder" "$3"
elif [[ ${1:-} == --extract-cover ]]; then
    exit 0
elif [[ ${1:-} == --check-config ]]; then
    load_config
    printf 'Music directory: %s\n' "$mDIR"
elif [[ ${1:-} == --refresh-library ]]; then
    load_config
    load_library
elif [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    main "$@"
fi

#!/usr/bin/env bash
# Toggle recording; copy the completed video as a file URI for pasting.
set -u
WFRC_FOLDER="${WFRC_FOLDER:-$HOME/Videos/Recordings}"
SCRIPT_NAME="${SCRIPT_NAME:-Simplecapture}"
WFRC_LOCK="${WFRC_LOCK:-${XDG_RUNTIME_DIR:-/run/user/$UID}/simplecapture-recording.pid}"
WFRC_ICON="${WFRC_ICON:-record}"
WFRC_RECORDER="${WFRC_RECORDER:-wf-recorder}"
WFRC_NOTIFY="${WFRC_NOTIFY:-1}"
WFRC_FULL_SCREEN="${WFRC_FULL_SCREEN:-0}"
notify() {
    if [[ "$WFRC_NOTIFY" == 1 ]]; then
        notify-send --app-name="$SCRIPT_NAME" --icon="$WFRC_ICON" "$1" "${2:-}" 9>&- 2>/dev/null || true
    fi
}
fail() { printf '%s\n' "$1" >&2; notify 'Recording error' "$1"; exit 1; }
command -v flock >/dev/null || fail 'flock is required.'
mkdir -p -- "$(dirname -- "$WFRC_LOCK")" || exit 1
exec 9>"$WFRC_LOCK.guard" || exit 1
if ! flock -n 9; then
    # Compare process start times to avoid signalling a reused PID.
    for attempt in {1..10}; do
        if read -r owner started < "$WFRC_LOCK" 2>/dev/null && [[ "$owner" =~ ^[0-9]+$ ]]; then
            current=$(awk '{print $22}' "/proc/$owner/stat" 2>/dev/null)
            if [[ -n "$started" && "$current" == "$started" ]]; then
                kill -TERM "$owner" 2>/dev/null
                exit $?
            fi
        fi
        sleep 0.05
    done
    fail 'Recording is starting or finishing. Try again in a moment.'
fi
recorder_pid=''
stop_requested=0
cleanup() { rm -f -- "$WFRC_LOCK"; }
stop_recording() {
    stop_requested=1
    interrupted=1
    if [[ -n "$recorder_pid" ]]; then
        kill -INT "$recorder_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT
trap stop_recording INT TERM HUP
printf '%s %s\n' "$$" "$(awk '{print $22}' /proc/$$/stat)" > "$WFRC_LOCK"
case "$WFRC_RECORDER" in
    wf-recorder|wl-screenrec) ;;
    *) fail "Unsupported recorder: $WFRC_RECORDER" ;;
esac
required=("$WFRC_RECORDER" python3)
[[ "${WFRC_COPY:-1}" != 1 ]] || required+=(wl-copy)
[[ "${WFRC_AUDIO:-1}" != 1 ]] || required+=(pactl)
for cmd in "${required[@]}"; do
    command -v "$cmd" >/dev/null || fail "Required command not found: $cmd"
done
[[ -n "${WAYLAND_DISPLAY:-}" ]] || fail 'No Wayland display found.'
geometry=''
if [[ "$WFRC_FULL_SCREEN" != 1 ]]; then
    command -v slurp >/dev/null || fail 'slurp is required for region selection.'
    geometry=$(slurp 9>&-) || { notify 'Recording cancelled'; exit 0; }
    [[ -n "$geometry" ]] || exit 0
fi
(( stop_requested == 0 )) || exit 0
mkdir -p -- "$WFRC_FOLDER" || fail 'Cannot create the recordings folder.'
WFRC_FILE_NAME="${WFRC_FILE_NAME:-$WFRC_FOLDER/$SCRIPT_NAME-$(date +%Y-%m-%dT%H-%M-%S-%N).mp4}"
[[ ! -e "$WFRC_FILE_NAME" ]] || fail "File already exists: $WFRC_FILE_NAME"
sleep "${WFRC_DELAY:-0}"
(( stop_requested == 0 )) || exit 0
if [[ "${WFRC_AUDIO:-1}" == 1 && -z "${WFRC_AUDIO_DEV:-}" ]]; then
    sink=$(pactl get-default-sink 9>&-) || fail 'Cannot find the default audio output.'
    [[ -n "$sink" ]] || fail 'No default audio output found.'
    WFRC_AUDIO_DEV="$sink.monitor"
fi
args=(-f "$WFRC_FILE_NAME")
[[ -z "$geometry" ]] || args+=(-g "$geometry")
if [[ "${WFRC_AUDIO:-1}" == 1 ]]; then
    if [[ "$WFRC_RECORDER" == wf-recorder ]]; then
        args+=("--audio=$WFRC_AUDIO_DEV")
    else
        args+=(--audio --audio-device "$WFRC_AUDIO_DEV")
    fi
fi
start=$SECONDS
"$WFRC_RECORDER" "${args[@]}" "$@" 9>&- &
recorder_pid=$!
if (( stop_requested )); then stop_recording; else notify 'Recording…' 'Press Super+R again to stop.'; fi
# A signal interrupts Bash's wait. Wait again until the recorder finishes
# writing its MP4 trailer before offering the file to another application.
while true; do
    interrupted=0
    wait "$recorder_pid"
    status=$?
    (( interrupted )) || break
done
recorder_pid=''
(( status == 0 )) || fail "Recorder exited with status $status. Check the video: $WFRC_FILE_NAME"
[[ -s "$WFRC_FILE_NAME" ]] || fail 'The recorder produced no video.'
uri=$(python3 - "$WFRC_FILE_NAME" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).resolve().as_uri())
PY
) || fail 'Could not create the clipboard file link.'
if [[ "${WFRC_COPY:-1}" == 1 ]] && ! printf '%s\r\n' "$uri" | wl-copy --type text/uri-list 9>&-; then
    fail "Video saved, but clipboard copying failed: $WFRC_FILE_NAME"
fi
size=$(du -h -- "$WFRC_FILE_NAME" | cut -f1)
duration=$((SECONDS - start))
label="Recording saved"
[[ "${WFRC_COPY:-1}" != 1 ]] || label="Recording saved and copied"
notify "$label" "$((duration / 60))m $((duration % 60))s | $size | ${geometry:-Full screen}"

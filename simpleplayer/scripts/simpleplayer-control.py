#!/usr/bin/env python3
"""Control Simpleplayer through mpv IPC, falling back to desktop players."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

COMMANDS = {
    'next': ['playlist-next', 'force'],
    'play-pause': ['cycle', 'pause'],
    'stop': ['quit'],
}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        raise SystemExit('Usage: simpleplayer-control.py next|play-pause|stop')
    action = sys.argv[1]
    root = Path(os.environ.get('XDG_RUNTIME_DIR', Path.home() / '.cache')) / 'simpleplayer'
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        try:
            client.connect(str(root / 'mpv.sock'))
        except (FileNotFoundError, ConnectionRefusedError):
            return subprocess.call(['playerctl', action])
        client.sendall((json.dumps({'command': COMMANDS[action], 'request_id': 1}) + '\n').encode())
        with client.makefile('r') as stream:
            for line in stream:
                response = json.loads(line)
                if response.get('request_id') == 1:
                    if response.get('error') != 'success':
                        raise RuntimeError(response.get('error'))
                    return 0
        # mpv may close IPC immediately when quitting.
        return 0 if action == 'stop' else 1


if __name__ == '__main__':
    raise SystemExit(main())

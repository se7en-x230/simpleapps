"""One bounded local request; invoked off the GTK thread."""
import json
import os
from pathlib import Path
import socket
import subprocess
import time

class Client:
    def __init__(self):
        self.path = str(Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / ('simpletag-' + str(os.getuid())) / 'picard.sock')

    def request(self, action, **arguments):
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(3)
            connection.connect(self.path)
            connection.sendall(json.dumps(dict(action=action, **arguments)).encode() + b'\n')
            chunks = bytearray()
            while b'\n' not in chunks:
                chunk = connection.recv(65536)
                if not chunk:
                    raise ValueError('Picard disconnected.')
                chunks.extend(chunk)
                if len(chunks) > 32 * 1024 * 1024:
                    raise ValueError('Picard returned too much data. Load fewer folders.')
        response = json.loads(chunks.split(b'\n', 1)[0])
        if 'error' in response:
            # A running Picard may still have the previous bridge loaded. Use its
            # official queued REMOVE command so no restart/discard is required.
            if action == 'clear' and response['error'] in ('Unknown action.', 'Select a current album or folder first.'):
                state = self.request('status')
                if state['busy']:
                    raise ValueError('Picard is still working. Wait for it to finish.')
                subprocess.run(['picard', '-e', 'REMOVE_ALL', '-e', 'REMOVE_EMPTY'], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=15)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    state = self.request('status')
                    if not state['groups'] and not state['busy']:
                        return {'ok': True}
                    time.sleep(0.1)
                raise ValueError('Picard has not finished clearing its list. Try closing again.')
            if action == 'remove' and response['error'] == 'Unknown action.':
                state = self.request('status')
                if state['busy']:
                    raise ValueError('Picard is still working. Wait for it to finish.')
                group = next((g for g in state['groups'] if g['id'] == arguments.get('group')), None)
                if not group or not group['files']:
                    raise ValueError('Select a current album or folder first.')
                paths = [f['path'] for f in group['files']]
                subprocess.run(['picard', '-e', 'REMOVE', *paths], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=15)
                return {'ok': True}
            raise ValueError(response['error'])
        return response

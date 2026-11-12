"""Simpletag local bridge for Picard 3; no HTTP listener or worker daemon."""
import json
import os
from pathlib import Path
from PyQt6 import QtCore, QtNetwork
from .engine import Engine

_bridge = None

def socket_path():
    base = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp'))
    directory = base / ('simpletag-' + str(os.getuid()))
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
        raise RuntimeError('Simpletag runtime directory must be private and owned by this user.')
    return str(directory/'picard.sock')

class Bridge(QtCore.QObject):
    def __init__(self, tagger):
        super().__init__(tagger)
        self.engine = Engine(tagger)
        self.server = QtNetwork.QLocalServer(self)
        self.server.setSocketOptions(QtNetwork.QLocalServer.SocketOption.UserAccessOption)
        path = socket_path()
        # Remove a stale socket only after confirming no server is listening.
        probe = QtNetwork.QLocalSocket()
        probe.connectToServer(path)
        if probe.waitForConnected(100):
            probe.disconnectFromServer()
            raise RuntimeError('Another Picard instance already owns the Simpletag bridge.')
        QtNetwork.QLocalServer.removeServer(path)
        if not self.server.listen(path):
            raise RuntimeError(self.server.errorString())
        self.server.newConnection.connect(self.accept)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.engine.finish_saves)
        self.timer.start()

    def accept(self):
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            client.buffer = bytearray()
            client.finished = False
            client.readyRead.connect(lambda c=client: self.read(c))
            client.disconnected.connect(client.deleteLater)
            timeout = QtCore.QTimer(client)
            timeout.setSingleShot(True)
            timeout.timeout.connect(client.disconnectFromServer)
            timeout.start(3000)
            if client.bytesAvailable():
                self.read(client)

    def read(self, client):
        if client.finished:
            return
        client.buffer.extend(bytes(client.readAll()))
        if len(client.buffer) > 65536:
            client.abort()
            return
        if b'\n' not in client.buffer:
            return
        client.finished = True
        try:
            request = json.loads(client.buffer.split(b'\n', 1)[0])
            if not isinstance(request, dict):
                raise ValueError('Expected a request object.')
            response = self.engine.action(request)
        except Exception as error:
            response = {'error': str(error)}
        client.write(json.dumps(response, ensure_ascii=False).encode() + b'\n')
        client.disconnectFromServer()

    def close(self):
        self.timer.stop()
        self.server.close()
        self.deleteLater()

def enable(api):
    global _bridge
    _bridge = Bridge(api.tagger)

def disable():
    global _bridge
    if _bridge:
        _bridge.close()
        _bridge = None

from __future__ import annotations

import socket
import threading
from typing import Callable


HOST = "127.0.0.1"
DEFAULT_PORT = 49371
MESSAGE_SHOW = b"show"


def notify_existing_instance(port: int = DEFAULT_PORT) -> bool:
    try:
        with socket.create_connection((HOST, port), timeout=0.2) as client:
            client.sendall(MESSAGE_SHOW)
        return True
    except OSError:
        return False


class SingleInstanceServer:
    def __init__(self, on_show: Callable[[], None], port: int = DEFAULT_PORT) -> None:
        self.on_show = on_show
        self.port = port
        self._stop_event = threading.Event()
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((HOST, self.port))
        except OSError:
            server.close()
            return False
        server.listen(1)
        server.settimeout(0.2)
        self._server = server
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._server is not None:
            self._server.close()

    def _serve(self) -> None:
        while not self._stop_event.is_set():
            try:
                assert self._server is not None
                client, _address = self._server.accept()
            except OSError:
                continue

            with client:
                try:
                    message = client.recv(16)
                except OSError:
                    continue
            if message == MESSAGE_SHOW:
                self.on_show()

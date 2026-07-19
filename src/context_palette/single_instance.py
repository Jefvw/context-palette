from __future__ import annotations

import socket
import threading
import json
from typing import Callable


HOST = "127.0.0.1"
DEFAULT_PORT = 49371
MESSAGE_SHOW = b"show"
MAX_MESSAGE_SIZE = 8192
CLIENT_RECEIVE_TIMEOUT_SECONDS = 0.5


def encode_request(request: dict[str, str]) -> bytes:
    allowed = {"command", "search", "context"}
    if set(request) - allowed:
        raise ValueError("Unsupported integration request field.")
    message = json.dumps(request, ensure_ascii=False).encode("utf-8")
    if len(message) > MAX_MESSAGE_SIZE:
        raise ValueError("Integration request is too large.")
    return message


def decode_request(message: bytes) -> dict[str, str] | None:
    if message == MESSAGE_SHOW:
        return {"command": "show"}
    try:
        value = json.loads(message.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("command") != "show":
        return None
    if set(value) - {"command", "search", "context"}:
        return None
    if not all(isinstance(item, str) for item in value.values()):
        return None
    return value


def receive_request(client: socket.socket) -> dict[str, str] | None:
    """Read one bounded request without allowing a client to hold the listener."""
    client.settimeout(CLIENT_RECEIVE_TIMEOUT_SECONDS)
    try:
        message = client.recv(MAX_MESSAGE_SIZE + 1)
    except OSError:
        return None
    if len(message) > MAX_MESSAGE_SIZE:
        return None
    return decode_request(message)


def notify_existing_instance(
    port: int = DEFAULT_PORT,
    request: dict[str, str] | None = None,
) -> bool:
    message = MESSAGE_SHOW if request is None else encode_request(request)
    try:
        with socket.create_connection((HOST, port), timeout=0.2) as client:
            client.sendall(message)
        return True
    except OSError:
        return False


class SingleInstanceServer:
    def __init__(self, on_request: Callable[[dict[str, str]], None], port: int = DEFAULT_PORT) -> None:
        self.on_request = on_request
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
                request = receive_request(client)
            if request is not None:
                self.on_request(request)

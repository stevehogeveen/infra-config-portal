"""Client for scripts/console-bridge.ps1, the helper that runs on the operator's Windows PC.

Docker containers on Windows cannot open COM ports, so the helper lists the PC's serial ports and
relays one of them over a local TCP connection. Port descriptions come back in pyserial's shape
(device, description, manufacturer, hwid) so the console identity verifier reads them unchanged,
and an opened port behaves like a pyserial connection (read, write, in_waiting, close)."""

from __future__ import annotations

import json
import os
import socket
import time
from types import SimpleNamespace
from typing import Any

DEFAULT_HOST = "host.docker.internal"
DEFAULT_PORT = 7091
CONNECT_TIMEOUT = 3.0


class BridgeUnavailable(OSError):
    """The helper is not running (or not reachable) on the operator's PC."""


def address() -> tuple[str, int]:
    # Inside Docker the helper is on the host; a backend running on the PC itself uses loopback.
    host = os.environ.get("CONSOLE_BRIDGE_HOST") or (DEFAULT_HOST if os.path.exists("/.dockerenv") else "127.0.0.1")
    try:
        port = int(os.environ.get("CONSOLE_BRIDGE_PORT") or DEFAULT_PORT)
    except ValueError:
        port = DEFAULT_PORT
    return host, port


def _connect() -> socket.socket:
    try:
        return socket.create_connection(address(), timeout=CONNECT_TIMEOUT)
    except OSError as exc:
        raise BridgeUnavailable(str(exc)) from None


def _read_line(sock: socket.socket, timeout: float) -> str:
    sock.settimeout(timeout)
    data = b""
    while not data.endswith(b"\n") and len(data) < 1_000_000:
        chunk = sock.recv(65536)
        if not chunk:
            break
        data += chunk
    return data.decode("utf-8", errors="replace").strip()


def list_ports() -> list[SimpleNamespace]:
    sock = _connect()
    try:
        sock.sendall(b"LIST\n")
        line = _read_line(sock, timeout=15.0)
    finally:
        sock.close()
    value = json.loads(line or "[]")
    items: list[Any] = value if isinstance(value, list) else [value]
    # PowerShell can wrap the list once more; flatten one level.
    flat = [inner for item in items for inner in (item if isinstance(item, list) else [item])]
    return [
        SimpleNamespace(device=item.get("device"), description=item.get("description") or "",
                        manufacturer=item.get("manufacturer") or "", hwid=item.get("hwid") or "",
                        product="", interface="", serial_number=None, location=None, vid=None, pid=None)
        for item in flat if isinstance(item, dict) and item.get("device")
    ]


class BridgeConnection:
    """A relayed COM port with the small pyserial surface the console code uses."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._sock.setblocking(False)
        self._pending = b""
        self.timeout = 0.1

    def _fill(self) -> None:
        while True:
            try:
                chunk = self._sock.recv(65536)
            except (BlockingIOError, InterruptedError):
                return
            if not chunk:
                return
            self._pending += chunk

    @property
    def in_waiting(self) -> int:
        self._fill()
        return len(self._pending)

    def read(self, size: int = 1) -> bytes:
        deadline = time.monotonic() + (self.timeout or 0)
        while True:
            self._fill()
            if self._pending or time.monotonic() >= deadline:
                break
            time.sleep(0.01)
        data, self._pending = self._pending[:size], self._pending[size:]
        return data

    def write(self, data: bytes) -> int:
        self._sock.setblocking(True)
        try:
            self._sock.sendall(data)
        finally:
            self._sock.setblocking(False)
        return len(data)

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def open_port(port: str, baud: int) -> BridgeConnection:
    sock = _connect()
    try:
        sock.sendall(f"OPEN {port} {int(baud)}\n".encode())
        reply = b""
        sock.settimeout(10.0)
        while not reply.endswith(b"\n") and len(reply) < 1000:
            chunk = sock.recv(1)
            if not chunk:
                break
            reply += chunk
        text = reply.decode("utf-8", errors="replace").strip()
        if text != "OK":
            raise OSError(text.removeprefix("ERR ").strip() or "the console helper refused to open the port")
    except Exception:
        sock.close()
        raise
    return BridgeConnection(sock)

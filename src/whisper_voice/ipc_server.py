# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unix domain socket IPC server for Local Whisper.

Accepts one Swift client at a time. All messages are newline-delimited JSON.
"""

import json
import os
import select
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from .utils import log

SOCKET_PATH = str(Path.home() / ".whisper" / "ipc.sock")
_SEND_READY_TIMEOUT = 2.0
_SEND_TOTAL_TIMEOUT = 5.0
_SEND_LOCK_ACQUIRE_TIMEOUT = 0.5


class IPCServer:
    """Unix domain socket server. Accepts one client at a time."""

    def __init__(self):
        self._client: Optional[socket.socket] = None
        self._client_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._message_handler: Optional[Callable[[dict], None]] = None
        self._on_connect: Optional[Callable[[], None]] = None
        self._server: Optional[socket.socket] = None
        self._running = False
        self._dispatch_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ipc-dispatch")

    def set_message_handler(self, callback: Callable[[dict], None]):
        """Register handler for incoming messages from the Swift client."""
        self._message_handler = callback

    def set_on_connect(self, callback: Callable[[], None]):
        """Register callback invoked when a new client connects."""
        self._on_connect = callback

    def send(self, msg: dict):
        """Thread-safe send. Drops the client on timeout or failure.

        State updates are snapshots, not a log — if another thread is already
        writing, we drop rather than queue. Writes are non-blocking with a
        total-time cap so a stalled consumer can never freeze the caller.
        """
        if not self._send_lock.acquire(timeout=_SEND_LOCK_ACQUIRE_TIMEOUT):
            return
        try:
            with self._client_lock:
                client = self._client
            if client is None:
                return
            data = (json.dumps(msg) + "\n").encode("utf-8")
            try:
                self._write_with_timeout(client, data)
            except Exception as e:
                log(f"IPC send error: {e}", "WARN")
                with self._client_lock:
                    if self._client is client:
                        self._client = None
                try:
                    client.close()
                except Exception:
                    pass
        finally:
            self._send_lock.release()

    def _write_with_timeout(self, client: socket.socket, data: bytes):
        """Non-blocking chunked write. Raises TimeoutError past the total cap.

        Uses MSG_DONTWAIT per-call instead of mutating the socket's blocking
        flag — the concurrent recv() in _read_loop shares this socket and must
        stay blocking.
        """
        deadline = time.monotonic() + _SEND_TOTAL_TIMEOUT
        view = memoryview(data)
        sent = 0
        while sent < len(view):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Swift client not draining (total timeout)")
            try:
                n = client.send(view[sent:], socket.MSG_DONTWAIT)
                if n == 0:
                    raise ConnectionError("socket closed mid-send")
                sent += n
            except BlockingIOError:
                _, writable, _ = select.select(
                    [], [client], [], min(_SEND_READY_TIMEOUT, remaining)
                )
                if not writable:
                    raise TimeoutError("Swift client not draining")

    def start(self):
        """Start the IPC server in a background daemon thread."""
        self._running = True
        t = threading.Thread(target=self._serve, daemon=True)
        t.start()

    def stop(self):
        """Stop the server and close all connections."""
        self._running = False
        self._dispatch_pool.shutdown(wait=False)
        with self._client_lock:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None
        if self._server is not None:
            try:
                self._server.close()
            except Exception:
                pass
        try:
            os.unlink(SOCKET_PATH)
        except Exception:
            pass

    def _serve(self):
        """Main server loop: bind, listen, accept clients one at a time."""
        # Ensure the socket directory exists
        socket_path = SOCKET_PATH
        os.makedirs(os.path.dirname(socket_path), exist_ok=True)

        # Clean up stale socket file
        try:
            os.unlink(socket_path)
        except FileNotFoundError:
            pass

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(socket_path)
            os.chmod(socket_path, 0o600)
        except Exception as e:
            log(f"IPC bind failed: {e}", "ERR")
            return
        server.listen(1)
        self._server = server
        log(f"IPC server listening at {SOCKET_PATH}", "OK")

        while self._running:
            try:
                client, _ = server.accept()
            except Exception:
                if self._running:
                    log("IPC accept error", "WARN")
                break

            log("Swift client connected", "OK")
            with self._client_lock:
                if self._client is not None:
                    try:
                        self._client.close()
                    except Exception:
                        pass
                self._client = client

            if self._on_connect is not None:
                try:
                    threading.Thread(target=self._on_connect, daemon=True).start()
                except Exception as e:
                    log(f"IPC on_connect error: {e}", "WARN")

            # Read loop for this client
            self._read_loop(client)

            log("Swift client disconnected", "INFO")
            with self._client_lock:
                self._client = None

    _MAX_BUF_SIZE = 1_048_576  # 1MB

    def _read_loop(self, client: socket.socket):
        """Read newline-delimited JSON messages from client until disconnect."""
        buf = b""
        while self._running:
            try:
                chunk = client.recv(4096)
            except Exception:
                break
            if not chunk:
                break
            buf += chunk
            if len(buf) > self._MAX_BUF_SIZE:
                log("IPC buffer overflow, closing connection", "WARN")
                break
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except Exception as e:
                    log(f"IPC parse error: {e}", "WARN")
                    continue
                if self._message_handler is not None:
                    try:
                        self._dispatch_pool.submit(self._message_handler, msg)
                    except RuntimeError:
                        pass  # pool shut down, drop message silently
                    except Exception as e:
                        log(f"IPC handler error: {e}", "WARN")
        try:
            client.close()
        except Exception:
            pass

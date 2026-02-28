# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Command socket server for programmatic access to Local Whisper.

Separate from the IPC socket (which serves the Swift UI). This server accepts
short-lived request/response connections from the CLI or external scripts.

Socket: ~/.whisper/cmd.sock (chmod 600)
Protocol: newline-delimited JSON (same format as IPC)
"""

import json
import os
import socket
import threading
from pathlib import Path
from typing import Callable, Optional

from .utils import log

CMD_SOCKET_PATH = str(Path.home() / ".whisper" / "cmd.sock")


class CommandServer:
    """Unix socket server for CLI commands. One connection at a time, request/response."""

    def __init__(self, handler: Callable[[dict, Callable], None]):
        """
        handler(request, send_fn) is called for each incoming command.
        send_fn(response_dict) writes a JSON response back to the client.
        The handler may call send_fn multiple times (e.g. started + done).
        """
        self._handler = handler
        self._server: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # Active operation cancellation: set by client disconnect or stop command
        self._active_stop_event: Optional[threading.Event] = None
        self._active_lock = threading.Lock()
        self._handling = False

    @property
    def stop_event(self) -> Optional[threading.Event]:
        """The stop event for the currently active CLI operation, if any."""
        with self._active_lock:
            return self._active_stop_event

    def start(self):
        """Start the command server in a background daemon thread."""
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the server and clean up."""
        self._running = False
        with self._active_lock:
            if self._active_stop_event:
                self._active_stop_event.set()
        if self._server is not None:
            try:
                self._server.close()
            except Exception:
                pass
        try:
            os.unlink(CMD_SOCKET_PATH)
        except Exception:
            pass

    def _serve(self):
        """Main server loop."""
        os.makedirs(os.path.dirname(CMD_SOCKET_PATH), exist_ok=True)
        try:
            os.unlink(CMD_SOCKET_PATH)
        except FileNotFoundError:
            pass

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(CMD_SOCKET_PATH)
            os.chmod(CMD_SOCKET_PATH, 0o600)
        except Exception as e:
            log(f"Command socket bind failed: {e}", "ERR")
            return
        server.listen(1)
        server.settimeout(1.0)
        self._server = server
        log(f"Command server listening at {CMD_SOCKET_PATH}", "OK")

        while self._running:
            try:
                client, _ = server.accept()
            except socket.timeout:
                continue
            except Exception:
                if self._running:
                    log("Command socket accept error", "WARN")
                break

            with self._active_lock:
                if self._handling:
                    # Reject: already handling a connection
                    try:
                        msg = json.dumps({"type": "error", "message": "Service is busy"}) + "\n"
                        client.sendall(msg.encode("utf-8"))
                        client.close()
                    except Exception:
                        pass
                    continue
                self._handling = True
            threading.Thread(
                target=self._handle_connection, args=(client,), daemon=True
            ).start()

    def _handle_connection(self, client: socket.socket):
        """Handle a single CLI connection: read request, dispatch, respond, close."""
        stop_event = threading.Event()
        with self._active_lock:
            self._active_stop_event = stop_event

        disconnected = threading.Event()

        def send_response(msg: dict):
            """Send a JSON response to the client."""
            if disconnected.is_set():
                return
            try:
                data = (json.dumps(msg) + "\n").encode("utf-8")
                client.sendall(data)
            except Exception:
                disconnected.set()
                stop_event.set()

        try:
            # Read exactly one request (newline-delimited JSON)
            buf = b""
            client.settimeout(5.0)
            while b"\n" not in buf:
                try:
                    chunk = client.recv(4096)
                except socket.timeout:
                    return
                if not chunk:
                    return
                buf += chunk
                if len(buf) > 65536:
                    return

            line = buf.split(b"\n", 1)[0].strip()
            if not line:
                return

            try:
                request = json.loads(line.decode("utf-8"))
            except Exception:
                send_response({"type": "error", "message": "Invalid JSON"})
                return

            # Monitor for client disconnect during long operations
            def _watch_disconnect():
                client.settimeout(None)
                try:
                    while not stop_event.is_set():
                        data = client.recv(4096)
                        if not data:
                            break
                        # Check for inline stop command
                        for part in data.split(b"\n"):
                            part = part.strip()
                            if not part:
                                continue
                            try:
                                msg = json.loads(part.decode("utf-8"))
                                if msg.get("type") == "stop":
                                    stop_event.set()
                                    return
                            except Exception:
                                pass
                except Exception:
                    pass
                disconnected.set()
                stop_event.set()

            watcher = threading.Thread(target=_watch_disconnect, daemon=True)
            watcher.start()

            # Inject stop_event into request for the handler
            request["_stop_event"] = stop_event
            self._handler(request, send_response)

        except Exception as e:
            log(f"Command handler error: {e}", "WARN")
        finally:
            with self._active_lock:
                if self._active_stop_event is stop_event:
                    self._active_stop_event = None
                self._handling = False
            stop_event.set()
            try:
                client.close()
            except Exception:
                pass

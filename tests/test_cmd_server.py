# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Integration tests for CommandServer using real Unix sockets in a tmp directory.

The CommandServer is isolated by patching CMD_SOCKET_PATH after import and
stubbing out macOS-only framework modules that are pulled in transitively.
"""

import json
import os
import shutil
import socket as sock_mod
import sys
import tempfile
import threading
import time
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import helper
# ---------------------------------------------------------------------------

def _import_cmd_server(socket_path: str):
    """
    Import cmd_server with framework stubs and redirect the socket path.
    Re-imports fresh each call to avoid cross-test state.
    """
    for mod in list(sys.modules.keys()):
        if "whisper_voice" in mod:
            del sys.modules[mod]

    stubs = {
        "sounddevice": None,
        "AppKit": None,
        "Foundation": None,
        "Quartz": None,
    }
    with patch.dict("sys.modules", stubs):
        import whisper_voice.cmd_server as cmd_mod

    cmd_mod.CMD_SOCKET_PATH = socket_path
    return cmd_mod


# ---------------------------------------------------------------------------
# Socket client helper
# ---------------------------------------------------------------------------

def _connect_and_send(socket_path: str, request: dict, timeout: float = 2.0) -> list:
    """Connect, send request JSON, read all responses until socket closes."""
    client = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
    client.settimeout(timeout)
    client.connect(socket_path)
    data = (json.dumps(request) + "\n").encode("utf-8")
    client.sendall(data)

    responses = []
    buf = b""
    while True:
        try:
            chunk = client.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line.strip():
                    responses.append(json.loads(line.decode("utf-8")))
        except sock_mod.timeout:
            break
    client.close()
    return responses


# ---------------------------------------------------------------------------
# Fixture: short Unix socket path (macOS limit is 104 bytes)
# ---------------------------------------------------------------------------


@pytest.fixture()
def sock_dir():
    """Temporary directory under /tmp to keep socket paths short enough for AF_UNIX."""
    d = tempfile.mkdtemp(dir="/tmp", prefix="wv_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCommandServer:

    def test_start_creates_socket(self, sock_dir):
        sock_path = os.path.join(sock_dir, "cmd.sock")
        cmd_mod = _import_cmd_server(sock_path)

        server = cmd_mod.CommandServer(handler=lambda req, send: None)
        try:
            server.start()
            time.sleep(0.2)
            assert os.path.exists(sock_path), "Socket file should exist after start()"
        finally:
            server.stop()

    def test_stop_removes_socket(self, sock_dir):
        sock_path = os.path.join(sock_dir, "cmd.sock")
        cmd_mod = _import_cmd_server(sock_path)

        server = cmd_mod.CommandServer(handler=lambda req, send: None)
        server.start()
        time.sleep(0.2)
        server.stop()
        time.sleep(0.1)

        assert not os.path.exists(sock_path), "Socket file should be removed after stop()"

    def test_echo_handler(self, sock_dir):
        sock_path = os.path.join(sock_dir, "cmd.sock")
        cmd_mod = _import_cmd_server(sock_path)

        def echo_handler(request, send):
            send({"type": "echo", "received": request.get("action")})

        server = cmd_mod.CommandServer(handler=echo_handler)
        try:
            server.start()
            time.sleep(0.2)

            responses = _connect_and_send(sock_path, {"action": "ping"})

            assert len(responses) == 1
            assert responses[0]["type"] == "echo"
            assert responses[0]["received"] == "ping"
        finally:
            server.stop()

    def test_handler_receives_request_fields(self, sock_dir):
        sock_path = os.path.join(sock_dir, "cmd.sock")
        cmd_mod = _import_cmd_server(sock_path)

        captured = {}

        def capture_handler(request, send):
            captured["action"] = request.get("action")
            captured["text"] = request.get("text")
            send({"type": "done", "success": True})

        server = cmd_mod.CommandServer(handler=capture_handler)
        try:
            server.start()
            time.sleep(0.2)

            _connect_and_send(sock_path, {"action": "whisper", "text": "hello"})
            time.sleep(0.1)

            assert captured["action"] == "whisper"
            assert captured["text"] == "hello"
        finally:
            server.stop()

    def test_handler_can_send_multiple_responses(self, sock_dir):
        sock_path = os.path.join(sock_dir, "cmd.sock")
        cmd_mod = _import_cmd_server(sock_path)

        def multi_handler(request, send):
            send({"type": "started", "action": request.get("action")})
            send({"type": "done", "text": "result", "success": True})

        server = cmd_mod.CommandServer(handler=multi_handler)
        try:
            server.start()
            time.sleep(0.2)

            responses = _connect_and_send(sock_path, {"action": "listen"})

            assert len(responses) == 2
            assert responses[0]["type"] == "started"
            assert responses[1]["type"] == "done"
            assert responses[1]["success"] is True
        finally:
            server.stop()

    def test_invalid_json_returns_error(self, sock_dir):
        sock_path = os.path.join(sock_dir, "cmd.sock")
        cmd_mod = _import_cmd_server(sock_path)

        server = cmd_mod.CommandServer(handler=lambda req, send: None)
        try:
            server.start()
            time.sleep(0.2)

            client = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
            client.settimeout(2.0)
            client.connect(sock_path)
            client.sendall(b"{ not valid json }\n")

            buf = b""
            try:
                while True:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    if b"\n" in buf:
                        break
            except sock_mod.timeout:
                pass
            client.close()

            line = buf.split(b"\n")[0].strip()
            response = json.loads(line.decode("utf-8"))
            assert response["type"] == "error"
            assert "Invalid JSON" in response["message"]
        finally:
            server.stop()

    def test_busy_rejection(self, sock_dir):
        sock_path = os.path.join(sock_dir, "cmd.sock")
        cmd_mod = _import_cmd_server(sock_path)

        # This event lets the test control when the first handler finishes.
        first_handler_release = threading.Event()
        first_connected = threading.Event()

        def blocking_handler(request, send):
            first_connected.set()
            first_handler_release.wait(timeout=5.0)
            send({"type": "done", "success": True})

        server = cmd_mod.CommandServer(handler=blocking_handler)
        try:
            server.start()
            time.sleep(0.2)

            # First connection: runs blocking_handler in the server's thread.
            first_client = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
            first_client.settimeout(3.0)
            first_client.connect(sock_path)
            first_client.sendall((json.dumps({"action": "listen"}) + "\n").encode("utf-8"))

            # Wait until the first handler is actually running before connecting a second.
            first_connected.wait(timeout=2.0)

            # Second connection while first is still in flight.
            second_responses = _connect_and_send(sock_path, {"action": "listen"})

            assert len(second_responses) == 1
            assert second_responses[0]["type"] == "error"
            assert "busy" in second_responses[0]["message"].lower()

            # Unblock and clean up the first connection.
            first_handler_release.set()
            try:
                first_client.close()
            except Exception:
                pass
        finally:
            server.stop()

    def test_stop_event_injected(self, sock_dir):
        sock_path = os.path.join(sock_dir, "cmd.sock")
        cmd_mod = _import_cmd_server(sock_path)

        captured_stop_event = {}

        def capture_handler(request, send):
            captured_stop_event["value"] = request.get("_stop_event")
            send({"type": "done", "success": True})

        server = cmd_mod.CommandServer(handler=capture_handler)
        try:
            server.start()
            time.sleep(0.2)

            _connect_and_send(sock_path, {"action": "transcribe", "path": "/tmp/test.wav"})
            time.sleep(0.1)

            stop_ev = captured_stop_event.get("value")
            assert stop_ev is not None, "Handler should receive _stop_event in request"
            assert isinstance(stop_ev, threading.Event)
        finally:
            server.stop()

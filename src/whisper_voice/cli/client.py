# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Command socket client for wh whisper / listen / transcribe."""

import signal
import sys
from pathlib import Path

from .constants import C_DIM, C_RED, C_RESET, CMD_SOCKET_PATH
from .lifecycle import _is_running


def _cmd_connect():
    """Connect to the command socket. Raises on failure."""
    import socket as _socket
    sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    sock.connect(CMD_SOCKET_PATH)
    return sock


def _cmd_send_recv(request: dict) -> dict:
    """Send a command and wait for the final response. Returns the last message."""
    import json
    import socket as _socket

    running, _ = _is_running()
    if not running:
        print(f"{C_RED}Service not running.{C_RESET} Start with: wh start", file=sys.stderr)
        sys.exit(1)

    try:
        sock = _cmd_connect()
    except (FileNotFoundError, ConnectionRefusedError):
        print(f"{C_RED}Cannot connect to service.{C_RESET} Try: wh restart", file=sys.stderr)
        sys.exit(1)

    # Handle Ctrl+C: send stop and exit cleanly
    stop_sent = False

    def _on_interrupt(*_):
        nonlocal stop_sent
        if not stop_sent:
            stop_sent = True
            try:
                sock.sendall((json.dumps({"type": "stop"}) + "\n").encode())
            except Exception:
                pass

    original_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, _on_interrupt)

    try:
        data = (json.dumps(request) + "\n").encode()
        sock.sendall(data)

        # Read responses until we get a terminal one (done/error)
        buf = b""
        last_response = None
        sock.settimeout(300)  # 5 min max for long operations
        while True:
            try:
                chunk = sock.recv(4096)
            except _socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except Exception:
                    continue
                last_response = msg
                msg_type = msg.get("type")
                if msg_type in ("done", "error"):
                    return msg
                # "started" messages: continue waiting
                if msg_type == "started":
                    action = msg.get("action", "")
                    if action == "listen":
                        print("Recording... (Ctrl+C to stop)", file=sys.stderr)

        return last_response or {"type": "error", "message": "Connection closed unexpectedly"}
    finally:
        signal.signal(signal.SIGINT, original_sigint)
        try:
            sock.close()
        except Exception:
            pass


def cmd_whisper(args: list):
    """Speak text aloud via TTS."""
    voice = None
    text_parts = []
    i = 0
    while i < len(args):
        if args[i] == "--voice" and i + 1 < len(args):
            voice = args[i + 1]
            i += 2
        else:
            text_parts.append(args[i])
            i += 1

    text = " ".join(text_parts)

    # Read from stdin if no text provided and stdin is piped
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()

    if not text:
        print(f"{C_RED}No text provided.{C_RESET}", file=sys.stderr)
        print(f"{C_DIM}Usage: wh whisper \"text\" [--voice NAME]{C_RESET}", file=sys.stderr)
        sys.exit(1)

    request = {"type": "whisper", "text": text}
    if voice:
        request["voice"] = voice

    result = _cmd_send_recv(request)
    if result.get("type") == "error":
        print(f"{C_RED}{result.get('message', 'Unknown error')}{C_RESET}", file=sys.stderr)
        sys.exit(1)


def cmd_listen(args: list):
    """Record from microphone and output transcription."""
    max_duration = 0
    raw = False
    for arg in args:
        if arg == "--raw":
            raw = True
        else:
            try:
                max_duration = int(arg)
            except ValueError:
                print(f"{C_RED}Invalid argument: {arg}{C_RESET}", file=sys.stderr)
                print(f"{C_DIM}Usage: wh listen [seconds] [--raw]{C_RESET}", file=sys.stderr)
                sys.exit(1)

    request = {"type": "listen", "max_duration": max_duration, "raw": raw}
    result = _cmd_send_recv(request)

    if result.get("type") == "error":
        print(f"{C_RED}{result.get('message', 'Unknown error')}{C_RESET}", file=sys.stderr)
        sys.exit(1)
    elif result.get("type") == "done":
        text = result.get("text", "")
        if text:
            print(text)


def cmd_transcribe(args: list):
    """Transcribe an audio file."""
    raw = False
    file_path = None
    for arg in args:
        if arg == "--raw":
            raw = True
        elif file_path is None:
            file_path = arg
        else:
            print(f"{C_RED}Unexpected argument: {arg}{C_RESET}", file=sys.stderr)
            sys.exit(1)

    if not file_path:
        print(f"{C_RED}No file provided.{C_RESET}", file=sys.stderr)
        print(f"{C_DIM}Usage: wh transcribe <file> [--raw]{C_RESET}", file=sys.stderr)
        sys.exit(1)

    # Resolve to absolute path
    file_path = str(Path(file_path).resolve())

    request = {"type": "transcribe", "path": file_path, "raw": raw}
    result = _cmd_send_recv(request)

    if result.get("type") == "error":
        print(f"{C_RED}{result.get('message', 'Unknown error')}{C_RESET}", file=sys.stderr)
        sys.exit(1)
    elif result.get("type") == "done":
        text = result.get("text", "")
        if text:
            print(text)

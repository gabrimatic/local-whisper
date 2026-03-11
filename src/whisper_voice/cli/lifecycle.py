# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Service lifecycle commands and config helpers."""

import fcntl
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from .constants import (
    C_BOLD,
    C_DIM,
    C_GREEN,
    C_RED,
    C_RESET,
    C_YELLOW,
    LAUNCHAGENT_LABEL,
    LAUNCHAGENT_PLIST,
    LOCK_FILE,
)

# Import TOML helpers from config (avoids duplication)
try:
    from whisper_voice.config import _find_in_section, _replace_in_section
except ImportError:
    # Fallback stubs used if config import fails (e.g., during install before venv)
    def _find_in_section(content, section, key):  # type: ignore[misc]
        return None

    def _replace_in_section(content, section, key, new_value):  # type: ignore[misc]
        return content


def _is_running() -> tuple:
    """Check if the service is running. Returns (is_running, pid_or_None)."""
    if not os.path.exists(LOCK_FILE):
        return False, None
    try:
        lf = open(LOCK_FILE, "r+")
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Got lock - service is not running (stale lock)
        fcntl.flock(lf, fcntl.LOCK_UN)
        lf.close()
        return False, None
    except FileNotFoundError:
        return False, None
    except OSError:
        # Lock held - service is running, find PID
        pid = _find_pid()
        return True, pid


def _find_pid() -> Optional[int]:
    """Find the service PID."""
    my_pid = os.getpid()
    for pattern in ["wh _run", "whisper_voice", "/bin/wh"]:
        try:
            result = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                for p in result.stdout.strip().split():
                    pid = int(p)
                    if pid != my_pid:
                        return pid
        except Exception:
            pass
    return None


def _cleanup_lock():
    """Remove stale lock file after service stops."""
    try:
        os.unlink(LOCK_FILE)
    except OSError:
        pass


def _get_config_path() -> Path:
    """Return the config file path."""
    return Path.home() / ".whisper" / "config.toml"


def _read_config_backend() -> Optional[str]:
    """Read the current backend from config.toml."""
    config_file = _get_config_path()
    if not config_file.exists():
        return None
    try:
        content = config_file.read_text()
        return _find_in_section(content, "grammar", "backend")
    except Exception:
        pass
    return None


def _read_config_backend_status() -> Optional[str]:
    """Read the grammar backend for status output, respecting the enabled flag."""
    config_file = _get_config_path()
    if not config_file.exists():
        return None
    try:
        content = config_file.read_text()
        enabled = _find_in_section(content, "grammar", "enabled")
        if enabled == "false":
            return "disabled"
        backend = _find_in_section(content, "grammar", "backend")
        if backend == "none":
            return "disabled"
        return backend
    except Exception:
        pass
    return None


def _write_config_backend(new_backend: str) -> bool:
    """Write a new backend value to config.toml. Returns True on success."""
    config_file = _get_config_path()
    if not config_file.exists():
        print(f"{C_RED}Config file not found: {config_file}{C_RESET}", file=sys.stderr)
        return False
    try:
        fd = os.open(str(config_file), os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            content = config_file.read_text()
            new_content = _replace_in_section(content, "grammar", "backend", f'"{new_backend}"')
            if new_content == content:
                # Key not found - add it
                if "[grammar]" in new_content:
                    new_content = new_content.replace(
                        "[grammar]",
                        f'[grammar]\nbackend = "{new_backend}"',
                        1
                    )
                else:
                    new_content += f'\n[grammar]\nbackend = "{new_backend}"\n'
            # Update enabled flag in [grammar] section only
            enabled_val = "false" if new_backend == "none" else "true"
            new_content = _replace_in_section(new_content, "grammar", "enabled", enabled_val)
            config_file.write_text(new_content)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return True
    except Exception as e:
        print(f"{C_RED}Failed to write config: {e}{C_RESET}", file=sys.stderr)
        return False


def _list_backends() -> dict:
    """Return BACKEND_REGISTRY without importing heavy modules."""
    try:
        from whisper_voice.backends import BACKEND_REGISTRY
        return BACKEND_REGISTRY
    except Exception:
        return {}


def _read_config_engine() -> Optional[str]:
    """Read the current transcription engine from config.toml."""
    config_file = _get_config_path()
    if not config_file.exists():
        return None
    try:
        content = config_file.read_text()
        return _find_in_section(content, "transcription", "engine")
    except Exception:
        pass
    return None


def _write_config_engine(engine_id: str) -> bool:
    """Write a new engine value to config.toml. Returns True on success."""
    config_file = _get_config_path()
    if not config_file.exists():
        print(f"{C_RED}Config file not found: {config_file}{C_RESET}", file=sys.stderr)
        return False
    try:
        fd = os.open(str(config_file), os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            content = config_file.read_text()
            new_content = _replace_in_section(content, "transcription", "engine", f'"{engine_id}"')
            if new_content == content:
                # Key not found - add it
                if "[transcription]" in new_content:
                    new_content = new_content.replace(
                        "[transcription]",
                        f'[transcription]\nengine = "{engine_id}"',
                        1
                    )
                else:
                    new_content += f'\n[transcription]\nengine = "{engine_id}"\n'
            config_file.write_text(new_content)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return True
    except Exception as e:
        print(f"{C_RED}Failed to write config: {e}{C_RESET}", file=sys.stderr)
        return False


def _list_engines() -> dict:
    """Return ENGINE_REGISTRY without importing heavy modules."""
    try:
        from whisper_voice.engines import ENGINE_REGISTRY
        return ENGINE_REGISTRY
    except Exception:
        return {}


def cmd_status():
    """Show service status."""
    running, pid = _is_running()
    backend = _read_config_backend_status() or "unknown"
    engine = _read_config_engine() or "unknown"
    config_path = _get_config_path()

    if running:
        pid_str = str(pid) if pid else "unknown"
        print(f"  {C_GREEN}{C_BOLD}Running{C_RESET}  pid {C_DIM}{pid_str}{C_RESET}")
    else:
        print(f"  {C_DIM}Stopped{C_RESET}")

    print(f"  {C_DIM}engine: {C_RESET} {engine}")
    print(f"  {C_DIM}backend:{C_RESET} {backend}")
    print(f"  {C_DIM}config: {C_RESET} {config_path}")


def cmd_start():
    """Launch the service."""
    running, pid = _is_running()
    if running:
        pid_str = str(pid) if pid else "unknown"
        print(f"{C_YELLOW}Already running (pid {pid_str}){C_RESET}")
        return

    if LAUNCHAGENT_PLIST.exists():
        result = subprocess.run(["launchctl", "start", LAUNCHAGENT_LABEL], capture_output=True)
        if result.returncode == 0:
            print(f"{C_GREEN}Started{C_RESET} (via LaunchAgent)")
        else:
            # launchctl start can fail if already loaded but stopped; try kickstart
            uid = os.getuid()
            subprocess.Popen(
                ["launchctl", "kickstart", f"gui/{uid}/{LAUNCHAGENT_LABEL}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            print(f"{C_GREEN}Started{C_RESET} (via LaunchAgent)")
    else:
        # No LaunchAgent installed - spawn directly
        wh_path = str(Path(sys.argv[0]).resolve())
        subprocess.Popen(
            [wh_path, "_run"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(f"{C_GREEN}Started{C_RESET}")


def cmd_stop():
    """Graceful kill with SIGTERM -> SIGKILL fallback."""
    running, pid = _is_running()
    if not running:
        print(f"{C_DIM}Not running{C_RESET}")
        return

    if pid is None:
        print(f"{C_YELLOW}Running but PID not found - check Activity Monitor{C_RESET}", file=sys.stderr)
        return

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"{C_DIM}Stopping (pid {pid})...{C_RESET}")

        # Wait up to 5s for graceful exit
        for _ in range(50):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                _cleanup_lock()
                print(f"{C_GREEN}Stopped{C_RESET}")
                return

        # Force kill
        try:
            os.kill(pid, signal.SIGKILL)
            _cleanup_lock()
            print(f"{C_YELLOW}Force-killed{C_RESET}")
        except ProcessLookupError:
            _cleanup_lock()
            print(f"{C_GREEN}Stopped{C_RESET}")

    except ProcessLookupError:
        _cleanup_lock()
        print(f"{C_GREEN}Stopped{C_RESET}")
    except PermissionError:
        print(f"{C_RED}Permission denied to kill pid {pid}{C_RESET}", file=sys.stderr)
        sys.exit(1)

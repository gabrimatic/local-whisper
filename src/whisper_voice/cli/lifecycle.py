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

from whisper_voice.config import _find_in_section, _replace_in_section

from .constants import (
    C_BOLD,
    C_DIM,
    C_GREEN,
    C_RED,
    C_RESET,
    C_YELLOW,
    INSTALL_BREW,
    LAUNCHAGENT_LABEL,
    LAUNCHAGENT_PLIST,
    LOCK_FILE,
    get_install_method,
)


def _is_running() -> tuple:
    """Return (is_running, pid_or_None)."""
    if not os.path.exists(LOCK_FILE):
        return False, None
    try:
        lf = open(LOCK_FILE, "r+")
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lf, fcntl.LOCK_UN)
        lf.close()
        return False, None
    except FileNotFoundError:
        return False, None
    except OSError:
        return True, _find_pid()


def _find_pid() -> Optional[int]:
    """Return the service PID, or None. Matches only `wh _run` so sibling
    CLI invocations (e.g. a concurrent `wh status`) are never mistaken
    for the long-lived service."""
    my_pid = os.getpid()
    try:
        result = subprocess.run(
            ["pgrep", "-f", "wh _run"],
            capture_output=True, text=True,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    for p in result.stdout.strip().split():
        try:
            pid = int(p)
        except ValueError:
            continue
        if pid != my_pid:
            return pid
    return None


def _cleanup_lock():
    try:
        os.unlink(LOCK_FILE)
    except OSError:
        pass


def _get_config_path() -> Path:
    return Path.home() / ".whisper" / "config.toml"


def _read_config_backend() -> Optional[str]:
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
                if "[grammar]" in new_content:
                    new_content = new_content.replace(
                        "[grammar]",
                        f'[grammar]\nbackend = "{new_backend}"',
                        1
                    )
                else:
                    new_content += f'\n[grammar]\nbackend = "{new_backend}"\n'
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
    """Show service status, uptime, RSS, and pending recovery."""
    running, pid = _is_running()
    backend = _read_config_backend_status() or "unknown"
    engine = _read_config_engine() or "unknown"
    config_path = _get_config_path()

    if running:
        pid_str = str(pid) if pid else "unknown"
        uptime = _process_uptime(pid) if pid else None
        rss_mb = _process_rss_mb(pid) if pid else None
        extras = []
        if uptime is not None:
            extras.append(f"up {_format_uptime(uptime)}")
        if rss_mb is not None:
            extras.append(f"{rss_mb:.0f} MB RSS")
        extras_str = f"  {C_DIM}{' · '.join(extras)}{C_RESET}" if extras else ""
        print(f"  {C_GREEN}{C_BOLD}Running{C_RESET}  pid {C_DIM}{pid_str}{C_RESET}{extras_str}")
    else:
        print(f"  {C_DIM}Stopped{C_RESET}")

    print(f"  {C_DIM}engine: {C_RESET} {engine}")
    print(f"  {C_DIM}backend:{C_RESET} {backend}")
    print(f"  {C_DIM}config: {C_RESET} {config_path}")

    pending = _pending_work_summary()
    if pending:
        print(f"  {C_YELLOW}pending:{C_RESET} {pending}")


def _process_uptime(pid: int) -> Optional[float]:
    """Return wall-clock uptime in seconds for the given pid, or None."""
    try:
        out = subprocess.run(
            ["ps", "-o", "etime=", "-p", str(pid)],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode != 0:
            return None
        etime = out.stdout.strip()
        if not etime:
            return None
        return _parse_etime(etime)
    except Exception:
        return None


def _parse_etime(etime: str) -> Optional[float]:
    """Parse ps etime `[[DD-]hh:]mm:ss` into seconds."""
    days = 0
    if "-" in etime:
        d, etime = etime.split("-", 1)
        days = int(d)
    parts = etime.split(":")
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return None
    if len(parts) == 2:
        minutes, seconds = parts
        hours = 0
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        return None
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _format_uptime(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        hours = seconds / 3600
        return f"{hours:.1f}h"
    return f"{seconds / 86400:.1f}d"


def _process_rss_mb(pid: int) -> Optional[float]:
    """Return RSS in megabytes for the given pid, or None on error."""
    try:
        out = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode != 0:
            return None
        rss_kb = out.stdout.strip()
        if not rss_kb:
            return None
        return int(rss_kb) / 1024.0
    except Exception:
        return None


def _pending_work_summary() -> Optional[str]:
    """Report interrupted pipelines waiting to be recovered on next boot."""
    home = Path.home() / ".whisper"
    parts = []
    marker = home / "processing.marker"
    if marker.exists():
        parts.append("1 interrupted transcription")
    session = home / "current_session.jsonl"
    if session.exists():
        try:
            chunks = sum(
                1 for line in session.read_text(encoding="utf-8").splitlines()
                if '"type": "chunk"' in line
            )
            parts.append(f"{chunks} chunks from a long session")
        except OSError:
            parts.append("partial long session")
    return "; ".join(parts) if parts else None


def cmd_start():
    """Launch the service."""
    running, pid = _is_running()
    if running:
        pid_str = str(pid) if pid else "unknown"
        print(f"{C_YELLOW}Already running (pid {pid_str}){C_RESET}")
        return

    is_brew = get_install_method() == INSTALL_BREW

    # Homebrew: prefer brew services which manages its own plist
    if is_brew:
        brew_plist = Path.home() / "Library" / "LaunchAgents" / "homebrew.mxcl.local-whisper.plist"
        if brew_plist.exists():
            result = subprocess.run(["brew", "services", "start", "local-whisper"], capture_output=True)
            if result.returncode == 0:
                print(f"{C_GREEN}Started{C_RESET} (via brew services)")
            else:
                print(f"{C_RED}Failed to start via brew services{C_RESET}", file=sys.stderr)
                stderr = result.stderr.decode().strip() if result.stderr else ""
                if stderr:
                    print(f"  {C_DIM}{stderr}{C_RESET}", file=sys.stderr)
            return

    if LAUNCHAGENT_PLIST.exists():
        # Ensure the agent is loaded (idempotent if already loaded)
        subprocess.run(
            ["launchctl", "load", str(LAUNCHAGENT_PLIST)],
            capture_output=True,
        )
        uid = os.getuid()
        # kickstart -k reliably starts the agent whether loaded-but-stopped or freshly loaded
        result = subprocess.run(
            ["launchctl", "kickstart", f"gui/{uid}/{LAUNCHAGENT_LABEL}"],
            capture_output=True,
        )
        if result.returncode == 0:
            print(f"{C_GREEN}Started{C_RESET} (via LaunchAgent)")
        else:
            # Fallback: try launchctl start
            subprocess.run(["launchctl", "start", LAUNCHAGENT_LABEL], capture_output=True)
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

    # If Homebrew, also tell brew services to stop (prevents auto-restart)
    if get_install_method() == INSTALL_BREW:
        subprocess.run(["brew", "services", "stop", "local-whisper"], capture_output=True)

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

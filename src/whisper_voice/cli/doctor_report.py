# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Shareable `wh doctor --report` output.

Captures the information a developer typically asks for in a bug report:
service running state, engine, backend, macOS version, Python version,
installed packages, last N log lines. Paths and user directories are left
intact (they're already tied to the developer's own machine), but the
report never includes the actual content of the config file, recorded
audio, or transcription history.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .constants import (
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_GREEN,
    C_RESET,
    LOG_FILE,
    get_install_method,
)
from .lifecycle import (
    _get_config_path,
    _is_running,
    _read_config_backend_status,
    _read_config_engine,
)


def write_doctor_report(out_path: Path) -> None:
    sections = [
        _header(),
        _system_section(),
        _service_section(),
        _packages_section(),
        _log_tail_section(),
    ]
    body = "\n\n".join(s for s in sections if s)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body + "\n", encoding="utf-8")
    print(f"  {C_GREEN}{C_BOLD}Report saved{C_RESET}  {C_DIM}→{C_RESET}  {C_CYAN}{out_path}{C_RESET}")


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _header() -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        from whisper_voice import __version__
    except Exception:
        __version__ = "unknown"
    return (
        f"# Local Whisper diagnostic report\n\n"
        f"- Generated: `{ts}`\n"
        f"- Version: `{__version__}`\n"
        f"- Install: `{get_install_method()}`"
    )


def _system_section() -> str:
    lines = ["## System", ""]
    lines.append(f"- Python: `{sys.version.split()[0]}`")
    macos = _run(["sw_vers", "-productVersion"])
    if macos:
        lines.append(f"- macOS: `{macos.strip()}`")
    arch = _run(["uname", "-m"])
    if arch:
        lines.append(f"- Architecture: `{arch.strip()}`")
    return "\n".join(lines)


def _service_section() -> str:
    running, pid = _is_running()
    backend = _read_config_backend_status() or "unknown"
    engine = _read_config_engine() or "unknown"
    config_path = _get_config_path()
    lines = ["## Service", ""]
    lines.append(f"- Running: `{'yes' if running else 'no'}`")
    if pid:
        lines.append(f"- PID: `{pid}`")
    lines.append(f"- Engine: `{engine}`")
    lines.append(f"- Grammar backend: `{backend}`")
    lines.append(f"- Config path: `{config_path}`")
    return "\n".join(lines)


def _packages_section() -> str:
    lines = ["## Python packages", ""]
    packages = [
        "sounddevice", "numpy", "pynput", "qwen3_asr_mlx", "kokoro_mlx",
        "requests", "soundfile", "misaki", "apple_fm_sdk",
    ]
    for pkg in packages:
        version = _pkg_version(pkg)
        mark = "x" if version else " "
        lines.append(f"- [{mark}] `{pkg}` {version or '(not installed)'}")
    return "\n".join(lines)


def _log_tail_section() -> str:
    if not LOG_FILE.exists():
        return "## Log tail\n\n_(no log file found)_"
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return f"## Log tail\n\n_(could not read log: {e})_"
    tail = [_redact_log_line(line) for line in lines[-60:]]
    block = "\n".join(tail)
    return "## Log tail (last 60 lines, transcription snippets redacted)\n\n```\n" + block + "\n```"


# Prefixes in the service log that carry transcription text we don't want to
# leak in a shareable report. Any line containing one of these markers has
# everything from the marker onward replaced with ``<redacted>``.
_REDACT_MARKERS = (
    "Raw:", "Copied:", "Pasted:", "Retry:",
    "Segment:", "Fixed:", "TTS: speaking",
)


def _redact_log_line(line: str) -> str:
    for marker in _REDACT_MARKERS:
        idx = line.find(marker)
        if idx != -1:
            return line[: idx + len(marker)] + " <redacted>"
    return line


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        return result.stdout
    except Exception:
        return ""


def _pkg_version(name: str) -> str:
    """Return the installed package version, or "" if not installed.

    Tries the PyPI distribution name (underscores → dashes) first, then the
    literal module name, so packages like ``apple_fm_sdk`` are resolved
    regardless of which spelling the installer recorded.
    """
    from importlib.metadata import version as _version

    for candidate in (name.replace("_", "-"), name):
        try:
            return _version(candidate)
        except Exception:
            continue
    return ""

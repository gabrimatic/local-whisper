# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Marker-file crash recovery for in-flight transcriptions."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from .config import CONFIG_DIR
from .utils import log

_MARKER = CONFIG_DIR / "processing.marker"


def mark_processing(audio_path: Path | str) -> None:
    try:
        _MARKER.parent.mkdir(parents=True, exist_ok=True)
        _MARKER.write_text(str(audio_path), encoding="utf-8")
    except OSError as e:
        log(f"Recovery marker write failed: {e}", "WARN")


def clear_marker() -> None:
    try:
        _MARKER.unlink(missing_ok=True)
    except OSError:
        pass


def pending_recoveries() -> list[Path]:
    if not _MARKER.exists():
        return []
    try:
        raw = _MARKER.read_text(encoding="utf-8").strip()
    except OSError as e:
        log(f"Recovery marker read failed: {e}", "WARN")
        return []
    if not raw:
        return []
    path = Path(raw)
    if not path.exists():
        clear_marker()
        return []
    return [path]


def marker_age_seconds() -> Optional[float]:
    try:
        return time.time() - _MARKER.stat().st_mtime
    except (OSError, FileNotFoundError):
        return None

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Export transcription history in user-friendly formats.

Reads from the on-disk history directory via ``Backup.get_history``; does not
require the live service to be running. Exports preserve timestamps and the
raw/corrected distinction where available.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .backup import Backup

SUPPORTED_FORMATS = ("md", "txt", "json")


def export_history(
    out_path: Path,
    fmt: str = "md",
    limit: Optional[int] = None,
) -> int:
    """Write transcription history to *out_path* in *fmt*.

    Returns the number of entries written. Raises ``ValueError`` on unknown
    formats so CLI callers can surface the error cleanly.
    """
    fmt = fmt.lower()
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unknown export format '{fmt}'. Supported: {', '.join(SUPPORTED_FORMATS)}"
        )

    backup = Backup()
    entries = backup.get_history(limit=limit if limit else 10_000)

    if fmt == "md":
        content = _render_markdown(entries)
    elif fmt == "txt":
        content = _render_plain_text(entries)
    else:
        content = _render_json(entries)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return len(entries)


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def _iter_ordered(entries: Iterable[dict]) -> list:
    """Sort oldest→newest for readability in exports."""
    return sorted(entries, key=lambda e: e.get("timestamp") or datetime.min)


def _render_markdown(entries: Iterable[dict]) -> str:
    ordered = _iter_ordered(entries)
    if not ordered:
        return "# Local Whisper history\n\n_No transcriptions yet._\n"
    lines = ["# Local Whisper history", ""]
    lines.append(f"_{len(ordered)} entries · oldest first_")
    lines.append("")
    for e in ordered:
        ts = _fmt_ts(e.get("timestamp"))
        fixed = (e.get("fixed") or "").strip()
        raw = (e.get("raw") or "").strip()
        lines.append(f"## {ts}")
        lines.append("")
        lines.append(fixed or raw or "_(empty)_")
        if raw and raw != fixed:
            lines.append("")
            lines.append("> Raw transcription:")
            lines.append("> ")
            for raw_line in raw.splitlines() or [""]:
                lines.append(f"> {raw_line}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _render_plain_text(entries: Iterable[dict]) -> str:
    ordered = _iter_ordered(entries)
    if not ordered:
        return "No transcriptions yet.\n"
    blocks = []
    for e in ordered:
        ts = _fmt_ts(e.get("timestamp"))
        text = (e.get("fixed") or e.get("raw") or "").strip()
        blocks.append(f"[{ts}]\n{text}")
    return "\n\n".join(blocks) + "\n"


def _render_json(entries: Iterable[dict]) -> str:
    ordered = _iter_ordered(entries)
    payload = []
    for e in ordered:
        ts = e.get("timestamp")
        path = e.get("path")
        # ``Backup.get_history`` returns ``path`` as a ``pathlib.Path`` already,
        # so grab ``.stem`` directly and fall back to a stringified form if a
        # caller hands us something else.
        entry_id = None
        if path is not None:
            entry_id = getattr(path, "stem", None) or Path(str(path)).stem
        payload.append({
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "raw": e.get("raw", ""),
            "fixed": e.get("fixed", ""),
            "id": entry_id,
        })
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _fmt_ts(ts) -> str:
    if hasattr(ts, "strftime"):
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    return str(ts)

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Long-session chunked transcription with partial persistence.

Recordings >= LONG_SESSION_THRESHOLD_SECONDS write each chunk to
current_session.jsonl as it completes, so a mid-session crash loses at
most one chunk and the rest is recovered on next boot.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Iterable, Optional

from .config import CONFIG_DIR
from .utils import log

LONG_SESSION_THRESHOLD_SECONDS = 300

_SESSION_PATH = CONFIG_DIR / "current_session.jsonl"


@dataclass
class SessionChunk:
    index: int
    text: str
    raw: str
    ts: float


class SessionLog:
    """Append-only JSONL writer for an in-progress long session."""

    def __init__(self, total_chunks: int):
        self.path = _SESSION_PATH
        self.started_at = time.time()
        self.total_chunks = total_chunks
        self._chunks: list[SessionChunk] = []
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as f:
                header = {
                    "type": "header",
                    "started_at": self.started_at,
                    "total_chunks": total_chunks,
                }
                f.write(json.dumps(header) + "\n")
                f.flush()
        except OSError as e:
            log(f"Long session log init failed: {e}", "WARN")

    def append(self, chunk: SessionChunk) -> None:
        self._chunks.append(chunk)
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "type": "chunk",
                    "index": chunk.index,
                    "text": chunk.text,
                    "raw": chunk.raw,
                    "ts": chunk.ts,
                }) + "\n")
                f.flush()
        except OSError as e:
            log(f"Long session log append failed: {e}", "WARN")

    def aggregated_raw(self) -> str:
        return " ".join(c.raw for c in self._chunks if c.raw).strip()

    def aggregated_text(self) -> str:
        return " ".join(c.text for c in self._chunks if c.text).strip()

    def close(self) -> None:
        """Remove the session file — call only after the aggregated text
        has been persisted to the regular history."""
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


def read_pending_session() -> Optional[dict]:
    """Return {started_at, total_chunks, chunks} or None if no session file."""
    if not _SESSION_PATH.exists():
        return None
    header: dict = {}
    chunks: list[SessionChunk] = []
    try:
        with _SESSION_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if payload.get("type") == "header":
                    header = payload
                elif payload.get("type") == "chunk":
                    chunks.append(SessionChunk(
                        index=int(payload.get("index", 0)),
                        text=str(payload.get("text", "")),
                        raw=str(payload.get("raw", "")),
                        ts=float(payload.get("ts", 0.0)),
                    ))
    except OSError as e:
        log(f"Long session log read failed: {e}", "WARN")
        return None
    return {
        "started_at": float(header.get("started_at", 0.0)),
        "total_chunks": int(header.get("total_chunks", len(chunks))),
        "chunks": chunks,
    }


def discard_pending_session() -> None:
    try:
        _SESSION_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def format_interrupted_session(chunks: Iterable[SessionChunk], total: int) -> tuple[str, str]:
    """Return (raw, final) for an interrupted session. Marker on final only."""
    completed = sorted(chunks, key=lambda c: c.index)
    raw = " ".join(c.raw for c in completed if c.raw).strip()
    final = " ".join(c.text for c in completed if c.text).strip()
    note = (
        f"[Interrupted: recovered {len(completed)} of {total} chunks]"
        if total > 0
        else f"[Interrupted: recovered {len(completed)} chunks]"
    )
    if final:
        final = f"{note}\n\n{final}"
    else:
        final = note
    return raw, final

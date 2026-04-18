# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Tests for whisper_voice.long_session."""

from __future__ import annotations

import json

import pytest

from whisper_voice import long_session
from whisper_voice.long_session import SessionChunk, SessionLog


@pytest.fixture
def session_tmp(tmp_path, monkeypatch):
    path = tmp_path / "current_session.jsonl"
    monkeypatch.setattr(long_session, "_SESSION_PATH", path)
    yield path


def test_session_log_writes_header_and_chunks(session_tmp):
    log = SessionLog(total_chunks=3)
    assert session_tmp.exists()
    log.append(SessionChunk(index=0, text="Hello", raw="hello", ts=1.0))
    log.append(SessionChunk(index=1, text="world", raw="world", ts=2.0))

    lines = [json.loads(line) for line in session_tmp.read_text().splitlines()]
    assert lines[0]["type"] == "header"
    assert lines[0]["total_chunks"] == 3
    assert lines[1] == {"type": "chunk", "index": 0, "text": "Hello", "raw": "hello", "ts": 1.0}
    assert lines[2]["text"] == "world"


def test_session_log_close_removes_file(session_tmp):
    log = SessionLog(total_chunks=1)
    log.append(SessionChunk(index=0, text="ok", raw="ok", ts=1.0))
    log.close()
    assert not session_tmp.exists()


def test_read_pending_session_returns_none_when_missing(session_tmp):
    assert long_session.read_pending_session() is None


def test_read_pending_session_parses_chunks(session_tmp):
    log = SessionLog(total_chunks=2)
    log.append(SessionChunk(index=0, text="first", raw="first raw", ts=10.0))
    log.append(SessionChunk(index=1, text="second", raw="second raw", ts=20.0))
    result = long_session.read_pending_session()
    assert result is not None
    assert result["total_chunks"] == 2
    assert len(result["chunks"]) == 2
    assert result["chunks"][0].text == "first"
    assert result["chunks"][1].raw == "second raw"


def test_read_pending_session_ignores_malformed_lines(session_tmp):
    session_tmp.write_text(
        '{"type": "header", "total_chunks": 2, "started_at": 0}\n'
        '{"type": "chunk", "index": 0, "text": "ok", "raw": "ok", "ts": 1.0}\n'
        'not json\n'
        '{"type": "chunk", "index": 1, "text": "two", "raw": "two", "ts": 2.0}\n',
        encoding="utf-8",
    )
    result = long_session.read_pending_session()
    assert result is not None
    assert len(result["chunks"]) == 2


def test_format_interrupted_session_tags_only_final():
    """The interruption marker is user-facing metadata — it belongs on
    ``final`` but not on ``raw`` so analytics and search that key off
    the raw transcription aren't polluted with synthetic strings."""
    chunks = [
        SessionChunk(index=0, text="Hello.", raw="hello", ts=0),
        SessionChunk(index=1, text="World.", raw="world", ts=0),
    ]
    raw, final = long_session.format_interrupted_session(chunks, total=5)
    assert raw == "hello world"
    assert final.startswith("[Interrupted: recovered 2 of 5 chunks]")
    assert "Hello." in final and "World." in final


def test_format_interrupted_session_empty_chunks():
    raw, final = long_session.format_interrupted_session([], total=3)
    assert raw == ""
    assert final == "[Interrupted: recovered 0 of 3 chunks]"


def test_discard_pending_session_is_idempotent(session_tmp):
    long_session.discard_pending_session()  # no-op when absent
    long_session.discard_pending_session()
    assert not session_tmp.exists()


def test_empty_session_with_only_header_is_authoritative(session_tmp):
    """A session file with a header but zero chunks still signals that
    the long-session pipeline started. read_pending_session returns the
    shell so the recovery caller can treat it as authoritative and clear
    the processing marker — preventing a redundant full-file
    retranscription on next startup."""
    SessionLog(total_chunks=3)  # header only
    result = long_session.read_pending_session()
    assert result is not None
    assert result["chunks"] == []
    assert result["total_chunks"] == 3

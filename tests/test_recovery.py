# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Tests for whisper_voice.recovery."""

from __future__ import annotations

import time

import pytest

from whisper_voice import recovery


@pytest.fixture
def marker_tmp(tmp_path, monkeypatch):
    """Redirect the marker into a temp dir so tests don't touch ~/.whisper."""
    marker = tmp_path / "processing.marker"
    monkeypatch.setattr(recovery, "_MARKER", marker)
    yield marker


def test_no_marker_means_no_recovery(marker_tmp):
    assert recovery.pending_recoveries() == []
    assert recovery.marker_age_seconds() is None


def test_mark_then_clear(marker_tmp, tmp_path):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"RIFF")
    recovery.mark_processing(audio)
    assert marker_tmp.exists()
    assert recovery.pending_recoveries() == [audio]
    recovery.clear_marker()
    assert not marker_tmp.exists()
    assert recovery.pending_recoveries() == []


def test_marker_pointing_at_missing_audio_is_auto_cleared(marker_tmp, tmp_path):
    missing = tmp_path / "deleted.wav"
    marker_tmp.write_text(str(missing), encoding="utf-8")
    # The audio no longer exists — there is nothing to recover, so the
    # marker should be removed and the caller should see an empty list.
    assert recovery.pending_recoveries() == []
    assert not marker_tmp.exists()


def test_marker_age_reports_seconds(marker_tmp, tmp_path):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"RIFF")
    recovery.mark_processing(audio)
    time.sleep(0.05)
    age = recovery.marker_age_seconds()
    assert age is not None and age >= 0.04


def test_empty_marker_is_ignored(marker_tmp):
    marker_tmp.write_text("", encoding="utf-8")
    assert recovery.pending_recoveries() == []


def test_clear_marker_is_idempotent(marker_tmp):
    recovery.clear_marker()  # no-op when absent
    recovery.clear_marker()  # still no-op
    assert not marker_tmp.exists()

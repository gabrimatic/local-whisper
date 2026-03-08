# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for backup.py.

All tests use temporary directories and never touch ~/.whisper/.
"""

import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Config stubs
# ---------------------------------------------------------------------------

@dataclass
class _BackupConfig:
    directory: str = "/tmp"
    history_limit: int = 100

    @property
    def path(self) -> Path:
        return Path(self.directory).expanduser()


@dataclass
class _AudioConfig:
    sample_rate: int = 16000


@dataclass
class _Config:
    backup: _BackupConfig
    audio: _AudioConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_backup(tmp_path, history_limit=100):
    """
    Import and instantiate Backup with all get_config calls redirected to a
    synthetic config pointing at tmp_path.

    Returns (Backup instance, backup module reference) so tests can introspect
    the module-level get_config if needed.
    """
    for mod in list(sys.modules.keys()):
        if "whisper_voice" in mod:
            del sys.modules[mod]

    cfg = _Config(
        backup=_BackupConfig(directory=str(tmp_path), history_limit=history_limit),
        audio=_AudioConfig(sample_rate=16000),
    )

    stubs = {
        "rumps": None,
        "sounddevice": None,
        "AppKit": None,
        "Foundation": None,
        "Quartz": None,
    }
    with patch.dict("sys.modules", stubs):
        with patch("whisper_voice.config.get_config", return_value=cfg):
            import whisper_voice.backup as backup_mod

    # Patch the module-level name so every subsequent get_config() call inside
    # backup.py (including _prune methods) returns our synthetic config.
    backup_mod.get_config = lambda: cfg
    b = backup_mod.Backup()
    return b, backup_mod


def _sine_audio(seconds=0.5, sr=16000):
    """Return a float32 sine wave array (values in [-1, 1])."""
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    return np.sin(2 * np.pi * 440 * t).astype(np.float32)


def _read_wav(path):
    """Return (n_channels, sample_width, frame_rate, frames) from a WAV file."""
    with wave.open(str(path), "rb") as w:
        return w.getnchannels(), w.getsampwidth(), w.getframerate(), w.readframes(w.getnframes())


# ---------------------------------------------------------------------------
# TestSaveAudio
# ---------------------------------------------------------------------------

class TestSaveAudio:
    def test_save_creates_wav_file(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        audio = _sine_audio()
        result = b.save_audio(audio)
        assert result is not None
        assert b.audio_path.exists()

    def test_save_audio_creates_history_copy(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        b.save_audio(_sine_audio())
        wavs = list(b.audio_history_dir.glob("*.wav"))
        assert len(wavs) == 1

    def test_save_audio_clamps_values(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        # Out-of-range and NaN values must not crash and must produce a valid WAV
        data = np.array([0.5, 2.0, -3.0, float("nan"), float("inf"), float("-inf")], dtype=np.float32)
        result = b.save_audio(data)
        assert result is not None
        assert b.audio_path.exists()
        # File must be readable as a valid WAV
        n_channels, sample_width, frame_rate, frames = _read_wav(b.audio_path)
        assert len(frames) > 0

    def test_save_audio_wav_format(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        b.save_audio(_sine_audio(seconds=0.1))
        n_channels, sample_width, frame_rate, _ = _read_wav(b.audio_path)
        assert n_channels == 1        # mono
        assert sample_width == 2      # 16-bit
        assert frame_rate == 16000    # 16 kHz

    def test_save_audio_returns_path(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        result = b.save_audio(_sine_audio())
        assert result == b.audio_path


# ---------------------------------------------------------------------------
# TestSaveText
# ---------------------------------------------------------------------------

class TestSaveText:
    def test_save_and_read_text(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        b.save_text("hello world")
        assert b.get_text() == "hello world"

    def test_get_text_missing_file(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        assert b.get_text() is None

    def test_save_text_overwrites(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        b.save_text("first")
        b.save_text("second")
        assert b.get_text() == "second"


# ---------------------------------------------------------------------------
# TestSaveRaw
# ---------------------------------------------------------------------------

class TestSaveRaw:
    def test_save_raw_writes_file(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        b.save_raw("raw transcript")
        assert b.raw_path.exists()
        assert b.raw_path.read_text("utf-8") == "raw transcript"

    def test_save_raw_overwrites(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        b.save_raw("first raw")
        b.save_raw("second raw")
        assert b.raw_path.read_text("utf-8") == "second raw"


# ---------------------------------------------------------------------------
# TestSaveHistory / TestGetHistory
# ---------------------------------------------------------------------------

class TestSaveHistory:
    def test_save_and_get_history_roundtrip(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        b.save_history("raw text", "fixed text")
        entries = b.get_history()
        assert len(entries) == 1
        assert entries[0]["raw"] == "raw text"
        assert entries[0]["fixed"] == "fixed text"

    def test_history_format_parsing(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        # Write a well-formed RAW/FIXED file manually and verify parsing
        content = "RAW:\nsome raw\n\nFIXED:\nsome fixed"
        ts = "20260101_120000_000001"
        (b.history_dir / f"{ts}.txt").write_text(content, encoding="utf-8")
        entries = b.get_history()
        assert entries[0]["raw"] == "some raw"
        assert entries[0]["fixed"] == "some fixed"

    def test_history_without_fixed_section(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        # Plain text (no markers): both raw and fixed should be the full content
        content = "just plain text"
        ts = "20260101_120000_000002"
        (b.history_dir / f"{ts}.txt").write_text(content, encoding="utf-8")
        entries = b.get_history()
        assert entries[0]["raw"] == "just plain text"
        assert entries[0]["fixed"] == "just plain text"

    def test_history_newest_first(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        for i in range(3):
            b.save_history(f"raw {i}", f"fixed {i}")
            time.sleep(0.01)  # ensure distinct microsecond timestamps
        entries = b.get_history()
        # The last saved entry must appear first (reverse chronological order)
        assert entries[0]["raw"] == "raw 2"
        assert entries[-1]["raw"] == "raw 0"

    def test_history_limit_parameter(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        for i in range(5):
            b.save_history(f"raw {i}", f"fixed {i}")
            time.sleep(0.01)
        entries = b.get_history(limit=2)
        assert len(entries) == 2

    def test_empty_history_not_saved(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        b.save_history("", "")
        assert list(b.history_dir.glob("*.txt")) == []

    def test_history_entry_has_required_keys(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        b.save_history("r", "f")
        entry = b.get_history()[0]
        assert "path" in entry
        assert "timestamp" in entry
        assert "raw" in entry
        assert "fixed" in entry

    def test_none_final_falls_back_to_raw(self, tmp_path):
        """save_history(raw, None) must store raw as fixed too."""
        b, _ = _make_backup(tmp_path)
        b.save_history("only raw", None)
        entry = b.get_history()[0]
        assert entry["raw"] == "only raw"
        assert entry["fixed"] == "only raw"


# ---------------------------------------------------------------------------
# TestPruning
# ---------------------------------------------------------------------------

class TestPruning:
    def test_prune_text_history(self, tmp_path):
        b, _ = _make_backup(tmp_path, history_limit=3)
        for i in range(5):
            b.save_history(f"raw {i}", f"fixed {i}")
            time.sleep(0.01)
        remaining = list(b.history_dir.glob("*.txt"))
        assert len(remaining) == 3

    def test_prune_audio_history(self, tmp_path):
        b, _ = _make_backup(tmp_path, history_limit=2)
        for _ in range(4):
            b.save_audio(_sine_audio(seconds=0.05))
            time.sleep(0.01)
        remaining = list(b.audio_history_dir.glob("*.wav"))
        assert len(remaining) == 2

    def test_prune_keeps_newest(self, tmp_path):
        b, _ = _make_backup(tmp_path, history_limit=2)
        for i in range(3):
            b.save_history(f"raw {i}", f"fixed {i}")
            time.sleep(0.01)
        entries = b.get_history()
        assert len(entries) == 2
        assert entries[0]["raw"] == "raw 2"
        assert entries[1]["raw"] == "raw 1"


# ---------------------------------------------------------------------------
# TestGetAudio
# ---------------------------------------------------------------------------

class TestGetAudio:
    def test_get_audio_exists(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        b.save_audio(_sine_audio())
        result = b.get_audio()
        assert result is not None
        assert result == b.audio_path

    def test_get_audio_missing(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        assert b.get_audio() is None


# ---------------------------------------------------------------------------
# TestSaveProcessedAudio
# ---------------------------------------------------------------------------

class TestSaveProcessedAudio:
    def test_save_processed_creates_file(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        result = b.save_processed_audio(_sine_audio())
        assert result is not None
        assert b.processed_audio_path.exists()

    def test_save_processed_wav_format(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        b.save_processed_audio(_sine_audio(seconds=0.1))
        n_channels, sample_width, frame_rate, _ = _read_wav(b.processed_audio_path)
        assert n_channels == 1
        assert sample_width == 2
        assert frame_rate == 16000

    def test_save_processed_separate_from_raw(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        b.save_audio(_sine_audio())
        b.save_processed_audio(_sine_audio(seconds=0.2))
        assert b.audio_path != b.processed_audio_path
        assert b.audio_path.exists()
        assert b.processed_audio_path.exists()


# ---------------------------------------------------------------------------
# TestSaveAudioSegment
# ---------------------------------------------------------------------------

class TestSaveAudioSegment:
    def test_save_segment_creates_file(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        result = b.save_audio_segment(_sine_audio(), index=0)
        assert result is not None
        assert result.exists()

    def test_save_segment_naming(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        path = b.save_audio_segment(_sine_audio(), index=3)
        assert path.name == "last_recording_3.wav"

    def test_save_multiple_segments(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        for i in range(3):
            b.save_audio_segment(_sine_audio(seconds=0.05), index=i)
        for i in range(3):
            assert (tmp_path / f"last_recording_{i}.wav").exists()

    def test_segment_wav_format(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        path = b.save_audio_segment(_sine_audio(seconds=0.1), index=0)
        n_channels, sample_width, frame_rate, _ = _read_wav(path)
        assert n_channels == 1
        assert sample_width == 2
        assert frame_rate == 16000


# ---------------------------------------------------------------------------
# TestDirectorySetup
# ---------------------------------------------------------------------------

class TestDirectorySetup:
    def test_dirs_created_on_init(self, tmp_path):
        b, _ = _make_backup(tmp_path)
        assert b.history_dir.is_dir()
        assert b.audio_history_dir.is_dir()

    def test_base_dir_matches_config(self, tmp_path):
        sub = tmp_path / "whisper_data"
        b, _ = _make_backup(sub)
        assert b._dir == sub
        assert sub.is_dir()

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Backup manager for Local Whisper.

Handles persistence of audio recordings and transcriptions.
"""

import glob
import os
import threading
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from .config import get_config
from .utils import log


class Backup:
    """Manages backup of audio files and transcription text."""

    def __init__(self):
        config = get_config()
        self._dir = config.backup.path
        self._dir.mkdir(parents=True, exist_ok=True)
        try:
            self._dir.chmod(0o700)
        except OSError:
            pass
        self._history_dir = self._dir / "history"
        self._history_dir.mkdir(parents=True, exist_ok=True)
        self._audio_history_dir = self._dir / "audio_history"
        self._audio_history_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @property
    def audio_path(self) -> Path:
        """Path to last recording audio file (raw, unprocessed - for backup/retry)."""
        return self._dir / "last_recording.wav"

    @property
    def processed_audio_path(self) -> Path:
        """Path to processed audio file (used only for transcription, not for retry)."""
        return self._dir / "last_recording_processed.wav"

    @property
    def raw_path(self) -> Path:
        """Path to raw transcription (before grammar fix)."""
        return self._dir / "last_raw.txt"

    @property
    def text_path(self) -> Path:
        """Path to final transcription text."""
        return self._dir / "last_transcription.txt"

    @property
    def history_dir(self) -> Path:
        """Directory for all history files."""
        return self._history_dir

    @property
    def audio_history_dir(self) -> Path:
        """Directory for all audio history files."""
        return self._audio_history_dir

    def _history_filename(self) -> Path:
        """Generate a unique history filename using timestamp + microseconds."""
        # Use full microsecond precision to avoid collisions
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return self._history_dir / f"{ts}.txt"

    def save_audio(self, data: np.ndarray) -> Path:
        """Save audio data to WAV file.

        Writes to last_recording.wav (for retry) AND a timestamped copy in
        audio_history/ so previous recordings are never lost. Keeps the last
        history_limit recordings and prunes older ones.
        """
        config = get_config()
        # Clean up stale segment files from previous long recordings
        for seg_file in glob.glob(os.path.join(self._dir, "last_recording_[0-9]*.wav")):
            try:
                os.remove(seg_file)
            except OSError:
                pass
        with self._lock:
            try:
                safe = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
                safe = np.clip(safe, -1.0, 1.0)
                audio_int16 = (safe * 32767).astype(np.int16)
                audio_bytes = audio_int16.tobytes()

                # Write to the canonical last_recording.wav (for retry)
                with wave.open(str(self.audio_path), 'wb') as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(config.audio.sample_rate)
                    w.writeframes(audio_bytes)

                # Also write a timestamped copy to audio_history/
                try:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    history_path = self._audio_history_dir / f"{ts}.wav"
                    with wave.open(str(history_path), 'wb') as w:
                        w.setnchannels(1)
                        w.setsampwidth(2)
                        w.setframerate(config.audio.sample_rate)
                        w.writeframes(audio_bytes)
                    self._prune_audio_history()
                except Exception as e:
                    log(f"Audio history save warning: {e}", "WARN")

                return self.audio_path
            except Exception as e:
                log(f"Save failed: {e}", "ERR")
                return None

    def _prune_audio_history(self):
        """Remove oldest audio history files, keeping history_limit most recent."""
        try:
            limit = get_config().backup.history_limit
            wav_files = sorted(
                self._audio_history_dir.glob("*.wav"),
                key=lambda p: p.name,
                reverse=True,
            )
            for old_file in wav_files[limit:]:
                try:
                    old_file.unlink()
                except OSError:
                    pass
        except Exception:
            pass  # Non-critical; don't let pruning failures break anything

    def save_raw(self, text: str):
        """Save raw transcription (before grammar fix)."""
        with self._lock:
            try:
                self.raw_path.write_text(text, encoding='utf-8')
            except Exception as e:
                log(f"Save raw failed: {e}", "ERR")

    def save_text(self, text: str):
        """Save final corrected text."""
        with self._lock:
            try:
                self.text_path.write_text(text, encoding='utf-8')
            except Exception as e:
                log(f"Save text failed: {e}", "ERR")

    def save_history(self, raw_text: str, final_text: str):
        """Save raw + final transcript for this session."""
        if not raw_text and not final_text:
            return
        raw_text = raw_text or ""
        final_text = final_text or raw_text
        payload = f"RAW:\n{raw_text}\n\nFIXED:\n{final_text}"
        with self._lock:
            try:
                path = self._history_filename()
                # Use exclusive creation mode to handle the unlikely case of collision
                try:
                    with open(path, 'x', encoding='utf-8') as f:
                        f.write(payload)
                except FileExistsError:
                    # Extremely rare: add process ID if collision occurs
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    path = self._history_dir / f"{ts}_{os.getpid()}.txt"
                    path.write_text(payload, encoding='utf-8')
                self._prune_text_history()
            except Exception as e:
                log(f"Save history failed: {e}", "ERR")

    def save_processed_audio(self, data: np.ndarray) -> Path:
        """Save processed audio for transcription (separate from raw backup)."""
        config = get_config()
        with self._lock:
            try:
                safe = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
                safe = np.clip(safe, -1.0, 1.0)
                audio = (safe * 32767).astype(np.int16)
                with wave.open(str(self.processed_audio_path), 'wb') as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(config.audio.sample_rate)
                    w.writeframes(audio.tobytes())
                return self.processed_audio_path
            except Exception as e:
                log(f"Save processed audio failed: {e}", "ERR")
                return None

    def save_audio_segment(self, data: np.ndarray, index: int) -> Path:
        """Save a segment of a long recording. Returns path."""
        config = get_config()
        path = self._dir / f"last_recording_{index}.wav"
        with self._lock:
            try:
                safe = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
                safe = np.clip(safe, -1.0, 1.0)
                audio = (safe * 32767).astype(np.int16)
                with wave.open(str(path), 'wb') as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(config.audio.sample_rate)
                    w.writeframes(audio.tobytes())
                return path
            except Exception as e:
                log(f"Save segment failed: {e}", "ERR")
                return None

    def get_audio(self) -> Path:
        """Get path to last audio file, or None if missing."""
        return self.audio_path if self.audio_path.exists() else None

    def get_text(self) -> str:
        """Get last transcription text, or None if missing."""
        if self.text_path.exists():
            try:
                return self.text_path.read_text('utf-8')
            except Exception as e:
                log(f"Read text failed: {e}", "ERR")
        return None

    def get_history(self, limit: int = 100) -> list:
        """Read text history files, newest first.

        Returns a list of dicts with keys: path, timestamp, raw, fixed.
        """
        results = []
        try:
            txt_files = sorted(
                self._history_dir.glob("*.txt"),
                key=lambda p: p.name,
                reverse=True,
            )
            for path in txt_files[:limit]:
                try:
                    # Parse timestamp from filename (YYYYMMDD_HHMMSS_ffffff[_pid].txt)
                    stem = path.stem.split("_")
                    # stem[0]=date, stem[1]=time, stem[2]=microseconds
                    ts_str = f"{stem[0]}_{stem[1]}_{stem[2]}"
                    ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S_%f")
                except (ValueError, IndexError):
                    ts = datetime.fromtimestamp(path.stat().st_mtime)

                try:
                    content = path.read_text(encoding='utf-8')
                    raw = ""
                    fixed = ""
                    if "RAW:\n" in content and "\n\nFIXED:\n" in content:
                        parts = content.split("\n\nFIXED:\n", 1)
                        raw = parts[0].removeprefix("RAW:\n")
                        fixed = parts[1] if len(parts) > 1 else raw
                    else:
                        raw = content
                        fixed = content
                    results.append({"path": path, "timestamp": ts, "raw": raw, "fixed": fixed})
                except Exception as e:
                    log(f"History read error ({path.name}): {e}", "WARN")
        except Exception as e:
            log(f"History listing error: {e}", "WARN")
        return results

    def get_audio_history(self) -> list:
        """Return audio history files, newest first.

        Returns a list of dicts with keys: path, timestamp.
        """
        results = []
        try:
            wav_files = sorted(
                self._audio_history_dir.glob("*.wav"),
                key=lambda p: p.name,
                reverse=True,
            )
            for path in wav_files:
                try:
                    stem = path.stem.split("_")
                    ts_str = f"{stem[0]}_{stem[1]}_{stem[2]}"
                    ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S_%f")
                except (ValueError, IndexError):
                    ts = datetime.fromtimestamp(path.stat().st_mtime)
                results.append({"path": path, "timestamp": ts})
        except Exception as e:
            log(f"Audio history listing error: {e}", "WARN")
        return results

    def _prune_text_history(self):
        """Remove oldest text history files, keeping history_limit most recent."""
        try:
            limit = get_config().backup.history_limit
            txt_files = sorted(
                self._history_dir.glob("*.txt"),
                key=lambda p: p.name,
                reverse=True,
            )
            for old_file in txt_files[limit:]:
                try:
                    old_file.unlink()
                except OSError:
                    pass
        except Exception:
            pass  # Non-critical; don't let pruning failures break anything

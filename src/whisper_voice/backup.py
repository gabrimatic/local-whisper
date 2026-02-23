# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Backup manager for Local Whisper.

Handles persistence of audio recordings and transcriptions.
"""

import os
import wave
import threading
from pathlib import Path
from datetime import datetime

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
        self._lock = threading.Lock()

    @property
    def audio_path(self) -> Path:
        """Path to last recording audio file."""
        return self._dir / "last_recording.wav"

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

    def _history_filename(self) -> Path:
        """Generate a unique history filename using timestamp + microseconds."""
        # Use full microsecond precision to avoid collisions
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return self._history_dir / f"{ts}.txt"

    def save_audio(self, data: np.ndarray) -> Path:
        """Save audio data to WAV file."""
        config = get_config()
        with self._lock:
            try:
                safe = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
                audio = (safe * 32767).astype(np.int16)
                with wave.open(str(self.audio_path), 'wb') as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(config.audio.sample_rate)
                    w.writeframes(audio.tobytes())
                return self.audio_path
            except Exception as e:
                log(f"Save failed: {e}", "ERR")
                return None

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
            except Exception as e:
                log(f"Save history failed: {e}", "ERR")

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

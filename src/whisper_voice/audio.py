# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Audio recording functionality for Local Whisper.
"""

import time
import threading

import sounddevice as sd
import numpy as np

from .config import get_config
from .utils import log


class Recorder:
    """Microphone audio recorder with thread-safe start/stop."""

    def __init__(self):
        self._recording = threading.Event()
        self._chunks = []
        self._chunks_lock = threading.Lock()
        self._stream = None
        self._state_lock = threading.Lock()
        self._start_time = None
        self._current_rms: float = 0.0

        config = get_config()
        buf_size = int(config.audio.sample_rate * config.audio.pre_buffer) if config.audio.pre_buffer > 0 else 0
        self._pre_buffer: np.ndarray = np.zeros(buf_size, dtype=np.float32)
        self._pre_buffer_pos: int = 0
        self._monitor_stream = None

    @property
    def recording(self) -> bool:
        """Whether recording is currently active."""
        return self._recording.is_set()

    @property
    def duration(self) -> float:
        """Get current recording duration in seconds."""
        if self._start_time and self._recording.is_set():
            return time.time() - self._start_time
        return 0.0

    @property
    def rms_level(self) -> float:
        """Current audio RMS level (0.0-1.0), updated each callback."""
        return self._current_rms

    def start_monitoring(self):
        """Start pre-recording monitor (lightweight, always-on when ready)."""
        config = get_config()
        if config.audio.pre_buffer <= 0:
            return
        try:
            self._monitor_stream = sd.InputStream(
                samplerate=config.audio.sample_rate,
                channels=1,
                dtype=np.float32,
                callback=self._monitor_callback,
                blocksize=512
            )
            self._monitor_stream.start()
        except Exception as e:
            log(f"Monitor stream warning: {e}", "WARN")
            self._monitor_stream = None

    def stop_monitoring(self):
        """Stop the pre-recording monitor."""
        if self._monitor_stream:
            try:
                self._monitor_stream.stop()
                self._monitor_stream.close()
            except Exception:
                pass
            self._monitor_stream = None

    def _monitor_callback(self, data, frames, time_info, status):
        """Fill ring buffer with latest audio."""
        flat = data[:, 0]
        n = len(flat)
        buf_size = len(self._pre_buffer)
        if buf_size == 0:
            return
        if n >= buf_size:
            self._pre_buffer[:] = flat[-buf_size:]
            self._pre_buffer_pos = 0
        else:
            end = self._pre_buffer_pos + n
            if end <= buf_size:
                self._pre_buffer[self._pre_buffer_pos:end] = flat
            else:
                first = buf_size - self._pre_buffer_pos
                self._pre_buffer[self._pre_buffer_pos:] = flat[:first]
                self._pre_buffer[:n - first] = flat[first:]
            self._pre_buffer_pos = end % buf_size

    def start(self) -> bool:
        """Start recording audio from microphone."""
        config = get_config()
        with self._state_lock:
            if self._recording.is_set():
                return False
            try:
                self.stop_monitoring()
                with self._chunks_lock:
                    if config.audio.pre_buffer > 0 and len(self._pre_buffer) > 0:
                        pre = np.roll(self._pre_buffer, -self._pre_buffer_pos)
                        self._chunks = [pre.copy()]
                    else:
                        self._chunks = []
                self._start_time = time.time()
                self._stream = sd.InputStream(
                    samplerate=config.audio.sample_rate,
                    channels=1,
                    dtype=np.float32,
                    callback=self._callback,
                    blocksize=1024
                )
                self._stream.start()
                self._recording.set()
                return True
            except Exception as e:
                log(f"Mic error: {e}", "ERR")
                self._recording.clear()
                return False

    def stop(self) -> np.ndarray:
        """Stop recording and return audio data."""
        with self._state_lock:
            if not self._recording.is_set():
                return np.array([], dtype=np.float32)
            self._recording.clear()
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception as e:
                    log(f"Stream cleanup warning: {e}", "WARN")
                self._stream = None
            with self._chunks_lock:
                if self._chunks:
                    return np.concatenate(self._chunks)
                return np.array([], dtype=np.float32)

    def _callback(self, data, frames, time_info, status):
        """Audio stream callback - accumulate chunks (thread-safe)."""
        # Check recording flag inside lock to prevent race with stop()
        with self._chunks_lock:
            if self._recording.is_set():
                self._chunks.append(data.copy())
        self._current_rms = float(np.sqrt(np.mean(data ** 2)))

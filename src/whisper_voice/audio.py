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

    def start(self) -> bool:
        """Start recording audio from microphone."""
        config = get_config()
        with self._state_lock:
            if self._recording.is_set():
                return False
            try:
                with self._chunks_lock:
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

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Kokoro TTS provider via kokoro-mlx (Apple Silicon, fully offline)."""

import threading
import time
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from ..utils import log
from .base import TTSProvider

_MAX_CHARS = 2000
_SAMPLE_RATE = 24000


class KokoroTTSProvider(TTSProvider):
    """
    Kokoro-82M TTS via kokoro-mlx. Runs in-process on Apple Silicon.

    The model is downloaded by setup.sh to ~/.whisper/models/ and runs
    fully offline at runtime (HF_HUB_OFFLINE=1). Model is loaded lazily
    on first use and kept in memory.
    """

    def __init__(self) -> None:
        self._model_id: str = ""
        self._model = None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "Kokoro"

    def start(self) -> bool:
        return True

    def running(self) -> bool:
        return True

    def refresh(self, model_id: str) -> None:
        """Unload model if model_id changed so it is reloaded on next speak()."""
        with self._lock:
            if model_id != self._model_id:
                self._model = None
                self._model_id = model_id

    def _load_model(self, model_id: str) -> bool:
        """Load model lazily (thread-safe). Returns True on success."""
        with self._lock:
            if self._model is not None and self._model_id == model_id:
                return True

        try:
            log(f"Loading Kokoro model: {model_id}...", "INFO")
            from kokoro_mlx import KokoroTTS
            model = KokoroTTS.from_pretrained(model_id)
            with self._lock:
                self._model = model
                self._model_id = model_id
            log("Kokoro model loaded", "OK")
            return True
        except ImportError:
            log("kokoro-mlx not available — run: pip install git+https://github.com/gabrimatic/kokoro-mlx", "ERR")
            return False
        except Exception as e:
            log(f"Failed to load Kokoro model: {e}", "ERR")
            return False

    def speak(
        self,
        text: str,
        stop_event: threading.Event,
        speaker: str = "af_sky",
        on_playback_start: Optional[Callable] = None,
    ) -> None:
        if not text.strip():
            return

        with self._lock:
            model_id = self._model_id

        if not self._load_model(model_id):
            return

        with self._lock:
            model = self._model

        chunks = _split_text(text, _MAX_CHARS)
        first_chunk = True
        for chunk in chunks:
            if stop_event.is_set():
                return
            _synthesize_and_play(
                model, chunk, speaker, stop_event,
                on_playback_start=on_playback_start if first_chunk else None,
            )
            first_chunk = False

    def close(self) -> None:
        sd.stop()
        with self._lock:
            self._model = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _synthesize_and_play(
    model,
    text: str,
    voice: str,
    stop_event: threading.Event,
    on_playback_start: Optional[Callable] = None,
) -> None:
    try:
        sample_rate = getattr(model, "SAMPLE_RATE", _SAMPLE_RATE)
        first = True

        for audio in model.generate_stream(text, voice=voice):
            if stop_event.is_set():
                sd.stop()
                return

            audio = np.asarray(audio, dtype=np.float32)
            if audio.ndim > 1:
                audio = audio.flatten()
            if len(audio) == 0:
                continue

            if first and on_playback_start is not None:
                try:
                    on_playback_start()
                except Exception:
                    pass
                first = False

            sd.play(audio, samplerate=sample_rate)
            duration = len(audio) / sample_rate
            deadline = time.monotonic() + duration + 0.15
            while time.monotonic() < deadline:
                if stop_event.is_set():
                    sd.stop()
                    return
                time.sleep(0.04)
            sd.wait()

    except Exception as e:
        log(f"Kokoro synthesis error: {e}", "ERR")
        sd.stop()


def _split_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current and current_len + len(para) > max_chars:
            chunks.append("\n\n".join(current))
            current, current_len = [para], len(para)
        else:
            current.append(para)
            current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))

    return chunks

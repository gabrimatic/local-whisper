# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Kokoro TTS provider via kokoro-mlx (Apple Silicon, fully offline)."""

import gc
import queue
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from ..utils import log
from .base import TTSProvider

_MAX_CHARS = 2000
_SAMPLE_RATE = 48000


class KokoroTTSProvider(TTSProvider):
    """
    Kokoro-82M TTS via kokoro-mlx. Runs in-process on Apple Silicon.

    The model is downloaded on first use to ~/.whisper/models/ and cached.
    Subsequent loads are offline from the local cache. Model is loaded
    lazily on first use and kept in memory.
    """

    def __init__(self) -> None:
        self._model_id: str = ""
        self._model = None
        self._lock = threading.Lock()
        self._speak_lock = threading.Lock()
        # Separate lock for the actual model load. Held across the expensive
        # from_pretrained() call so only one thread pays the download cost.
        self._load_lock = threading.Lock()

    @property
    def name(self) -> str:
        return "Kokoro"

    def start(self) -> bool:
        return True

    def running(self) -> bool:
        return True

    def refresh(self, model_id: str) -> None:
        """Unload model if model_id changed so it is reloaded on next speak()."""
        released = False
        with self._lock:
            if model_id != self._model_id:
                self._release_model_locked()
                self._model_id = model_id
                released = True
        if released:
            _clear_runtime_cache()

    def _load_model(self, model_id: str) -> bool:
        """Load model lazily (thread-safe). Returns True on success.

        The load lock serializes concurrent callers so two threads never pay the
        download/load cost in parallel. Once one thread finishes, other waiters
        see the cached model and return immediately.
        """
        with self._load_lock:
            with self._lock:
                if self._model is not None and self._model_id == model_id:
                    return True
            try:
                log(f"Loading Kokoro model: {model_id}...", "INFO")
                from kokoro_mlx import KokoroTTS
                model = KokoroTTS.from_pretrained(model_id)
                with self._lock:
                    if self._model is not None and self._model_id != model_id:
                        self._release_model_locked()
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
        if model is None:
            return

        with self._speak_lock:
            try:
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
            finally:
                _clear_runtime_cache()

    def unload(self) -> None:
        """Release model from RAM. Will lazy-reload on next speak()."""
        with self._lock:
            self._release_model_locked()
        _clear_runtime_cache()
        log("Kokoro model unloaded (idle)", "INFO")

    def close(self) -> None:
        sd.stop()
        with self._lock:
            self._release_model_locked()
            self._model_id = ""
        _clear_runtime_cache()

    def _release_model_locked(self) -> None:
        if self._model is None:
            return
        try:
            self._model.close()
        except Exception:
            pass
        self._model = None


def _clear_runtime_cache() -> None:
    gc.collect()
    try:
        import mlx.core as mx

        mx.clear_cache()
    except Exception:
        pass


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
    audio_q: queue.Queue[np.ndarray | None] = queue.Queue()
    first_chunk_ready = threading.Event()
    finished = threading.Event()

    def _produce() -> None:
        try:
            for audio in model.generate_stream(text, voice=voice, sample_rate=_SAMPLE_RATE):
                if stop_event.is_set():
                    return
                audio = np.asarray(audio, dtype=np.float32)
                if audio.ndim > 1:
                    audio = audio.flatten()
                if len(audio) > 0:
                    audio_q.put(audio)
                    first_chunk_ready.set()
        except Exception as e:
            log(f"Kokoro synthesis error: {e}", "ERR")
        finally:
            audio_q.put(None)
            first_chunk_ready.set()

    producer = threading.Thread(target=_produce, daemon=True)
    producer.start()

    # Wait for at least one chunk before opening the audio stream.
    first_chunk_ready.wait()
    if stop_event.is_set() or audio_q.empty():
        producer.join(timeout=2.0)
        return

    playback_started = False
    write_size = _SAMPLE_RATE // 10  # 100ms pieces

    try:
        with sd.OutputStream(samplerate=_SAMPLE_RATE, channels=1, dtype="float32") as stream:
            while not finished.is_set():
                if stop_event.is_set():
                    break
                try:
                    chunk = audio_q.get(timeout=0.05)
                except queue.Empty:
                    continue
                if chunk is None:
                    finished.set()
                    break

                if not playback_started:
                    playback_started = True
                    if on_playback_start is not None:
                        try:
                            on_playback_start()
                        except Exception:
                            pass

                for i in range(0, len(chunk), write_size):
                    if stop_event.is_set():
                        break
                    piece = chunk[i : i + write_size]
                    stream.write(piece.reshape(-1, 1))
    except Exception as e:
        log(f"Kokoro playback error: {e}", "ERR")

    producer.join(timeout=2.0)


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

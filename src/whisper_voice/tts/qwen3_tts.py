# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Qwen3-TTS provider via mlx-audio."""

import threading
import time
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from ..utils import log
from .base import TTSProvider

# Maximum characters to send in a single TTS call (prevents OOM for very long text)
_MAX_CHARS = 2000

# Variant detection by model_id substring
_VARIANT_CUSTOM_VOICE = "CustomVoice"
_VARIANT_VOICE_DESIGN = "VoiceDesign"


class Qwen3TTSProvider(TTSProvider):
    """
    Qwen3-TTS via mlx-audio. Runs in-process on Apple Silicon (no server subprocess).

    Supports three model variants:
      - CustomVoice: built-in named speakers + optional style instruction
      - VoiceDesign: voice described in text
      - Base: voice cloning from a reference audio clip

    The model is loaded lazily on first use and kept in memory.
    """

    def __init__(self):
        self._model_id: str = ""
        self._model = None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "Qwen3-TTS"

    def start(self) -> bool:
        return True

    def running(self) -> bool:
        return True

    def refresh(self, model_id: str) -> None:
        """Reload model if model_id changed."""
        with self._lock:
            if model_id != self._model_id:
                self._model = None
                self._model_id = model_id

    def _load_model(self, model_id: str) -> bool:
        """Load model (thread-safe). Returns True on success."""
        with self._lock:
            if self._model is not None and self._model_id == model_id:
                return True
        try:
            log(f"Loading Qwen3-TTS model: {model_id}...", "INFO")
            from mlx_audio.tts.utils import load_model
            model = load_model(model_id)
            with self._lock:
                self._model = model
                self._model_id = model_id
            log("Qwen3-TTS model loaded", "OK")
            return True
        except ImportError:
            log("mlx-audio TTS module not available — update mlx-audio: pip install -U mlx-audio", "ERR")
            return False
        except Exception as e:
            log(f"Failed to load Qwen3-TTS model: {e}", "ERR")
            return False

    def speak(self, text: str, stop_event: threading.Event,
              speaker: str = "Vivian", language: str = "English",
              instruct: str = "",
              on_playback_start: Optional[Callable] = None) -> None:
        """Synthesize and play text, streaming chunks as they're generated."""
        if not text.strip():
            return

        with self._lock:
            model_id = self._model_id

        if not self._load_model(model_id):
            return

        with self._lock:
            model = self._model

        variant = _detect_variant(model_id)
        chunks = _split_text(text, _MAX_CHARS)

        first_chunk = True
        for chunk in chunks:
            if stop_event.is_set():
                return
            if first_chunk:
                _synthesize_and_play(model, chunk, variant, speaker, language, instruct, stop_event,
                                     on_playback_start=on_playback_start)
                first_chunk = False
            else:
                _synthesize_and_play(model, chunk, variant, speaker, language, instruct, stop_event)

    def close(self) -> None:
        sd.stop()
        with self._lock:
            self._model = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_variant(model_id: str) -> str:
    if _VARIANT_CUSTOM_VOICE in model_id:
        return "custom_voice"
    if _VARIANT_VOICE_DESIGN in model_id:
        return "voice_design"
    return "base"


def _synthesize_and_play(model, text: str, variant: str, speaker: str,
                         language: str, instruct: str,
                         stop_event: threading.Event,
                         on_playback_start: Optional[Callable] = None) -> None:
    """Generate audio for a single text chunk and play it, respecting stop_event."""
    try:
        if variant == "custom_voice":
            generator = model.generate_custom_voice(
                text=text,
                speaker=speaker,
                language=language,
                instruct=instruct,
            )
        elif variant == "voice_design":
            generator = model.generate_voice_design(
                text=text,
                language=language,
                instruct=instruct if instruct else "A clear, neutral voice.",
            )
        else:
            # Base model — basic synthesis without built-in speakers
            generator = model.generate(text=text)

        first = True
        for result in generator:
            if stop_event.is_set():
                sd.stop()
                return

            audio = np.array(result.audio)
            if audio.ndim > 1:
                audio = audio.flatten()
            audio = audio.astype(np.float32)
            if len(audio) == 0:
                continue

            # Signal the caller that audio is about to start playing
            if first and on_playback_start is not None:
                try:
                    on_playback_start()
                except Exception:
                    pass
                first = False

            sd.play(audio, samplerate=model.sample_rate)
            duration = len(audio) / model.sample_rate
            deadline = time.monotonic() + duration + 0.15
            while time.monotonic() < deadline:
                if stop_event.is_set():
                    sd.stop()
                    return
                time.sleep(0.04)
            sd.wait()

    except Exception as e:
        log(f"Qwen3-TTS synthesis error: {e}", "ERR")
        sd.stop()


def _split_text(text: str, max_chars: int) -> list:
    """Split text at paragraph boundaries, respecting max_chars."""
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks = []
    current: list = []
    current_len = 0

    for para in paragraphs:
        if current and current_len + len(para) > max_chars:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))

    return chunks

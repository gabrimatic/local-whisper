# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Qwen3-ASR transcription engine for Local Whisper.

Uses mlx-audio to run Qwen3-ASR locally via MLX, supporting up to 20 minutes
of audio natively without chunking.
"""

import concurrent.futures
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from .base import TranscriptionEngine
from ..config import get_config
from ..utils import log

_DEFAULT_MODEL = "mlx-community/Qwen3-ASR-1.7B-bf16"

# Maps ISO 639-1 language codes to the full names Qwen3-ASR expects.
LANGUAGE_MAP = {
    "en": "English", "zh": "Chinese", "ja": "Japanese", "ko": "Korean",
    "de": "German", "fr": "French", "es": "Spanish", "pt": "Portuguese",
    "it": "Italian", "nl": "Dutch", "ru": "Russian", "ar": "Arabic",
    "tr": "Turkish", "pl": "Polish", "sv": "Swedish", "da": "Danish",
    "fi": "Finnish", "no": "Norwegian", "cs": "Czech", "ro": "Romanian",
    "hu": "Hungarian", "el": "Greek", "he": "Hebrew", "th": "Thai",
    "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay", "hi": "Hindi",
    "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "ur": "Urdu",
    "fa": "Persian", "uk": "Ukrainian", "bg": "Bulgarian", "hr": "Croatian",
    "sk": "Slovak", "sl": "Slovenian", "lt": "Lithuanian", "lv": "Latvian",
    "et": "Estonian", "ca": "Catalan", "gl": "Galician", "eu": "Basque",
    "cy": "Welsh", "ga": "Irish",
}


class Qwen3ASREngine(TranscriptionEngine):
    """Transcription engine backed by Qwen3-ASR via mlx-audio."""

    def __init__(self):
        self._model = None
        self._timeout = 0

    @property
    def name(self) -> str:
        return "Qwen3-ASR"

    @property
    def supports_long_audio(self) -> bool:
        return True

    def start(self) -> bool:
        config = get_config()
        qwen_cfg = getattr(config, "qwen3_asr", None)
        model_name = getattr(qwen_cfg, "model", _DEFAULT_MODEL) if qwen_cfg else _DEFAULT_MODEL
        self._timeout = getattr(qwen_cfg, "timeout", 0) if qwen_cfg else 0

        log(f"Loading Qwen3-ASR model ({model_name})...", "INFO")
        try:
            from mlx_audio.stt.utils import load_model
            self._model = load_model(model_name)
        except ImportError:
            log("mlx-audio is not installed. Run: pip install mlx-audio", "ERR")
            return False
        except Exception as e:
            log(f"Qwen3-ASR failed to load: {e}", "ERR")
            return False

        # Warm up the MLX compute graph so the first real transcription is fast.
        log("Warming up Qwen3-ASR...", "INFO")
        try:
            import numpy as np
            import soundfile as sf

            silence = np.zeros(8000, dtype=np.float32)  # 0.5s at 16kHz
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                sf.write(tmp.name, silence, 16000)
                self._model.generate(tmp.name, max_tokens=1)
        except Exception:
            pass  # Warm-up failure is non-fatal

        log("Qwen3-ASR ready", "OK")
        return True

    def running(self) -> bool:
        return self._model is not None

    def transcribe(self, path: Path) -> Tuple[Optional[str], Optional[str]]:
        if self._model is None:
            return None, "Model not loaded"

        try:
            config = get_config()
            qwen3_cfg = getattr(config, "qwen3_asr", None)
            language = getattr(qwen3_cfg, "language", "auto") if qwen3_cfg else "auto"
            prefill_step_size = getattr(qwen3_cfg, "prefill_step_size", 4096) if qwen3_cfg else 4096
            timeout = getattr(qwen3_cfg, "timeout", self._timeout) if qwen3_cfg else self._timeout

            # Compute a duration-scaled token budget to avoid wasteful generation.
            max_tokens = 8192
            try:
                import soundfile as sf
                info = sf.info(str(path))
                max_tokens = max(256, int(info.duration * 50))
            except Exception:
                pass  # Fall back to the safe default

            kwargs: dict = {
                "max_tokens": max_tokens,
                "repetition_penalty": 1.2,
                "prefill_step_size": prefill_step_size,
            }

            # Only pass language when explicitly set; let the model auto-detect otherwise.
            if language and language.lower() not in ("auto", ""):
                full_name = LANGUAGE_MAP.get(language.lower(), language)
                kwargs["language"] = full_name

            timeout_val = timeout if timeout and timeout > 0 else None
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._model.generate, str(path), **kwargs)
                try:
                    result = future.result(timeout=timeout_val)
                except concurrent.futures.TimeoutError:
                    return None, f"Transcription timed out after {timeout_val}s"

            text = result.text.strip() if result and hasattr(result, "text") and result.text else ""
            if text:
                return text, None
            return None, "Empty transcription"
        except Exception as e:
            return None, str(e)

    def close(self) -> None:
        self._model = None
        try:
            import gc
            import mlx.core as mx
            gc.collect()
            mx.clear_cache()
        except Exception:
            pass
        log("Qwen3-ASR model unloaded", "INFO")

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Qwen3-ASR transcription engine for Local Whisper.

Uses qwen3-asr-mlx to run Qwen3-ASR locally via MLX, supporting up to 20 minutes
of audio natively without chunking.
"""

import concurrent.futures
from pathlib import Path
from typing import Optional, Tuple

from ..config import get_config
from ..utils import log
from .base import TranscriptionEngine

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
    """Transcription engine backed by Qwen3-ASR via qwen3-asr-mlx."""

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
            from qwen3_asr_mlx import Qwen3ASR
            self._model = Qwen3ASR.from_pretrained(model_name)
        except ImportError:
            log("qwen3-asr-mlx is not installed. Run: pip install qwen3-asr-mlx", "ERR")
            return False
        except Exception as e:
            log(f"Qwen3-ASR failed to load: {e}", "ERR")
            return False

        log("Warming up Qwen3-ASR...", "INFO")
        try:
            self._model.warm_up()
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
            timeout = getattr(qwen3_cfg, "timeout", self._timeout) if qwen3_cfg else self._timeout

            temperature = getattr(qwen3_cfg, "temperature", 0.0) if qwen3_cfg else 0.0
            top_p = getattr(qwen3_cfg, "top_p", 1.0) if qwen3_cfg else 1.0
            top_k = getattr(qwen3_cfg, "top_k", 0) if qwen3_cfg else 0
            chunk_duration = getattr(qwen3_cfg, "chunk_duration", 1200.0) if qwen3_cfg else 1200.0

            kwargs: dict = {
                "repetition_penalty": getattr(qwen3_cfg, "repetition_penalty", 1.2) if qwen3_cfg else 1.2,
                "temperature": temperature,
                "top_p": top_p,
                "top_k": top_k,
                "chunk_duration": chunk_duration,
            }

            # Only pass language when explicitly set; let the model auto-detect otherwise.
            if language and language.lower() not in ("auto", ""):
                full_name = LANGUAGE_MAP.get(language.lower(), language)
                kwargs["language"] = full_name

            timeout_val = timeout if timeout and timeout > 0 else None
            if timeout_val is None:
                result = self._model.transcribe(str(path), **kwargs)
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self._model.transcribe, str(path), **kwargs)
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
        if self._model is not None:
            try:
                self._model.close()
            except Exception:
                pass
        self._model = None
        log("Qwen3-ASR model unloaded", "INFO")

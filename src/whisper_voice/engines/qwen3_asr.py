# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Qwen3-ASR transcription engine for Local Whisper.

Uses mlx-audio to run Qwen3-ASR locally via MLX, supporting up to 20 minutes
of audio natively without chunking.
"""

from pathlib import Path
from typing import Optional, Tuple

from .base import TranscriptionEngine
from ..config import get_config
from ..utils import log

_DEFAULT_MODEL = "mlx-community/Qwen3-ASR-1.7B-8bit"


class Qwen3ASREngine(TranscriptionEngine):
    """Transcription engine backed by Qwen3-ASR via mlx-audio."""

    def __init__(self):
        self._model = None

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

        log(f"Loading Qwen3-ASR model ({model_name})...", "INFO")
        try:
            from mlx_audio.stt.utils import load_model
            self._model = load_model(model_name)
            log("Qwen3-ASR ready", "OK")
            return True
        except ImportError:
            log("mlx-audio is not installed. Run: pip install mlx-audio", "ERR")
            return False
        except Exception as e:
            log(f"Qwen3-ASR failed to load: {e}", "ERR")
            return False

    def running(self) -> bool:
        return self._model is not None

    def transcribe(self, path: Path) -> Tuple[Optional[str], Optional[str]]:
        if self._model is None:
            return None, "Model not loaded"

        try:
            config = get_config()
            qwen3_cfg = getattr(config, "qwen3_asr", None)
            language = getattr(qwen3_cfg, "language", "auto") if qwen3_cfg else "auto"

            kwargs = {}
            if language and language.lower() not in ("auto", ""):
                kwargs["language"] = language

            result = self._model.generate(str(path), **kwargs)
            text = result.text.strip() if result and hasattr(result, "text") and result.text else ""
            if text:
                return text, None
            return None, "Empty transcription"
        except Exception as e:
            return None, str(e)

    def close(self) -> None:
        self._model = None
        log("Qwen3-ASR model unloaded", "INFO")

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Transcription module for Local Whisper.

This module provides a unified interface to transcription engines.
The engine is selected based on the [transcription] configuration.

Supported engines:
- qwen3_asr: On-device MLX transcription via Qwen3-ASR (default)
- whisperkit: Local WhisperKit server

Usage:
    from whisper_voice.transcriber import Transcriber

    t = Transcriber()
    if t.start():
        text, error = t.transcribe(path)
    t.close()
"""

from pathlib import Path
from typing import Optional, Tuple

from .config import get_config
from .engines import TranscriptionEngine, create_engine
from .utils import log


class Transcriber:
    """
    Unified transcription interface.

    Wraps the configured engine and provides a consistent API.
    """

    def __init__(self, engine_id: str = None):
        if engine_id is None:
            engine_id = get_config().transcription.engine
        try:
            self._engine: TranscriptionEngine = create_engine(engine_id)
            log(f"Transcription engine: {self._engine.name}", "INFO")
        except ValueError as e:
            log(f"Failed to create transcription engine '{engine_id}': {e}", "ERR")
            raise

    def start(self) -> bool:
        """Initialize and verify engine availability."""
        return self._engine.start()

    def running(self) -> bool:
        """Check if the engine is ready to accept transcription requests."""
        return self._engine.running()

    def transcribe(self, path: Path) -> Tuple[Optional[str], Optional[str]]:
        """
        Transcribe an audio file.

        Args:
            path: Path to the audio file to transcribe.

        Returns:
            Tuple of (text, error_message).
            On success, error_message is None.
            On error, text is None and error_message describes the failure.
        """
        return self._engine.transcribe(path)

    def unload(self) -> None:
        """Release engine model from RAM. Call start() to reload."""
        if hasattr(self._engine, 'unload'):
            self._engine.unload()

    def ensure_loaded(self) -> bool:
        """Reload engine if it was unloaded. Returns True if ready."""
        if self._engine.running():
            return True
        log("Reloading transcription engine...", "INFO")
        return self._engine.start()

    def reload(self) -> bool:
        """Force close + start. Use after an abandoned transcription to reset MLX state."""
        log(f"Forcing {self._engine.name} reload after pipeline abandonment", "WARN")
        try:
            self._engine.close()
        except Exception as e:
            log(f"Close during reload failed: {e}", "WARN")
        return self._engine.start()

    def close(self) -> None:
        """Release all engine resources."""
        self._engine.close()

    @property
    def supports_long_audio(self) -> bool:
        """Whether the engine handles audio >28s natively without chunking."""
        return self._engine.supports_long_audio

    @property
    def name(self) -> str:
        """Human-readable name of the active engine."""
        return self._engine.name

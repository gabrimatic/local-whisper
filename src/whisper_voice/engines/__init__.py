# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Transcription engines for Local Whisper.

To add a new engine:
1. Create a new folder under engines/ with __init__.py and engine.py
2. Add an entry to ENGINE_REGISTRY below

Usage:
    from whisper_voice.engines import create_engine, ENGINE_REGISTRY

    engine = create_engine("whisperkit")
    if engine.start():
        text, error = engine.transcribe(path)
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .base import TranscriptionEngine


@dataclass
class EngineInfo:
    """Metadata for a transcription engine."""
    id: str                              # Config identifier (e.g., "whisperkit")
    name: str                            # Display name (e.g., "WhisperKit")
    description: str                     # Short description for menu
    factory: Callable[[], TranscriptionEngine]  # Function to create instance


def _create_qwen3_asr() -> TranscriptionEngine:
    from .qwen3_asr import Qwen3ASREngine
    return Qwen3ASREngine()


def _create_whisperkit() -> TranscriptionEngine:
    from .whisperkit import WhisperKitEngine
    return WhisperKitEngine()


# ============================================================================
# ENGINE REGISTRY - Add new engines here
# ============================================================================
ENGINE_REGISTRY: Dict[str, EngineInfo] = {
    "qwen3_asr": EngineInfo(
        id="qwen3_asr",
        name="Qwen3-ASR",
        description="On-device MLX transcription (no server required)",
        factory=_create_qwen3_asr,
    ),
    "whisperkit": EngineInfo(
        id="whisperkit",
        name="WhisperKit",
        description="Local WhisperKit server",
        factory=_create_whisperkit,
    ),
}


def create_engine(engine_id: str) -> TranscriptionEngine:
    """
    Factory function to create a transcription engine instance.

    Args:
        engine_id: Engine ID from ENGINE_REGISTRY

    Returns:
        An instance of the requested engine.

    Raises:
        ValueError: If engine_id is not recognized.
    """
    if engine_id not in ENGINE_REGISTRY:
        available = ", ".join(ENGINE_REGISTRY.keys())
        raise ValueError(f"Unknown engine: {engine_id}. Available: {available}")

    return ENGINE_REGISTRY[engine_id].factory()


def get_engine_info(engine_id: str) -> Optional[EngineInfo]:
    """Get metadata for an engine type."""
    return ENGINE_REGISTRY.get(engine_id)


def get_engine_choices() -> List[Tuple[str, str]]:
    """Return [(id, name), ...] for all registered engines, for use in UI."""
    return [(info.id, info.name) for info in ENGINE_REGISTRY.values()]


__all__ = [
    "TranscriptionEngine",
    "EngineInfo",
    "ENGINE_REGISTRY",
    "create_engine",
    "get_engine_info",
    "get_engine_choices",
]

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""TTS provider registry and factory."""

from dataclasses import dataclass
from typing import Callable, Dict

from .base import TTSProvider


@dataclass
class TTSProviderInfo:
    id: str
    name: str
    description: str
    factory: Callable[[], TTSProvider]


def _qwen3_tts_factory() -> TTSProvider:
    from .qwen3_tts import Qwen3TTSProvider
    return Qwen3TTSProvider()


TTS_REGISTRY: Dict[str, TTSProviderInfo] = {
    "qwen3_tts": TTSProviderInfo(
        id="qwen3_tts",
        name="Qwen3-TTS",
        description="On-device TTS via mlx-audio (Apple Silicon)",
        factory=_qwen3_tts_factory,
    ),
}


def create_tts_provider(provider_id: str) -> TTSProvider:
    info = TTS_REGISTRY.get(provider_id)
    if info is None:
        raise ValueError(f"Unknown TTS provider: {provider_id}")
    return info.factory()


def get_tts_provider_info(provider_id: str) -> TTSProviderInfo:
    return TTS_REGISTRY.get(provider_id)

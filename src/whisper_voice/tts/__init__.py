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


def _kokoro_factory() -> TTSProvider:
    from .kokoro_tts import KokoroTTSProvider
    return KokoroTTSProvider()


TTS_REGISTRY: Dict[str, TTSProviderInfo] = {
    "kokoro": TTSProviderInfo(
        id="kokoro",
        name="Kokoro",
        description="On-device TTS via kokoro-mlx (Apple Silicon, fast English)",
        factory=_kokoro_factory,
    ),
}


def create_tts_provider(provider_id: str) -> TTSProvider:
    info = TTS_REGISTRY.get(provider_id)
    if info is None:
        raise ValueError(f"Unknown TTS provider: {provider_id}")
    return info.factory()


def get_tts_provider_info(provider_id: str) -> TTSProviderInfo:
    return TTS_REGISTRY.get(provider_id)

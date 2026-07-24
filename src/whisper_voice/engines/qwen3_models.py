# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""First-class Qwen3-ASR model variants supported by the MLX runtime."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Qwen3ASRModel:
    id: str
    label: str
    quality: str
    memory: str
    latency: str
    supports_contextual_prompting: bool


DEFAULT_QWEN3_ASR_MODEL = "mlx-community/Qwen3-ASR-1.7B-bf16"

QWEN3_ASR_MODELS = (
    Qwen3ASRModel(
        id=DEFAULT_QWEN3_ASR_MODEL,
        label="1.7B · Higher quality",
        quality="higher",
        memory="higher",
        latency="higher",
        supports_contextual_prompting=True,
    ),
    Qwen3ASRModel(
        id="mlx-community/Qwen3-ASR-0.6B-bf16",
        label="0.6B · Lower memory and latency",
        quality="efficient",
        memory="lower",
        latency="lower",
        supports_contextual_prompting=True,
    ),
)

_MODEL_ALIASES = {
    "1.7b": DEFAULT_QWEN3_ASR_MODEL,
    "1.7": DEFAULT_QWEN3_ASR_MODEL,
    "0.6b": "mlx-community/Qwen3-ASR-0.6B-bf16",
    "0.6": "mlx-community/Qwen3-ASR-0.6B-bf16",
}


def resolve_qwen3_asr_model(value: str) -> str:
    """Resolve a documented size alias or exact supported model ID."""
    normalized = value.strip()
    alias = _MODEL_ALIASES.get(normalized.lower())
    if alias:
        return alias
    for model in QWEN3_ASR_MODELS:
        if normalized.lower() == model.id.lower():
            return model.id
    choices = ", ".join(("1.7b", "0.6b"))
    raise ValueError(f"Unknown Qwen3-ASR model '{value}'. Available: {choices}")


def qwen3_warm_sentinel_name(model_id: str) -> str:
    """Return a model-specific warm-up marker filename."""
    model_name = model_id.rsplit("/", 1)[-1]
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", model_name).strip("-")
    return f".qwen3_{slug or 'model'}_warmed"


def qwen3_model_supports_contextual_prompting(model_id: str) -> bool:
    """Whether a catalog model is validated with qwen3-asr-mlx context prompts."""
    return any(
        model.id.casefold() == model_id.strip().casefold()
        and model.supports_contextual_prompting
        for model in QWEN3_ASR_MODELS
    )


__all__ = [
    "DEFAULT_QWEN3_ASR_MODEL",
    "QWEN3_ASR_MODELS",
    "Qwen3ASRModel",
    "qwen3_warm_sentinel_name",
    "qwen3_model_supports_contextual_prompting",
    "resolve_qwen3_asr_model",
]

"""
Grammar correction backends for Local Whisper.

To add a new backend:
1. Create a new folder under backends/ with __init__.py and backend.py
2. Add an entry to BACKEND_REGISTRY below

Usage:
    from whisper_voice.backends import create_backend, BACKEND_REGISTRY

    backend = create_backend("ollama")
    if backend.start():
        corrected, error = backend.fix("some text")
"""

from dataclasses import dataclass
from typing import Callable, Dict, Optional

from .base import GrammarBackend


@dataclass
class BackendInfo:
    """Metadata for a grammar backend."""
    id: str                    # Config identifier (e.g., "ollama")
    name: str                  # Display name (e.g., "Ollama")
    description: str           # Short description for menu
    factory: Callable[[], GrammarBackend]  # Function to create instance


def _create_ollama() -> GrammarBackend:
    from .ollama import OllamaBackend
    return OllamaBackend()


def _create_apple_intelligence() -> GrammarBackend:
    from .apple_intelligence import AppleIntelligenceBackend
    return AppleIntelligenceBackend()


def _create_lm_studio() -> GrammarBackend:
    from .lm_studio import LMStudioBackend
    return LMStudioBackend()


# ============================================================================
# BACKEND REGISTRY - Add new backends here
# ============================================================================
BACKEND_REGISTRY: Dict[str, BackendInfo] = {
    "apple_intelligence": BackendInfo(
        id="apple_intelligence",
        name="Apple Intelligence",
        description="On-device, macOS 26+",
        factory=_create_apple_intelligence,
    ),
    "ollama": BackendInfo(
        id="ollama",
        name="Ollama",
        description="Local LLM server",
        factory=_create_ollama,
    ),
    "lm_studio": BackendInfo(
        id="lm_studio",
        name="LM Studio",
        description="OpenAI-compatible local server",
        factory=_create_lm_studio,
    ),
}


def create_backend(backend_type: str) -> GrammarBackend:
    """
    Factory function to create a grammar backend instance.

    Args:
        backend_type: Backend ID from BACKEND_REGISTRY

    Returns:
        An instance of the requested backend.

    Raises:
        ValueError: If backend_type is not recognized.
    """
    if backend_type not in BACKEND_REGISTRY:
        available = ", ".join(BACKEND_REGISTRY.keys())
        raise ValueError(f"Unknown backend: {backend_type}. Available: {available}")

    return BACKEND_REGISTRY[backend_type].factory()


def get_backend_info(backend_type: str) -> Optional[BackendInfo]:
    """Get metadata for a backend type."""
    return BACKEND_REGISTRY.get(backend_type)


__all__ = ["GrammarBackend", "BackendInfo", "BACKEND_REGISTRY", "create_backend", "get_backend_info"]

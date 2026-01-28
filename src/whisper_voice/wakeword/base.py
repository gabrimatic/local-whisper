"""Abstract base class for wake word engines."""

from abc import ABC, abstractmethod
from typing import Optional
import numpy as np


class WakeWordEngine(ABC):
    """Abstract base class for wake word detection engines."""

    @abstractmethod
    def load_model(self, model_name: str) -> bool:
        """Load a wake word model.

        Args:
            model_name: Name of the model to load

        Returns:
            True if loaded successfully, False otherwise
        """
        pass

    @abstractmethod
    def predict(self, audio_chunk: np.ndarray) -> dict[str, float]:
        """Run prediction on audio chunk.

        Args:
            audio_chunk: Audio samples (16kHz, float32, mono)

        Returns:
            Dictionary mapping model names to activation probabilities
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset internal state (e.g., between activations)."""
        pass

    @abstractmethod
    def get_sample_rate(self) -> int:
        """Get expected sample rate."""
        pass

    @abstractmethod
    def get_frame_samples(self) -> int:
        """Get expected frame size in samples."""
        pass

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """Check if model is loaded and ready."""
        pass

    @abstractmethod
    def unload(self) -> None:
        """Unload model and free resources."""
        pass

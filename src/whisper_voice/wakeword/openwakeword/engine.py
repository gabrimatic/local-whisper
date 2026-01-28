"""OpenWakeWord engine implementation."""

import logging
from typing import Optional
import numpy as np

from ..base import WakeWordEngine

logger = logging.getLogger(__name__)

# Check if openwakeword is available
try:
    import openwakeword
    from openwakeword.model import Model
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    OPENWAKEWORD_AVAILABLE = False
    Model = None


class OpenWakeWordEngine(WakeWordEngine):
    """Wake word engine using OpenWakeWord library."""

    # OpenWakeWord constants
    SAMPLE_RATE = 16000
    FRAME_MS = 80
    FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)  # 1280 samples

    def __init__(self):
        self._model: Optional["Model"] = None
        self._model_name: Optional[str] = None

        if not OPENWAKEWORD_AVAILABLE:
            logger.warning(
                "openwakeword not installed. Wake word detection disabled. "
                "Install with: pip install openwakeword"
            )

    def load_model(self, model_name: str) -> bool:
        """Load an OpenWakeWord model.

        Args:
            model_name: Pre-trained model name (e.g., "hey_jarvis", "alexa")

        Returns:
            True if loaded successfully
        """
        if not OPENWAKEWORD_AVAILABLE:
            return False

        try:
            # Unload existing model first
            if self._model is not None:
                self.unload()

            # Load the model
            # OpenWakeWord downloads pre-trained models automatically
            self._model = Model(wakeword_models=[model_name])
            self._model_name = model_name
            logger.info(f"Loaded wake word model: {model_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to load wake word model '{model_name}': {e}")
            self._model = None
            self._model_name = None
            return False

    def predict(self, audio_chunk: np.ndarray) -> dict[str, float]:
        """Run prediction on audio chunk.

        Args:
            audio_chunk: Audio samples (16kHz, float32, mono)

        Returns:
            Dictionary mapping model names to activation probabilities
        """
        if self._model is None:
            return {}

        # OpenWakeWord expects int16, but we have float32
        # Convert float32 [-1.0, 1.0] to int16 [-32768, 32767]
        if audio_chunk.dtype == np.float32:
            audio_int16 = np.clip(audio_chunk * 32767, -32768, 32767).astype(np.int16)
        else:
            audio_int16 = audio_chunk.astype(np.int16)

        # Run prediction
        prediction = self._model.predict(audio_int16)

        return prediction

    def reset(self) -> None:
        """Reset internal state."""
        if self._model is not None:
            self._model.reset()

    def get_sample_rate(self) -> int:
        """Get expected sample rate (16kHz)."""
        return self.SAMPLE_RATE

    def get_frame_samples(self) -> int:
        """Get expected frame size in samples."""
        return self.FRAME_SAMPLES

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None

    def unload(self) -> None:
        """Unload model and free resources."""
        if self._model is not None:
            logger.info(f"Unloading wake word model: {self._model_name}")
            self._model = None
            self._model_name = None

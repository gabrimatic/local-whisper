"""Wake word detector with audio streaming and coordination."""

import logging
import threading
import time
from collections import deque
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Check if sounddevice is available
try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False


class WakeWordDetector:
    """Streaming wake word detector with audio buffering.

    Manages a continuous audio stream for wake word detection,
    separate from the main recording stream.
    """

    def __init__(
        self,
        engine,  # WakeWordEngine instance
        *,
        threshold: float = 0.8,
        sensitivity: float = 0.5,
        cooldown: float = 2.0,
        buffer_seconds: float = 3.0,
        on_wake: Optional[Callable[[str], None]] = None,
    ):
        """Initialize wake word detector.

        Args:
            engine: WakeWordEngine instance (must be loaded)
            threshold: Activation probability threshold
            sensitivity: Detection sensitivity (0.0-1.0)
            cooldown: Seconds between activations
            buffer_seconds: Circular buffer size in seconds
            on_wake: Callback when wake word detected, receives model name
        """
        self._engine = engine
        self._threshold = threshold
        self._sensitivity = sensitivity
        self._cooldown = cooldown
        self._buffer_seconds = buffer_seconds
        self._on_wake = on_wake

        # Audio parameters
        self._sample_rate = engine.get_sample_rate()
        self._frame_samples = engine.get_frame_samples()

        # Circular buffer for audio
        buffer_size = int(self._sample_rate * buffer_seconds)
        self._buffer: deque = deque(maxlen=buffer_size)
        self._buffer_lock = threading.Lock()

        # Streaming state
        self._stream: Optional["sd.InputStream"] = None
        self._listening = threading.Event()
        self._stream_lock = threading.Lock()

        # Cooldown tracking
        self._last_activation: float = 0.0

        # Prediction thread
        self._predict_thread: Optional[threading.Thread] = None
        self._stop_predict = threading.Event()

    def start(self) -> bool:
        """Start listening for wake word.

        Returns:
            True if started successfully
        """
        if not SOUNDDEVICE_AVAILABLE:
            logger.error("sounddevice not available for wake word detection")
            return False

        if not self._engine.is_loaded:
            logger.error("Wake word engine not loaded")
            return False

        with self._stream_lock:
            if self._listening.is_set():
                logger.warning("Already listening for wake word")
                return True

            try:
                # Create audio stream
                self._stream = sd.InputStream(
                    samplerate=self._sample_rate,
                    channels=1,
                    dtype=np.float32,
                    blocksize=self._frame_samples,
                    callback=self._audio_callback,
                )
                self._stream.start()

                # Start prediction thread
                self._stop_predict.clear()
                self._predict_thread = threading.Thread(
                    target=self._prediction_loop,
                    daemon=True,
                    name="WakeWordPredictor",
                )
                self._predict_thread.start()

                self._listening.set()
                logger.info("Started wake word detection")
                return True

            except Exception as e:
                logger.error(f"Failed to start wake word detection: {e}")
                self._cleanup_stream()
                return False

    def stop(self) -> None:
        """Stop listening for wake word."""
        with self._stream_lock:
            if not self._listening.is_set():
                return

            self._listening.clear()
            self._stop_predict.set()

            # Wait for prediction thread
            if self._predict_thread is not None:
                self._predict_thread.join(timeout=1.0)
                self._predict_thread = None

            self._cleanup_stream()
            self._engine.reset()
            logger.info("Stopped wake word detection")

    def pause(self) -> None:
        """Pause listening (e.g., during recording).

        Unlike stop(), this doesn't reset the engine state.
        """
        with self._stream_lock:
            if self._stream is not None and self._stream.active:
                self._stream.stop()
                logger.debug("Paused wake word detection")

    def resume(self) -> None:
        """Resume listening after pause."""
        with self._stream_lock:
            if self._stream is not None and not self._stream.active:
                # Clear buffer to avoid processing old audio
                with self._buffer_lock:
                    self._buffer.clear()
                self._engine.reset()
                self._stream.start()
                logger.debug("Resumed wake word detection")

    @property
    def is_listening(self) -> bool:
        """Check if currently listening."""
        return self._listening.is_set()

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status,
    ) -> None:
        """Audio stream callback - adds samples to buffer."""
        if status:
            logger.warning(f"Wake audio status: {status}")

        # Add samples to circular buffer
        with self._buffer_lock:
            self._buffer.extend(indata[:, 0])

    def _prediction_loop(self) -> None:
        """Background thread for wake word prediction."""
        frame_duration = self._frame_samples / self._sample_rate

        while not self._stop_predict.is_set():
            if not self._listening.is_set():
                time.sleep(0.01)
                continue

            # Get a frame from the buffer
            with self._buffer_lock:
                if len(self._buffer) < self._frame_samples:
                    time.sleep(frame_duration / 2)
                    continue

                # Extract frame
                frame = np.array(
                    [self._buffer.popleft() for _ in range(self._frame_samples)],
                    dtype=np.float32,
                )

            # Run prediction
            try:
                predictions = self._engine.predict(frame)
            except Exception as e:
                logger.error(f"Wake word prediction error: {e}")
                continue

            # Check for activation
            self._check_activation(predictions)

    def _check_activation(self, predictions: dict[str, float]) -> None:
        """Check predictions for wake word activation."""
        # Adjust threshold based on sensitivity
        # Higher sensitivity = lower effective threshold
        effective_threshold = self._threshold * (1.0 - self._sensitivity * 0.5)

        for model_name, probability in predictions.items():
            if probability >= effective_threshold:
                # Check cooldown
                now = time.time()
                if now - self._last_activation < self._cooldown:
                    logger.debug(
                        f"Wake word '{model_name}' detected but in cooldown"
                    )
                    continue

                logger.info(
                    f"Wake word '{model_name}' activated "
                    f"(prob={probability:.2f}, threshold={effective_threshold:.2f})"
                )
                self._last_activation = now

                # Trigger callback
                if self._on_wake is not None:
                    try:
                        self._on_wake(model_name)
                    except Exception as e:
                        logger.error(f"Wake callback error: {e}")

    def _cleanup_stream(self) -> None:
        """Clean up audio stream resources."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.debug(f"Stream cleanup error: {e}")
            self._stream = None

        with self._buffer_lock:
            self._buffer.clear()

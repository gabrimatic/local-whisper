# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Abstract base class for TTS providers."""

import threading
from abc import ABC, abstractmethod
from typing import Callable, Optional


class TTSProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def start(self) -> bool:
        """Initialize the provider. Returns True if ready."""
        ...

    @abstractmethod
    def running(self) -> bool:
        """Returns True if the provider is available."""
        ...

    @abstractmethod
    def speak(self, text: str, stop_event: threading.Event,
              speaker: str = "af_sky",
              on_playback_start: Optional[Callable] = None) -> None:
        """
        Synthesize and play text. Blocks until done or stop_event is set.

        on_playback_start is called (once) right before the first audio chunk
        starts playing, so callers can update the UI from "Generating..." to
        "Speaking..." at the correct moment.
        """
        ...

    @abstractmethod
    def refresh(self, model_id: str) -> None:
        """Reload model if the model_id changed."""
        ...

    def ensure_loaded(self, model_id: str) -> bool:
        """Eagerly load weights so the first speak() is instant.

        Default is a no-op — providers that lazy-load override this so the
        Settings panel can surface a real progress bar when the user flips
        TTS on instead of stalling the first ⌥T press.
        """
        return True

    @abstractmethod
    def close(self) -> None:
        """Release resources."""
        ...

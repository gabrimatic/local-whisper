# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Base transcription engine interface for Local Whisper.

All transcription engines must inherit from TranscriptionEngine
and implement the required methods.
"""

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Optional, Protocol, Tuple, runtime_checkable


class EngineCapability(str, Enum):
    """Optional features an engine may explicitly implement."""

    CONTEXTUAL_PROMPTING = "contextual_prompting"


class TranscriptionEngine(ABC):
    """
    Abstract base class for transcription engines.

    Defines the interface that all transcription engines must implement.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the engine."""
        pass

    @abstractmethod
    def start(self) -> bool:
        """
        Initialize and verify engine availability.

        Returns True if engine is ready, False otherwise.
        """
        pass

    @abstractmethod
    def running(self) -> bool:
        """Check if the engine is ready to accept transcription requests."""
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def close(self) -> None:
        """Release all resources."""
        pass

    @property
    def supports_long_audio(self) -> bool:
        """Whether this engine handles audio >28s natively without chunking."""
        return False


@runtime_checkable
class ContextualPromptingEngine(Protocol):
    """Engine contract for model-native context or hotword prompting."""

    def transcribe_with_context(
        self,
        path: Path,
        context: Optional[str],
    ) -> Tuple[Optional[str], Optional[str]]:
        """Transcribe with a locally constructed contextual prompt."""
        ...

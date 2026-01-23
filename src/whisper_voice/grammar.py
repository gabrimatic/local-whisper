"""
Proofreading module for Local Whisper.

This module provides a unified interface to proofreading backends.
The backend is selected based on the [grammar] configuration.

Supported backends:
- apple_intelligence: Apple's on-device Foundation Models (macOS 26+)
- ollama: Local Ollama server with configurable LLM models
- lm_studio: LM Studio with OpenAI-compatible API

Usage:
    from whisper_voice.grammar import Grammar

    grammar = Grammar()
    if grammar.start():
        proofread, error = grammar.fix("some text")
    grammar.close()
"""

from typing import Tuple, Optional

from .backends import create_backend, GrammarBackend
from .config import get_config
from .utils import log


class Grammar:
    """
    Unified proofreading interface.

    Wraps the configured backend and provides a consistent API.
    """

    def __init__(self):
        config = get_config()
        try:
            self._backend: GrammarBackend = create_backend(config.grammar.backend)
            log(f"Grammar backend: {self._backend.name}", "INFO")
        except ValueError as e:
            log(f"Failed to create proofreading backend '{config.grammar.backend}': {e}", "ERR")
            raise

    def close(self) -> None:
        """Clean up backend resources."""
        self._backend.close()

    def running(self) -> bool:
        """Check if the proofreading backend is available."""
        return self._backend.running()

    def start(self) -> bool:
        """Initialize and verify backend availability."""
        return self._backend.start()

    def fix(self, text: str) -> Tuple[str, Optional[str]]:
        """
        Proofread the given text.

        Args:
            text: The text to proofread.

        Returns:
            Tuple of (proofread_text, error_message).
            On success, error_message is None.
            On error, returns original text with error description.
        """
        return self._backend.fix(text)

    @property
    def name(self) -> str:
        """Get the name of the current backend."""
        return self._backend.name

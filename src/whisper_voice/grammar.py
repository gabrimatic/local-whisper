# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Grammar correction module for Local Whisper.

This module provides a unified interface to grammar correction backends.
The backend is selected based on the [grammar] configuration.

Supported backends:
- apple_intelligence: Apple's on-device Foundation Models (macOS 15+)
- ollama: Local Ollama server with configurable LLM models

Usage:
    from whisper_voice.grammar import Grammar

    grammar = Grammar()
    if grammar.start():
        corrected, error = grammar.fix("some text")
    grammar.close()
"""

from typing import Optional, Tuple

from .backends import GrammarBackend, create_backend
from .config import get_config
from .utils import log


class Grammar:
    """
    Unified grammar correction interface.

    Wraps the configured backend and provides a consistent API.
    """

    def __init__(self):
        config = get_config()
        try:
            self._backend: GrammarBackend = create_backend(config.grammar.backend)
            log(f"Grammar backend: {self._backend.name}", "INFO")
        except ValueError as e:
            log(f"Failed to create grammar backend '{config.grammar.backend}': {e}", "ERR")
            raise

    def close(self) -> None:
        """Clean up backend resources."""
        self._backend.close()

    def running(self) -> bool:
        """Check if the grammar backend is available."""
        return self._backend.running()

    def start(self) -> bool:
        """Initialize and verify backend availability."""
        return self._backend.start()

    def fix(self, text: str) -> Tuple[str, Optional[str]]:
        """
        Fix grammar in the given text.

        Args:
            text: The text to correct.

        Returns:
            Tuple of (corrected_text, error_message).
            On success, error_message is None.
            On error, returns original text with error description.
        """
        return self._backend.fix(text)

    def fix_with_mode(self, text: str, mode_id: str) -> Tuple[str, Optional[str]]:
        """
        Fix text using a specific transformation mode.

        Args:
            text: The text to transform.
            mode_id: The mode identifier (e.g., "proofread", "rewrite").

        Returns:
            Tuple of (transformed_text, error_message).
            On success, error_message is None.
            On error, returns original text with error description.
        """
        return self._backend.fix_with_mode(text, mode_id)

    @property
    def name(self) -> str:
        """Get the name of the current backend."""
        return self._backend.name

    @property
    def backend(self) -> GrammarBackend:
        """Get the underlying backend."""
        return self._backend

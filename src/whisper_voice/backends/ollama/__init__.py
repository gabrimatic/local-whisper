# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Ollama backend for grammar correction.

Uses local Ollama server with configurable LLM models.
"""

from .backend import OllamaBackend

__all__ = ["OllamaBackend"]

"""
Ollama backend for grammar correction.

Uses local Ollama server with configurable LLM models.
"""

from .backend import OllamaBackend

__all__ = ["OllamaBackend"]

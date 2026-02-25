# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Local Whisper - Local voice transcription with grammar correction for macOS

Double-tap Right Option -> speak -> tap to stop -> polished text copied to clipboard.
All processing runs locally. No internet. No cloud. No tracking.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("local-whisper")
except PackageNotFoundError:
    __version__ = "0.0.0"

from .cli import cli_main as main

__all__ = ["main", "__version__"]

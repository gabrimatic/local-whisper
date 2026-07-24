# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Resolve the native menu app bundled with the active Local Whisper install."""

import sys
from pathlib import Path


def home_ui_binary() -> Path:
    """Return the per-user UI binary used by source installs."""
    return Path.home() / ".whisper" / "LocalWhisperUI.app" / "Contents" / "MacOS" / "LocalWhisperUI"


def home_speech_binary() -> Path:
    """Return the per-user Apple Speech helper."""
    return Path.home() / ".whisper" / "LocalWhisperUI.app" / "Contents" / "MacOS" / "LocalWhisperSpeech"


def homebrew_ui_binary() -> Path:
    """Return the UI binary bundled with the active Homebrew Cellar version."""
    return Path(sys.prefix).parent / "LocalWhisperUI.app" / "Contents" / "MacOS" / "LocalWhisperUI"


def preferred_ui_binary() -> Path:
    """Prefer the current Cellar UI and fall back to the per-user source bundle."""
    cellar_binary = homebrew_ui_binary()
    if cellar_binary.exists():
        return cellar_binary
    return home_ui_binary()

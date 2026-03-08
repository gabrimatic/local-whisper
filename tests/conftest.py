# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Shared pytest configuration and fixtures.
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Stubs for macOS framework modules that aren't available in test environments
FRAMEWORK_STUBS = {
    "sounddevice": None,
    "AppKit": None,
    "Foundation": None,
    "Quartz": None,
}

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def flush_whisper_modules():
    """Remove all cached whisper_voice modules so imports resolve fresh."""
    for mod in list(sys.modules.keys()):
        if "whisper_voice" in mod:
            del sys.modules[mod]


def import_with_stubs(module_path: str, extra_stubs: dict | None = None):
    """Import a whisper_voice module with framework stubs applied.

    Returns the imported module object.
    """
    flush_whisper_modules()
    stubs = {**FRAMEWORK_STUBS, **(extra_stubs or {})}
    with patch.dict("sys.modules", stubs):
        import importlib
        mod = importlib.import_module(module_path)
    return mod

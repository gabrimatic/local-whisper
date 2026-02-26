# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Apple Intelligence backend for grammar correction.

Uses Apple's Foundation Models Python SDK for on-device text generation.
Requires macOS 26+ with Apple Intelligence enabled on Apple Silicon.
"""

from .backend import AppleIntelligenceBackend

__all__ = ["AppleIntelligenceBackend"]

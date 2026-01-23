"""
Apple Intelligence backend for proofreading.

Uses Apple's on-device Foundation Models via a Swift CLI helper.
Requires macOS 26+ with Apple Intelligence enabled.
"""

from .backend import AppleIntelligenceBackend

__all__ = ["AppleIntelligenceBackend"]

"""
Apple Intelligence backend for grammar correction.

Uses Apple's on-device Foundation Models via a Swift CLI helper.
Requires macOS 15+ with Apple Intelligence enabled.
"""

from .backend import AppleIntelligenceBackend

__all__ = ["AppleIntelligenceBackend"]

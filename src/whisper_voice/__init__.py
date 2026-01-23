"""
Local Whisper - Local voice transcription with proofreading for macOS

Double-tap Right Option (⌥) -> speak -> tap to stop -> proofread text copied to clipboard.
All processing runs locally. No internet. No cloud. No tracking.
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("local-whisper")
except PackageNotFoundError:
    __version__ = "0.0.0"  # Not installed

from .app import main

__all__ = ["main", "__version__"]

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""ANSI color codes and shared path constants for the CLI."""

from pathlib import Path

from .._install import INSTALL_BREW, INSTALL_PIP, INSTALL_SOURCE, get_install_method

# Color constants
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"

LOCK_FILE = str(Path.home() / ".whisper" / "service.lock")
LAUNCHAGENT_LABEL = "com.local-whisper"
LAUNCHAGENT_PLIST = Path.home() / "Library" / "LaunchAgents" / "com.local-whisper.plist"
LOG_FILE = Path.home() / ".whisper" / "service.log"
MODEL_DIR = Path.home() / ".whisper" / "models"

CMD_SOCKET_PATH = str(Path.home() / ".whisper" / "cmd.sock")

__all__ = [
    "C_RESET", "C_BOLD", "C_DIM", "C_RED", "C_GREEN", "C_YELLOW", "C_CYAN",
    "LOCK_FILE", "LAUNCHAGENT_LABEL", "LAUNCHAGENT_PLIST", "LOG_FILE",
    "MODEL_DIR", "CMD_SOCKET_PATH",
    "INSTALL_SOURCE", "INSTALL_BREW", "INSTALL_PIP", "get_install_method",
]

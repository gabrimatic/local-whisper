# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""ANSI color codes and shared path constants for the CLI."""

import sys
from functools import lru_cache
from pathlib import Path

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


# Install method detection

INSTALL_SOURCE = "source"   # git clone + venv (development)
INSTALL_BREW = "brew"       # Homebrew formula
INSTALL_PIP = "pip"         # standalone pip install


@lru_cache(maxsize=1)
def get_install_method() -> str:
    """Detect how local-whisper was installed.

    Returns INSTALL_SOURCE, INSTALL_BREW, or INSTALL_PIP.

    Homebrew formula installs have sys.prefix under /opt/homebrew/Cellar/ (the
    libexec virtualenv lives inside the Cellar). A dev venv created from
    Homebrew Python has sys.prefix pointing at the local .venv but the resolved
    executable symlinks through Cellar, so only sys.prefix is a reliable signal.
    """
    if "/Cellar/" in sys.prefix:
        return INSTALL_BREW

    # Source (dev) install: project root is a git repo
    try:
        project_root = Path(__file__).resolve().parents[3]
        if (project_root / ".git").is_dir():
            return INSTALL_SOURCE
    except (IndexError, OSError):
        pass

    return INSTALL_PIP

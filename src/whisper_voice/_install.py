# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Install-method detection (brew vs source vs pip)."""

import sys
from functools import lru_cache
from pathlib import Path

INSTALL_SOURCE = "source"
INSTALL_BREW = "brew"
INSTALL_PIP = "pip"


@lru_cache(maxsize=1)
def get_install_method() -> str:
    """Return INSTALL_SOURCE, INSTALL_BREW, or INSTALL_PIP."""
    if "/Cellar/" in sys.prefix:
        return INSTALL_BREW
    try:
        project_root = Path(__file__).resolve().parents[2]
        if (project_root / ".git").is_dir():
            return INSTALL_SOURCE
    except (IndexError, OSError):
        pass
    return INSTALL_PIP

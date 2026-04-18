# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Utility functions for Local Whisper.

Includes logging, sound playback, and helper functions.
"""

import re
import subprocess
import threading
from datetime import datetime

from .config import get_config

# Console colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"
C_MAGENTA = "\033[95m"

# Log level styles
LOG_STYLES = {
    "INFO": (C_DIM, "›"),
    "OK": (C_GREEN, "✓"),
    "WARN": (C_YELLOW, "⚠"),
    "ERR": (C_RED, "✗"),
    "REC": (C_RED + C_BOLD, "●"),
    "AI": (C_MAGENTA, "✦"),
    "APP": (C_CYAN, "◆"),
}

# Duration update interval (seconds). Used by the recording duration ticker.
DURATION_UPDATE_INTERVAL = 0.1

# Timeout values (seconds)
CLIPBOARD_TIMEOUT = 5
SERVICE_CHECK_TIMEOUT = 2
TRANSCRIBE_CHECK_TIMEOUT = 3

# Display truncation
LOG_TRUNCATE = 60
PREVIEW_TRUNCATE = 70

# Known Whisper hallucination patterns
HALLUCINATION_PATTERNS = [
    "продолжение следует",  # Russian "to be continued"
    "to be continued",
    "thank you for watching",
    "thanks for watching",
    "subscribe",
    "like and subscribe",
    "see you next time",
    "music",
    "applause",
    "[music]",
    "[applause]",
]


def log(msg: str, level: str = "INFO"):
    """Print a timestamped, colored log message."""
    ts = datetime.now().strftime("%H:%M:%S")
    color, sym = LOG_STYLES.get(level, (C_DIM, "›"))
    print(f"  {C_DIM}{ts}{C_RESET}  {color}{sym}{C_RESET}  {msg}")


def play_sound(name: str):
    """Play a macOS system sound (Tink, Pop, Purr, etc.)."""
    config = get_config()
    if not config.ui.sounds_enabled:
        return
    try:
        subprocess.Popen(
            ['afplay', f'/System/Library/Sounds/{name}.aiff'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    except Exception:
        pass  # Silent failure


def strip_hallucination_lines(text: str) -> tuple[str, bool]:
    """Remove short, standalone hallucination lines while preserving real content."""
    if not text:
        return text, False
    lines = text.splitlines()
    kept = []
    removed = False
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            kept.append(line)
            continue
        lower = line_stripped.lower()
        drop = False
        for pattern in HALLUCINATION_PATTERNS:
            if pattern in lower:
                if len(lower) <= max(80, len(pattern) * 4):
                    drop = True
                    break
        if drop:
            removed = True
            continue
        kept.append(line)
    cleaned = "\n".join(kept).strip()
    for pattern in HALLUCINATION_PATTERNS:
        cleaned_next = re.sub(
            rf"(?:\s*[-]*\s*)?(?:\.{{3,}}|\.\s*)?\s*{re.escape(pattern)}(?:\.{{3,}}|\.\s*)?\s*$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
        if cleaned_next != cleaned:
            removed = True
            cleaned = cleaned_next
    return cleaned, removed


def is_hallucination(text: str) -> bool:
    """Check if text matches known Whisper hallucination patterns."""
    if not text:
        return False
    cleaned, removed = strip_hallucination_lines(text)
    if removed and not cleaned:
        return True
    lower = cleaned.lower().strip() if cleaned else ""
    if not lower:
        return True
    for pattern in HALLUCINATION_PATTERNS:
        if pattern in lower:
            words = re.findall(r"[a-z0-9']+|[а-я0-9']+", lower)
            if len(lower) <= max(80, len(pattern) * 4) and len(words) <= 6:
                return True
    return False


def check_microphone_permission() -> tuple[bool, str]:
    """Check and request macOS microphone permission via AVFoundation.

    Returns (authorized, message) where message explains the situation.
    """
    try:
        import AVFoundation

        status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(
            AVFoundation.AVMediaTypeAudio
        )

        # 3 = authorized
        if status == 3:
            return True, "Microphone access granted"

        # 1 = restricted, 2 = denied
        if status in (1, 2):
            return False, (
                "Microphone access denied. "
                "Go to System Settings > Privacy & Security > Microphone "
                "and enable Python, then restart."
            )

        # 0 = notDetermined - request access
        if status == 0:
            event = threading.Event()
            result = [False]

            def callback(granted):
                result[0] = granted
                event.set()

            AVFoundation.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                AVFoundation.AVMediaTypeAudio, callback
            )
            event.wait(timeout=30)

            if result[0]:
                return True, "Microphone access granted"
            else:
                return False, (
                    "Microphone access denied. "
                    "Go to System Settings > Privacy & Security > Microphone "
                    "and enable your terminal app, then restart."
                )

        return False, f"Unknown microphone authorization status: {status}"

    except ImportError:
        # AVFoundation not available - skip check, let it fail later if needed
        return True, "Could not check microphone permission (AVFoundation unavailable)"
    except Exception as e:
        # Don't block startup on permission check failures
        return True, f"Could not check microphone permission: {e}"


_notification_sender = None


def register_notification_sender(fn):
    """Register a callback that delivers notifications via the Swift app."""
    global _notification_sender
    _notification_sender = fn


def send_notification(title: str, message: str):
    """Send a macOS notification if notifications are enabled."""
    config = get_config()
    if not config.ui.notifications_enabled:
        return
    if _notification_sender is None:
        return
    try:
        _notification_sender(title, message)
    except Exception as e:
        log(f"Notification delivery failed: {type(e).__name__}: {e}", "WARN")


def truncate(text: str, length: int = LOG_TRUNCATE) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) > length:
        return text[:length] + "..."
    return text


def time_ago(dt: datetime) -> str:
    """Return a human-readable relative time string for a datetime.

    Examples: "Just now", "2m ago", "1h ago", "Yesterday", "3d ago", "Feb 20".
    """
    now = datetime.now()
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "Just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days == 1:
        return "Yesterday"
    if days < 30:
        return f"{days}d ago"
    return dt.strftime("%b %-d")


def check_accessibility_trusted() -> bool:
    """Return True if this process has Accessibility permission. False on error."""
    try:
        import ctypes
        lib = ctypes.CDLL(
            '/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices'
        )
        func = lib.AXIsProcessTrustedWithOptions
        func.restype = ctypes.c_bool
        func.argtypes = [ctypes.c_void_p]
        return bool(func(None))
    except Exception as e:
        log(f"Accessibility check failed: {e}", "WARN")
        return False


_accessibility_prompt_shown = False


def request_accessibility_permission() -> bool:
    """
    Trigger the macOS Accessibility permission prompt.
    Opens System Settings → Accessibility with this process highlighted.
    Returns True if already trusted, False if prompt was shown.
    Only shows the prompt once per process lifetime.
    """
    global _accessibility_prompt_shown
    if _accessibility_prompt_shown:
        return False
    _accessibility_prompt_shown = True
    try:
        import ctypes
        cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        ax = ctypes.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')

        ax.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
        ax.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFDictionaryCreate.restype = ctypes.c_void_p
        cf.CFDictionaryCreate.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
        ]

        key = cf.CFStringCreateWithCString(None, b'AXTrustedCheckOptionPrompt', 0x08000100)
        true_val = ctypes.c_void_p.in_dll(cf, 'kCFBooleanTrue').value
        key_cbs = ctypes.addressof(ctypes.c_byte.in_dll(cf, 'kCFTypeDictionaryKeyCallBacks'))
        val_cbs = ctypes.addressof(ctypes.c_byte.in_dll(cf, 'kCFTypeDictionaryValueCallBacks'))

        keys = (ctypes.c_void_p * 1)(key)
        vals = (ctypes.c_void_p * 1)(true_val)
        opts = cf.CFDictionaryCreate(None, keys, vals, 1, key_cbs, val_cbs)
        return bool(ax.AXIsProcessTrustedWithOptions(opts))
    except Exception:
        subprocess.Popen(['open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'])
        return False

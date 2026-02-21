"""
Utility functions for Local Whisper.

Includes logging, sound playback, and helper functions.
"""

import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path

import numpy as np

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

# Menu bar icons + status glyphs
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

def _validate_asset(path: str) -> str:
    """Validate asset file exists, return path or raise error."""
    if not Path(path).exists():
        raise FileNotFoundError(f"Missing asset: {path}")
    return path

ICON_IMAGE = _validate_asset(str(ASSETS_DIR / "icon_waveform.png"))
ICON_FRAMES = [
    _validate_asset(str(ASSETS_DIR / "icon_waveform_1.png")),
    _validate_asset(str(ASSETS_DIR / "icon_waveform_2.png")),
    _validate_asset(str(ASSETS_DIR / "icon_waveform_3.png")),
    _validate_asset(str(ASSETS_DIR / "icon_waveform_4.png")),
]
ICON_PROCESS_FRAMES = [
    _validate_asset(str(ASSETS_DIR / "icon_waveform_p1.png")),
    _validate_asset(str(ASSETS_DIR / "icon_waveform_p2.png")),
    _validate_asset(str(ASSETS_DIR / "icon_waveform_p3.png")),
    _validate_asset(str(ASSETS_DIR / "icon_waveform_p4.png")),
]
ICON_IDLE = ""
ICON_RECORDING = ""
ICON_PROCESSING = "···"
ICON_SUCCESS = "✓"
ICON_ERROR = "✗"

OVERLAY_WAVE_FRAMES = [
    _validate_asset(str(ASSETS_DIR / "overlay_wave_1.png")),
    _validate_asset(str(ASSETS_DIR / "overlay_wave_2.png")),
    _validate_asset(str(ASSETS_DIR / "overlay_wave_3.png")),
    _validate_asset(str(ASSETS_DIR / "overlay_wave_4.png")),
]

# Timing for icon resets (seconds)
ICON_RESET_SUCCESS = 1.0
ICON_RESET_ERROR = 1.0

# Animation intervals (seconds)
ANIM_INTERVAL_RECORDING = 0.1
ANIM_INTERVAL_PROCESSING = 0.2
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


def is_silent(audio: np.ndarray) -> bool:
    """Check if audio is mostly silence based on RMS level."""
    # Only reject truly empty audio - let WhisperKit handle silence detection
    if len(audio) == 0:
        return True
    return False


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
        import objc

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
                "and enable your terminal app, then restart."
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


def hide_dock_icon():
    """Hide the dock icon (menu bar app only)."""
    try:
        from AppKit import NSApp, NSApplicationActivationPolicyAccessory
        if NSApp:
            NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass


def truncate(text: str, length: int = LOG_TRUNCATE) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) > length:
        return text[:length] + "..."
    return text


def check_accessibility_trusted() -> bool:
    """Return True if this process has Accessibility permission."""
    try:
        import ctypes
        lib = ctypes.CDLL(
            '/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices'
        )
        func = lib.AXIsProcessTrustedWithOptions
        func.restype = ctypes.c_bool
        func.argtypes = [ctypes.c_void_p]
        return bool(func(None))
    except Exception:
        return True  # assume trusted if we can't check


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
        from Foundation import NSDictionary
        import ctypes
        lib = ctypes.CDLL(
            '/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices'
        )
        func = lib.AXIsProcessTrustedWithOptions
        func.restype = ctypes.c_bool
        func.argtypes = [ctypes.c_void_p]
        opts = NSDictionary.dictionaryWithObject_forKey_(True, 'AXTrustedCheckOptionPrompt')
        return bool(func(opts))
    except Exception:
        return False

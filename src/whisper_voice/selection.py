# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Shared selected-text reader for text transforms and TTS.

Strategy:
  1. Accessibility API — no clipboard side effects. Works in most native
     apps, fails in Chrome/Firefox/Electron.
  2. Cmd+C with a UUID marker — the marker distinguishes "no selection"
     from "user selected the same text that was already on the clipboard",
     and guarantees stale clipboard content is never mistaken for a fresh
     selection.

The user's clipboard is captured as a full pasteboard snapshot (all types,
so images and files survive) and restored on every path that doesn't
intentionally leave new content behind.
"""

import subprocess
import time
import uuid
from typing import List, Optional, Tuple

from ApplicationServices import (
    AXUIElementCopyAttributeValue,
    AXUIElementCreateSystemWide,
    kAXFocusedUIElementAttribute,
    kAXSelectedTextAttribute,
)

from .utils import CLIPBOARD_TIMEOUT, log

CLIPBOARD_DELAY = 0.15
# Delay before synthetic keystrokes so a still-held shortcut modifier can't
# merge into the Cmd+C / Cmd+V we send.
MODIFIER_RELEASE_DELAY = 0.3


class ClipboardSnapshot:
    """Captured pasteboard state that can be restored later.

    Prefers a full NSPasteboard snapshot (all types — images, files, rich
    text). Falls back to plain text via pbpaste when AppKit is unavailable.
    """

    def __init__(self, items: Optional[List[Tuple[str, bytes]]], text: Optional[str]):
        self._items = items
        self._text = text

    @classmethod
    def capture(cls) -> "ClipboardSnapshot":
        items: Optional[List[Tuple[str, bytes]]] = None
        try:
            from AppKit import NSPasteboard
            pb = NSPasteboard.generalPasteboard()
            captured: List[Tuple[str, bytes]] = []
            for pb_type in (pb.types() or []):
                data = pb.dataForType_(pb_type)
                if data is not None:
                    captured.append((str(pb_type), bytes(data)))
            items = captured
        except Exception as e:
            log(f"Pasteboard snapshot failed ({type(e).__name__}: {e}); text-only fallback", "INFO")
        text = read_clipboard_text()
        return cls(items, text)

    @property
    def text(self) -> Optional[str]:
        return self._text

    def restore(self) -> bool:
        """Put the captured content back on the pasteboard."""
        if self._items:
            try:
                from AppKit import NSPasteboard
                from Foundation import NSData
                pb = NSPasteboard.generalPasteboard()
                pb.clearContents()
                for pb_type, raw in self._items:
                    data = NSData.dataWithBytes_length_(raw, len(raw))
                    pb.setData_forType_(data, pb_type)
                return True
            except Exception as e:
                log(f"Pasteboard restore failed: {type(e).__name__}: {e}", "WARN")
        if self._text is not None:
            return write_clipboard_text(self._text)
        # Nothing was captured (empty/non-readable clipboard): leave the
        # pasteboard alone rather than overwrite it with emptiness.
        return False


def read_clipboard_text() -> Optional[str]:
    """Read current clipboard as text. None when unreadable."""
    try:
        result = subprocess.run(
            ['pbpaste'], capture_output=True, text=True, timeout=CLIPBOARD_TIMEOUT
        )
        if result.returncode != 0:
            log(f"pbpaste returned non-zero: {result.returncode}", "WARN")
            return None
        return result.stdout
    except subprocess.TimeoutExpired:
        log("Timeout reading clipboard", "WARN")
        return None
    except Exception as e:
        log(f"Error reading clipboard: {type(e).__name__}: {e}", "WARN")
        return None


def write_clipboard_text(text: str) -> bool:
    """Copy text to the clipboard. Returns True on success."""
    try:
        subprocess.run(
            ['pbcopy'], input=text.encode('utf-8'), check=True, timeout=CLIPBOARD_TIMEOUT
        )
        return True
    except Exception as e:
        log(f"Error writing clipboard: {type(e).__name__}: {e}", "ERR")
        return False


def get_selected_text_accessibility() -> Optional[str]:
    """Read the focused element's selected text via the Accessibility API."""
    try:
        system = AXUIElementCreateSystemWide()
        err, focused = AXUIElementCopyAttributeValue(
            system, kAXFocusedUIElementAttribute, None
        )
        if err != 0 or focused is None:
            log(f"Accessibility: could not get focused element (err={err})", "INFO")
            return None
        err, selected_text = AXUIElementCopyAttributeValue(
            focused, kAXSelectedTextAttribute, None
        )
        if err != 0 or selected_text is None:
            log(f"Accessibility: could not get selected text (err={err})", "INFO")
            return None
        # Return the selection VERBATIM (strip only decides emptiness).
        # Paste-in-place replaces the entire selected span, so a stripped
        # read would delete the selection's own boundary whitespace — e.g.
        # a double-clicked word's trailing space or a triple-clicked
        # paragraph's newline — from the user's document.
        text = str(selected_text)
        if text.strip():
            log(f"Accessibility: got {len(text)} chars", "INFO")
            return text
        return None
    except Exception as e:
        log(f"Accessibility API error: {type(e).__name__}: {e}", "INFO")
        return None


def get_selected_text_via_copy(snapshot: ClipboardSnapshot) -> Optional[str]:
    """Cmd+C fallback with a UUID marker.

    1. Write a unique marker to the clipboard (verified — a failed write
       would make stale clipboard content look like a fresh selection).
    2. Send Cmd+C.
    3. Clipboard still equals the marker -> no selection; restore snapshot.
    4. Anything else -> that's the selection.
    """
    marker = f"__clipboard_marker_{uuid.uuid4()}__"
    try:
        subprocess.run(
            ['pbcopy'], input=marker.encode(), timeout=CLIPBOARD_TIMEOUT, check=True
        )
        time.sleep(MODIFIER_RELEASE_DELAY)
        result = subprocess.run([
            'osascript', '-e',
            'tell application "System Events" to keystroke "c" using command down'
        ], capture_output=True, timeout=CLIPBOARD_TIMEOUT)
        if result.returncode != 0:
            stderr = result.stderr.decode('utf-8', errors='replace')[:100]
            log(f"Cmd+C failed (code={result.returncode}): {stderr}", "WARN")
            snapshot.restore()
            return None
        time.sleep(CLIPBOARD_DELAY)
        new_clipboard = read_clipboard_text()
        if new_clipboard == marker:
            log("Clipboard marker unchanged (no selection)", "INFO")
            snapshot.restore()
            return None
        if new_clipboard:
            log(f"Clipboard fallback: got {len(new_clipboard)} chars", "INFO")
            return new_clipboard
        log("Clipboard empty after Cmd+C (no selection)", "INFO")
        snapshot.restore()
        return None
    except subprocess.TimeoutExpired:
        log("Timeout getting selected text via clipboard", "WARN")
        snapshot.restore()
        return None
    except Exception as e:
        log(f"Error getting selection via clipboard: {type(e).__name__}: {e}", "WARN")
        snapshot.restore()
        return None


def get_selected_text(snapshot: ClipboardSnapshot) -> Optional[str]:
    """Read the current selection: Accessibility first, Cmd+C fallback."""
    text = get_selected_text_accessibility()
    if text:
        return text
    log("Accessibility API failed, falling back to Cmd+C", "INFO")
    return get_selected_text_via_copy(snapshot)

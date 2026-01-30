"""
Keyboard shortcut handler for text transformation modes.

Provides processing logic for text transformation shortcuts.
The actual key detection is handled by the main keyboard listener in app.py.
"""

import subprocess
import threading
import time
import uuid
from typing import Optional, Set, TYPE_CHECKING

from ApplicationServices import (
    AXUIElementCreateSystemWide,
    AXUIElementCopyAttributeValue,
    kAXFocusedUIElementAttribute,
    kAXSelectedTextAttribute,
)

from .backends.modes import MODE_REGISTRY, get_mode
from .config import get_config
from .overlay import get_overlay
from .utils import log, play_sound, OVERLAY_WAVE_FRAMES

if TYPE_CHECKING:
    from .grammar import Grammar


CLIPBOARD_TIMEOUT = 5
CLIPBOARD_DELAY = 0.15
MODIFIER_RELEASE_DELAY = 0.3  # Delay before Cmd+C to let user release modifier keys
STATUS_DISPLAY_DURATION = 1.5
ANIMATION_INTERVAL = 0.2  # Match voice processing animation interval

# Error messages for user display (keep short for overlay)
ERR_NO_TEXT = "No text selected"
ERR_EMPTY_RESULT = "Empty result"
ERR_COPY_FAILED = "Copy failed"
ERR_BACKEND_UNAVAILABLE = "Backend unavailable"
ERR_CLIPBOARD_READ = "Clipboard read failed"
ERR_SELECTION_FAILED = "Selection failed"


class ShortcutProcessor:
    """
    Process text transformation shortcuts.

    This class handles the actual text processing when a shortcut is triggered.
    Key detection is handled externally by the main keyboard listener.
    """

    def __init__(self, grammar: "Grammar"):
        self._grammar = grammar
        self._overlay = get_overlay()
        self._busy = False
        self._lock = threading.Lock()
        self._animating = False
        log("ShortcutProcessor initialized", "INFO")

    def is_busy(self) -> bool:
        """Check if currently processing."""
        with self._lock:
            return self._busy

    def _start_animation(self, mode_name: str):
        """Start processing animation in background thread."""
        self._animating = True
        # Set static status text once (no cycling dots)
        self._overlay.set_status_text(mode_name)

        def animate():
            frame_index = 0
            while self._animating:
                # Cycle through wave frames only (same as voice processing)
                frame = OVERLAY_WAVE_FRAMES[frame_index % len(OVERLAY_WAVE_FRAMES)]
                self._overlay.set_processing_frame(frame)
                frame_index += 1
                time.sleep(ANIMATION_INTERVAL)

        threading.Thread(target=animate, daemon=True).start()

    def _stop_animation(self):
        """Stop the processing animation."""
        self._animating = False

    def trigger(self, mode_id: str):
        """Trigger processing for a mode. Called from keyboard listener."""
        with self._lock:
            if self._busy:
                log(f"Shortcut ignored: processor busy (mode={mode_id})", "INFO")
                return
            self._busy = True

        log(f"Shortcut triggered: {mode_id}", "INFO")
        threading.Thread(
            target=self._process,
            args=(mode_id,),
            daemon=True
        ).start()

    def _process(self, mode_id: str):
        """Process the shortcut in background thread."""
        mode = get_mode(mode_id)
        if not mode:
            log(f"Unknown mode requested: {mode_id}", "ERR")
            with self._lock:
                self._busy = False
            return

        old_clipboard = None

        try:
            # Check if grammar backend is available before proceeding
            if not self._grammar.running():
                log(f"Grammar backend not available for shortcut: {mode_id}", "ERR")
                self._show_status(ERR_BACKEND_UNAVAILABLE, is_error=True)
                return

            self._overlay.show()
            self._overlay.set_status_text("Copying...")

            # Read current clipboard (for restoration on error)
            old_clipboard = self._read_clipboard()
            if old_clipboard is None:
                log("Could not read clipboard (may be empty or contain non-text)", "INFO")

            # Get selected text (pass old_clipboard for restoration if clipboard fallback fails)
            text = self._get_selected_text(old_clipboard)

            if not text:
                log("No text selected or selection unchanged", "WARN")
                self._restore_clipboard(old_clipboard)
                self._show_status(ERR_NO_TEXT, is_error=True)
                return

            log(f"Processing {len(text)} chars with mode: {mode.name}", "INFO")
            play_sound("Pop")

            # Start animation and call grammar backend
            self._start_animation(mode.name)
            try:
                result, error = self._grammar.fix_with_mode(text, mode_id)
            finally:
                self._stop_animation()

            if error:
                log(f"Backend error for {mode.name}: {error}", "ERR")
                self._restore_clipboard(old_clipboard)
                self._show_status(error[:40], is_error=True)
                return

            if not result or not result.strip():
                log(f"Empty result from backend for {mode.name}", "WARN")
                self._restore_clipboard(old_clipboard)
                self._show_status(ERR_EMPTY_RESULT, is_error=True)
                return

            # Copy result to clipboard
            if not self._copy_to_clipboard(result):
                log("Failed to copy result to clipboard", "ERR")
                self._restore_clipboard(old_clipboard)
                self._show_status(ERR_COPY_FAILED, is_error=True)
                return

            # Success
            char_diff = len(result) - len(text)
            diff_str = f"+{char_diff}" if char_diff >= 0 else str(char_diff)
            self._overlay.set_status_text(f"Done! ({diff_str} chars)")
            self._overlay.set_status("done")
            play_sound("Glass")
            log(f"{mode.name}: {len(text)} -> {len(result)} chars ({diff_str})", "OK")

            time.sleep(STATUS_DISPLAY_DURATION)
            self._overlay.hide()

        except subprocess.TimeoutExpired as e:
            log(f"Timeout during shortcut processing: {e}", "ERR")
            self._restore_clipboard(old_clipboard)
            self._show_status("Timeout", is_error=True)
        except subprocess.SubprocessError as e:
            log(f"Subprocess error during shortcut: {e}", "ERR")
            self._restore_clipboard(old_clipboard)
            self._show_status("System error", is_error=True)
        except Exception as e:
            log(f"Unexpected error during shortcut processing: {type(e).__name__}: {e}", "ERR")
            self._restore_clipboard(old_clipboard)
            self._show_status("Error", is_error=True)
        finally:
            with self._lock:
                self._busy = False

    def _read_clipboard(self) -> Optional[str]:
        """Read current clipboard content."""
        try:
            result = subprocess.run(
                ['pbpaste'],
                capture_output=True,
                text=True,
                timeout=CLIPBOARD_TIMEOUT
            )
            if result.returncode != 0:
                log(f"pbpaste returned non-zero: {result.returncode}", "WARN")
                return None
            return result.stdout
        except subprocess.TimeoutExpired:
            log("Timeout reading clipboard", "WARN")
            return None
        except subprocess.SubprocessError as e:
            log(f"Subprocess error reading clipboard: {e}", "WARN")
            return None
        except Exception as e:
            log(f"Unexpected error reading clipboard: {type(e).__name__}: {e}", "WARN")
            return None

    def _get_selected_text(self, old_clipboard: Optional[str]) -> Optional[str]:
        """
        Get currently selected text using hybrid approach.

        Primary: Accessibility API (no clipboard modification)
        Fallback: Cmd+C (for apps that don't support AX, like Chrome/Firefox)

        Args:
            old_clipboard: Original clipboard content to restore on failure
        """
        # Try Accessibility API first
        text = self._get_selected_text_accessibility()
        if text:
            return text

        # Fallback to clipboard-based approach
        log("Accessibility API failed, falling back to Cmd+C", "INFO")
        return self._get_selected_text_clipboard(old_clipboard)

    def _get_selected_text_accessibility(self) -> Optional[str]:
        """
        Get selected text via macOS Accessibility API.

        This method doesn't touch the clipboard, making it cleaner and faster.
        Works with most native macOS apps but may fail with Chrome, Firefox, etc.
        """
        try:
            # Get system-wide accessibility element
            system = AXUIElementCreateSystemWide()

            # Get the currently focused UI element
            err, focused = AXUIElementCopyAttributeValue(
                system, kAXFocusedUIElementAttribute, None
            )

            if err != 0 or focused is None:
                log(f"Accessibility: could not get focused element (err={err})", "INFO")
                return None

            # Get selected text from the focused element
            err, selected_text = AXUIElementCopyAttributeValue(
                focused, kAXSelectedTextAttribute, None
            )

            if err != 0 or selected_text is None:
                log(f"Accessibility: could not get selected text (err={err})", "INFO")
                return None

            # Convert to string and strip whitespace
            text = str(selected_text).strip()
            if text:
                log(f"Accessibility: got {len(text)} chars", "INFO")
                return text

            log("Accessibility: selected text is empty", "INFO")
            return None

        except Exception as e:
            log(f"Accessibility API error: {type(e).__name__}: {e}", "INFO")
            return None

    def _get_selected_text_clipboard(self, old_clipboard: Optional[str]) -> Optional[str]:
        """
        Get selected text via Cmd+C (clipboard-based fallback).

        Uses a unique marker to detect if Cmd+C actually copied something:
        1. Write a unique UUID marker to clipboard
        2. Send Cmd+C
        3. If clipboard == marker -> Cmd+C failed (no selection)
        4. If clipboard != marker -> Cmd+C succeeded, return content
        5. Restore old clipboard on failure

        This preserves user's clipboard on failure and works even if
        the user selects the same text that was already in clipboard.
        """
        marker = f"__clipboard_marker_{uuid.uuid4()}__"

        try:
            # Write marker to clipboard
            subprocess.run(['pbcopy'], input=marker.encode(), timeout=CLIPBOARD_TIMEOUT)

            # Wait for user to release modifier keys (fixes Ctrl+Shift+Cmd+C bug)
            time.sleep(MODIFIER_RELEASE_DELAY)

            # Simulate Cmd+C to copy selected text
            result = subprocess.run([
                'osascript', '-e',
                'tell application "System Events" to keystroke "c" using command down'
            ], capture_output=True, timeout=CLIPBOARD_TIMEOUT)

            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='replace')[:100]
                log(f"Cmd+C failed (code={result.returncode}): {stderr}", "WARN")
                self._restore_clipboard(old_clipboard)
                return None

            # Brief delay for clipboard to update
            time.sleep(CLIPBOARD_DELAY)

            # Check if clipboard changed from marker
            new_clipboard = self._read_clipboard()

            if new_clipboard == marker:
                # Cmd+C didn't change clipboard = no selection
                log("Clipboard marker unchanged (no selection)", "WARN")
                self._restore_clipboard(old_clipboard)
                return None

            if new_clipboard:
                log(f"Clipboard fallback: got {len(new_clipboard)} chars", "INFO")
                return new_clipboard
            else:
                # Clipboard is empty/None after Cmd+C
                log("Clipboard empty after Cmd+C (no selection)", "WARN")
                self._restore_clipboard(old_clipboard)
                return None

        except subprocess.TimeoutExpired:
            log("Timeout getting selected text via clipboard", "WARN")
            self._restore_clipboard(old_clipboard)
            return None
        except subprocess.SubprocessError as e:
            log(f"Subprocess error getting selection via clipboard: {e}", "WARN")
            self._restore_clipboard(old_clipboard)
            return None
        except Exception as e:
            log(f"Unexpected error getting selection via clipboard: {type(e).__name__}: {e}", "WARN")
            self._restore_clipboard(old_clipboard)
            return None

    def _copy_to_clipboard(self, text: str) -> bool:
        """Copy text to clipboard."""
        try:
            subprocess.run(
                ['pbcopy'],
                input=text.encode('utf-8'),
                check=True,
                timeout=CLIPBOARD_TIMEOUT
            )
            return True
        except subprocess.TimeoutExpired:
            log("Timeout copying to clipboard", "ERR")
            return False
        except subprocess.CalledProcessError as e:
            log(f"pbcopy failed with code {e.returncode}", "ERR")
            return False
        except subprocess.SubprocessError as e:
            log(f"Subprocess error copying to clipboard: {e}", "ERR")
            return False
        except UnicodeEncodeError as e:
            log(f"Unicode encoding error copying to clipboard: {e}", "ERR")
            return False
        except Exception as e:
            log(f"Unexpected error copying to clipboard: {type(e).__name__}: {e}", "ERR")
            return False

    def _restore_clipboard(self, content: Optional[str]):
        """Restore clipboard to previous content."""
        if content is not None:
            if not self._copy_to_clipboard(content):
                log("Failed to restore original clipboard content", "WARN")

    def _show_status(self, message: str, is_error: bool = False):
        """Show status message in overlay."""
        try:
            self._overlay.set_status_text(message)
            if is_error:
                self._overlay.set_status("error")
                play_sound("Basso")
            time.sleep(STATUS_DISPLAY_DURATION)
            self._overlay.hide()
        except Exception as e:
            log(f"Error showing status overlay: {e}", "WARN")


def parse_shortcut(shortcut: str) -> tuple[Set[str], str]:
    """
    Parse a shortcut string into modifiers and key.

    Args:
        shortcut: String like "ctrl+shift+g"

    Returns:
        Tuple of (set of modifiers, key)
    """
    parts = [p.strip().lower() for p in shortcut.split("+")]
    key = parts[-1] if parts else ""
    modifiers = set(parts[:-1]) if len(parts) > 1 else set()
    return modifiers, key


def build_shortcut_map(config) -> dict:
    """
    Build a map of key -> (modifiers, mode_id) from config.

    Returns:
        Dict mapping trigger key to (required_modifiers, mode_id)
    """
    shortcut_map = {}

    shortcuts = {
        "proofread": config.shortcuts.proofread,
        "rewrite": config.shortcuts.rewrite,
        "prompt_engineer": config.shortcuts.prompt_engineer,
    }

    for mode_id, shortcut_str in shortcuts.items():
        modifiers, key = parse_shortcut(shortcut_str)
        if key:
            shortcut_map[key] = (modifiers, mode_id)

    return shortcut_map

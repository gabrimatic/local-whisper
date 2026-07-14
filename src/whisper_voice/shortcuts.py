# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Keyboard shortcut handler for text transformation modes.

Provides processing logic for text transformation shortcuts.
The actual key detection is handled by the main keyboard listener in app.py.
"""

import subprocess
import threading
import time
from typing import TYPE_CHECKING, Optional, Set

from .backends.modes import get_mode
from .config import get_config
from .selection import (
    MODIFIER_RELEASE_DELAY,
    ClipboardSnapshot,
    get_selected_text,
    write_clipboard_text,
)
from .utils import CLIPBOARD_TIMEOUT, log, play_sound
from .watchdog import TimedOut, run_with_timeout

if TYPE_CHECKING:
    from .grammar import Grammar


STATUS_DISPLAY_DURATION = 1.5

# A wedged backend must never hold _busy forever (that silently disables all
# shortcuts AND TTS via the enabled guard). Base budget plus a per-length
# allowance so long selections still get time to finish.
TRANSFORM_WATCHDOG_BASE_SECONDS = 120.0
TRANSFORM_WATCHDOG_SECONDS_PER_KCHAR = 20.0

# Selections beyond this are almost certainly an accidental select-all; local
# models would take minutes and possibly overflow their context.
MAX_SELECTION_CHARS = 30_000

# Error messages for user display (keep short for overlay)
ERR_NO_TEXT = "No text selected"
ERR_EMPTY_RESULT = "Empty result"
ERR_COPY_FAILED = "Copy failed"
ERR_BACKEND_UNAVAILABLE = "Backend unavailable"
ERR_CLIPBOARD_READ = "Clipboard read failed"
ERR_SELECTION_FAILED = "Selection failed"
ERR_SELECTION_TOO_LARGE = "Selection too large"


class ShortcutProcessor:
    """
    Process text transformation shortcuts.

    This class handles the actual text processing when a shortcut is triggered.
    Key detection is handled externally by the main keyboard listener.
    """

    def __init__(self, grammar: "Grammar", status_callback=None):
        self._grammar = grammar
        self._status_callback = status_callback
        self._busy = False
        self._lock = threading.Lock()
        self._animating = False
        # Status generation counter: delayed idle-resets only fire if no
        # newer status has been shown, so a fresh transform's "processing"
        # is never clobbered by the previous transform's idle timer.
        self._status_gen = 0
        log("ShortcutProcessor initialized", "INFO")

    def is_busy(self) -> bool:
        """Check if currently processing."""
        with self._lock:
            return self._busy

    def _emit_status(self, phase: str, message: str) -> int:
        """Send a status update and return its generation number."""
        with self._lock:
            self._status_gen += 1
            gen = self._status_gen
        if self._status_callback:
            self._status_callback(phase, message)
        return gen

    def _schedule_idle_reset(self, gen: int):
        """Reset the overlay to idle after the display window — unless a
        newer status has replaced this one in the meantime."""
        def _reset():
            with self._lock:
                if gen != self._status_gen:
                    return
            if self._status_callback:
                self._status_callback("idle", "")

        timer = threading.Timer(STATUS_DISPLAY_DURATION, _reset)
        timer.daemon = True
        timer.start()

    def _start_animation(self, mode_name: str):
        """Start processing animation in background thread."""
        self._animating = True
        self._emit_status("processing", mode_name)

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

        snapshot = None

        try:
            # Check if grammar backend is available before proceeding
            if not self._grammar.running():
                log(f"Grammar backend not available for shortcut: {mode_id}", "ERR")
                self._show_status(ERR_BACKEND_UNAVAILABLE, is_error=True)
                return

            self._emit_status("processing", "Copying...")

            # Snapshot the full pasteboard (all types) so images/files survive
            # restoration on every failure path.
            snapshot = ClipboardSnapshot.capture()

            text = get_selected_text(snapshot)

            if not text or not text.strip():
                log("No text selected or selection unchanged", "WARN")
                self._restore_clipboard(snapshot)
                self._show_status(ERR_NO_TEXT, is_error=True)
                return

            if len(text) > MAX_SELECTION_CHARS:
                log(f"Selection too large for transform: {len(text)} chars", "WARN")
                self._restore_clipboard(snapshot)
                self._show_status(ERR_SELECTION_TOO_LARGE, is_error=True)
                return

            # The paste replaces the ENTIRE selection, so its boundary
            # whitespace (double-click trailing space, triple-click newline,
            # leading indentation) belongs to the result: transform only the
            # core, re-attach the edges afterwards.
            lead_ws = text[:len(text) - len(text.lstrip())]
            trail_ws = text[len(text.rstrip()):]
            text = text.strip()

            log(f"Processing {len(text)} chars with mode: {mode.name}", "INFO")
            play_sound("Pop")

            # Call the grammar backend under a watchdog: a wedged local model
            # must never pin _busy forever (that would disable every shortcut
            # and TTS until restart).
            watchdog_seconds = (
                TRANSFORM_WATCHDOG_BASE_SECONDS
                + (len(text) / 1000.0) * TRANSFORM_WATCHDOG_SECONDS_PER_KCHAR
            )
            self._start_animation(mode.name)
            try:
                outcome = run_with_timeout(
                    self._grammar.fix_with_mode,
                    text,
                    mode_id,
                    timeout_seconds=watchdog_seconds,
                    stage="transform",
                )
            finally:
                self._stop_animation()

            if isinstance(outcome, TimedOut):
                log(f"{mode.name} timed out after {outcome.seconds:.0f}s", "ERR")
                self._restore_clipboard(snapshot)
                self._show_status("Timeout", is_error=True)
                return
            result, error = outcome

            if error:
                log(f"Backend error for {mode.name}: {error}", "ERR")
                self._restore_clipboard(snapshot)
                self._show_status(error[:40], is_error=True)
                return

            if not result or not result.strip():
                log(f"Empty result from backend for {mode.name}", "WARN")
                self._restore_clipboard(snapshot)
                self._show_status(ERR_EMPTY_RESULT, is_error=True)
                return

            # Re-attach the selection's own boundary whitespace so pasting
            # over the span doesn't merge lines or glue words together.
            result = lead_ws + result.strip() + trail_ws

            # Copy result to clipboard. Even in paste mode the result stays on
            # the clipboard as a backup, so a paste that lands nowhere never
            # loses the transformed text.
            if not write_clipboard_text(result):
                log("Failed to copy result to clipboard", "ERR")
                self._restore_clipboard(snapshot)
                self._show_status(ERR_COPY_FAILED, is_error=True)
                return

            # Paste over the still-active selection when configured.
            pasted = False
            if get_config().shortcuts.paste_result:
                pasted = self._paste_over_selection()
                if not pasted:
                    log("Paste-in-place failed; result left in clipboard", "WARN")

            # Success. The idle reset runs on a timer so _busy releases
            # immediately — rapid back-to-back transforms must not drop
            # presses during the 1.5s status display.
            char_diff = len(result) - len(text)
            diff_str = f"+{char_diff}" if char_diff >= 0 else str(char_diff)
            done_msg = f"Replaced! ({diff_str} chars)" if pasted else f"Done! ({diff_str} chars)"
            gen = self._emit_status("done", done_msg)
            play_sound("Glass")
            log(f"{mode.name}: {len(text)} -> {len(result)} chars ({diff_str})", "OK")
            self._schedule_idle_reset(gen)

        except subprocess.TimeoutExpired as e:
            log(f"Timeout during shortcut processing: {e}", "ERR")
            self._restore_clipboard(snapshot)
            self._show_status("Timeout", is_error=True)
        except subprocess.SubprocessError as e:
            log(f"Subprocess error during shortcut: {e}", "ERR")
            self._restore_clipboard(snapshot)
            self._show_status("System error", is_error=True)
        except Exception as e:
            log(f"Unexpected error during shortcut processing: {type(e).__name__}: {e}", "ERR")
            self._restore_clipboard(snapshot)
            self._show_status("Error", is_error=True)
        finally:
            with self._lock:
                self._busy = False

    def _paste_over_selection(self) -> bool:
        """Paste the clipboard (the transformed result) over the selection.

        The original selection is normally still active in the source app, so
        Cmd+V replaces it in place. Waits briefly first so a still-held
        shortcut modifier can't turn Cmd+V into Ctrl+Shift+Cmd+V.
        """
        try:
            time.sleep(MODIFIER_RELEASE_DELAY)
            result = subprocess.run([
                'osascript', '-e',
                'tell application "System Events" to keystroke "v" using command down'
            ], capture_output=True, timeout=CLIPBOARD_TIMEOUT)
            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='replace')[:100]
                log(f"Paste keystroke failed (code={result.returncode}): {stderr}", "WARN")
                return False
            return True
        except subprocess.TimeoutExpired:
            log("Timeout pasting result over selection", "WARN")
            return False
        except Exception as e:
            log(f"Unexpected error pasting result: {type(e).__name__}: {e}", "WARN")
            return False

    def _restore_clipboard(self, snapshot: Optional[ClipboardSnapshot]):
        """Restore the pasteboard to its captured state."""
        if snapshot is not None and not snapshot.restore():
            log("Original clipboard content could not be restored", "WARN")

    def _show_status(self, message: str, is_error: bool = False):
        """Show a status message, then reset to idle on a timer (non-blocking
        so _busy releases immediately and back-to-back presses still work)."""
        try:
            phase = "error" if is_error else "done"
            gen = self._emit_status(phase, message)
            if is_error:
                play_sound("Basso")
            self._schedule_idle_reset(gen)
        except Exception as e:
            log(f"Error showing status: {e}", "WARN")


# ---------------------------------------------------------------------------
# Shortcut string parsing / validation
# ---------------------------------------------------------------------------

# Canonical modifier names plus the aliases users naturally type.
MODIFIER_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl", "ctl": "ctrl",
    "shift": "shift",
    "cmd": "cmd", "command": "cmd", "meta": "cmd", "super": "cmd",
    "alt": "alt", "option": "alt", "opt": "alt",
}
_MODIFIER_ORDER = ("ctrl", "alt", "shift", "cmd")

# Keys the CGEventTap interceptor can match (must stay in sync with
# key_interceptor.VK_TO_CHAR).
_LETTERS = set("abcdefghijklmnopqrstuvwxyz")
_DIGITS = set("0123456789")
_FUNCTION_KEYS = {f"f{n}" for n in range(1, 13)}
_PUNCTUATION = set(",./;'[]\\-=`")
SUPPORTED_KEYS = _LETTERS | _DIGITS | _FUNCTION_KEYS | _PUNCTUATION

# Keys that may be bound without a modifier. Letters/digits/punctuation
# without a modifier would hijack normal typing system-wide.
_BARE_ALLOWED_KEYS = _FUNCTION_KEYS


def parse_shortcut(shortcut: str) -> tuple[Set[str], str]:
    """
    Parse a shortcut string into normalized modifiers and key.

    Modifier aliases are normalized (option/opt -> alt, command/meta -> cmd,
    control/ctl -> ctrl). Unknown modifier tokens are preserved verbatim so
    validate_shortcut() can name them; they will never match a real event.

    Args:
        shortcut: String like "ctrl+shift+g"

    Returns:
        Tuple of (set of modifiers, key)
    """
    parts = [p.strip().lower() for p in shortcut.split("+")]
    parts = [p for p in parts if p or len(parts) == 1]
    key = parts[-1] if parts else ""
    modifiers = {MODIFIER_ALIASES.get(p, p) for p in parts[:-1]} if len(parts) > 1 else set()
    return modifiers, key


def normalize_shortcut(shortcut: str) -> str:
    """Render a shortcut in canonical form, e.g. "shift+control+G" -> "ctrl+shift+g"."""
    modifiers, key = parse_shortcut(shortcut)
    ordered = [m for m in _MODIFIER_ORDER if m in modifiers]
    ordered += sorted(m for m in modifiers if m not in _MODIFIER_ORDER)
    return "+".join(ordered + [key]) if key else ""


def validate_shortcut(shortcut: str) -> Optional[str]:
    """
    Check whether a shortcut string can actually be intercepted.

    Returns None when valid, otherwise a human-readable problem description.
    An empty string is valid and means "this shortcut is disabled".
    """
    if not shortcut or not shortcut.strip():
        return None
    modifiers, key = parse_shortcut(shortcut)
    if not key:
        return "missing key (format: modifier+key, e.g. ctrl+shift+g)"
    unknown = sorted(m for m in modifiers if m not in _MODIFIER_ORDER)
    if unknown:
        return f"unknown modifier: {', '.join(unknown)} (use ctrl, alt, shift, cmd)"
    if key not in SUPPORTED_KEYS:
        return f"unsupported key '{key}' (use a-z, 0-9, f1-f12, or , . / ; ' [ ] \\ - = `)"
    if not modifiers and key not in _BARE_ALLOWED_KEYS:
        return f"'{key}' needs at least one modifier, or it would hijack normal typing"
    return None


def build_shortcut_map(config) -> tuple[dict, list]:
    """
    Build the transform-shortcut bindings from config.

    Returns:
        Tuple of (bindings, problems) where bindings maps
        (key, frozenset(modifiers)) -> mode_id and problems is a list of
        human-readable strings for invalid or conflicting shortcuts.
        Empty shortcut strings silently disable the mode.
    """
    bindings: dict = {}
    problems: list = []

    shortcuts = {
        "proofread": config.shortcuts.proofread,
        "rewrite": config.shortcuts.rewrite,
        "prompt_engineer": config.shortcuts.prompt_engineer,
    }

    for mode_id, shortcut_str in shortcuts.items():
        if not shortcut_str or not shortcut_str.strip():
            continue
        error = validate_shortcut(shortcut_str)
        if error:
            problems.append(f"{mode_id} shortcut '{shortcut_str}': {error}")
            continue
        modifiers, key = parse_shortcut(shortcut_str)
        combo = (key, frozenset(modifiers))
        if combo in bindings:
            problems.append(
                f"{mode_id} shortcut '{shortcut_str}' conflicts with {bindings[combo]} — ignored"
            )
            continue
        bindings[combo] = mode_id

    return bindings, problems

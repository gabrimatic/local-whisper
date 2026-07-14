# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
CGEventTap-based keyboard shortcut interception for macOS.

This module intercepts keyboard shortcuts at the system level, allowing
the application to suppress key events so they don't reach other apps.

Usage:
    interceptor = KeyInterceptor()
    interceptor.register_shortcut({"ctrl", "shift"}, "g", callback_fn)
    interceptor.set_enabled_guard(lambda: app_is_ready)
    interceptor.start()
    ...
    interceptor.stop()
"""

import threading
from typing import Callable, Dict, FrozenSet, List, Optional, Set, Tuple

from Quartz import (
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRun,
    CFRunLoopStop,
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    CGEventMaskBit,
    CGEventTapCreate,
    CGEventTapEnable,
    kCFRunLoopCommonModes,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskShift,
    kCGEventKeyDown,
    kCGEventTapDisabledByTimeout,
    kCGEventTapDisabledByUserInput,
    kCGEventTapOptionDefault,
    kCGHeadInsertEventTap,
    kCGKeyboardEventKeycode,
    kCGSessionEventTap,
)

from .utils import log, request_accessibility_permission

# macOS virtual keycodes
KEY_SPACE = 49
KEY_ESC = 53

# ANSI-layout virtual keycodes -> shortcut key names. Letters, digits,
# function keys, and common punctuation. Must stay in sync with
# shortcuts.SUPPORTED_KEYS. Note: modifier keys (Option, Command, ...)
# emit flagsChanged events, not keyDown, so they can never appear here.
VK_TO_CHAR = {
    0x00: 'a', 0x0B: 'b', 0x08: 'c', 0x02: 'd', 0x0E: 'e', 0x03: 'f',
    0x05: 'g', 0x04: 'h', 0x22: 'i', 0x26: 'j', 0x28: 'k', 0x25: 'l',
    0x2E: 'm', 0x2D: 'n', 0x1F: 'o', 0x23: 'p', 0x0C: 'q', 0x0F: 'r',
    0x01: 's', 0x11: 't', 0x20: 'u', 0x09: 'v', 0x0D: 'w', 0x07: 'x',
    0x10: 'y', 0x06: 'z',
    # Digits
    0x12: '1', 0x13: '2', 0x14: '3', 0x15: '4', 0x17: '5',
    0x16: '6', 0x1A: '7', 0x1C: '8', 0x19: '9', 0x1D: '0',
    # Function keys
    0x7A: 'f1', 0x78: 'f2', 0x63: 'f3', 0x76: 'f4', 0x60: 'f5', 0x61: 'f6',
    0x62: 'f7', 0x64: 'f8', 0x65: 'f9', 0x6D: 'f10', 0x67: 'f11', 0x6F: 'f12',
    # Punctuation
    0x2B: ',', 0x2F: '.', 0x2C: '/', 0x29: ';', 0x27: "'",
    0x21: '[', 0x1E: ']', 0x2A: '\\', 0x1B: '-', 0x18: '=', 0x32: '`',
}

# Key name -> keycode (for suppressing a non-modifier recording trigger).
KEYCODE_FOR_KEY_NAME = {name: code for code, name in VK_TO_CHAR.items()}


class KeyInterceptor:
    """
    Intercepts and optionally suppresses keyboard shortcuts using CGEventTap.

    CGEventTap allows intercepting events before they reach applications.
    By returning None from the callback, events are suppressed.
    By returning the event, they pass through normally.
    """

    def __init__(self):
        # key -> list of (required_modifiers, callback). Multiple bindings can
        # share a key as long as their modifier sets differ; matching is exact.
        self._shortcuts: Dict[str, List[Tuple[FrozenSet[str], Callable]]] = {}
        self._enabled_guard: Optional[Callable[[], bool]] = None
        self._run_loop = None
        self._tap = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._recording_active = False
        self._recording_handler: Optional[Callable] = None
        self._speaking_active = False
        self._speaking_handler: Optional[Callable] = None
        self._record_keycode: Optional[int] = None
        # Set once the tap thread reaches its run loop (or fails), so stop()
        # can synchronize with a start() still in flight.
        self._started_event = threading.Event()

    def register_shortcut(self, modifiers: Set[str], key: str, callback: Callable):
        """
        Register a shortcut to intercept. A binding with the same key and the
        same modifier set replaces the previous one; a different modifier set
        on the same key coexists with it.

        Args:
            modifiers: Set of modifier keys (e.g., {"ctrl", "shift"})
            key: The trigger key (lowercase, e.g., "g" or "f6")
            callback: Function to call when shortcut is pressed
        """
        combo = frozenset(modifiers)
        with self._lock:
            bindings = self._shortcuts.setdefault(key.lower(), [])
            bindings[:] = [(mods, cb) for mods, cb in bindings if mods != combo]
            bindings.append((combo, callback))

    def unregister_shortcut(self, key: str, modifiers: Optional[Set[str]] = None):
        """Remove binding(s) for a key. With modifiers, remove only that combo;
        without, remove every binding on the key. No-op if not registered."""
        with self._lock:
            bindings = self._shortcuts.get(key.lower())
            if bindings is None:
                return
            if modifiers is None:
                del self._shortcuts[key.lower()]
                return
            combo = frozenset(modifiers)
            bindings[:] = [(mods, cb) for mods, cb in bindings if mods != combo]
            if not bindings:
                del self._shortcuts[key.lower()]

    def clear_shortcuts(self):
        """Remove every registered shortcut binding."""
        with self._lock:
            self._shortcuts.clear()

    def set_record_keycode(self, keycode: Optional[int]):
        """Set the keycode of a non-modifier recording trigger (e.g. an F-key).

        While set, that key is always suppressed so pressing the dictation
        trigger never leaks a keystroke into the frontmost app. Pass None for
        modifier triggers (they emit flagsChanged, which this tap never sees).
        """
        with self._lock:
            self._record_keycode = keycode

    def set_recording_active(self, active: bool):
        """Enable or disable recording-mode suppression (thread-safe)."""
        with self._lock:
            self._recording_active = active

    def set_recording_handler(self, callback: Callable):
        """Set the callback invoked for every key during recording mode."""
        with self._lock:
            self._recording_handler = callback

    def set_speaking_active(self, active: bool):
        """Enable or disable speaking-mode Esc interception (thread-safe)."""
        with self._lock:
            self._speaking_active = active

    def set_speaking_handler(self, callback: Callable):
        """Set the callback invoked when Esc is pressed during speaking."""
        with self._lock:
            self._speaking_handler = callback

    def set_enabled_guard(self, guard: Callable[[], bool]):
        """
        Set a guard callback that determines if interception is enabled.

        The guard is called for every potential shortcut match.
        If it returns False, the shortcut is not intercepted (passes through).

        Args:
            guard: Callable returning True if interception should be active
        """
        self._enabled_guard = guard

    def start(self) -> bool:
        """
        Start the event tap in a background thread.

        Returns:
            True if started successfully, False otherwise.
        """
        with self._lock:
            if self._running:
                return True

        try:
            self._started_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            return True
        except Exception as e:
            log(f"Failed to start KeyInterceptor: {e}", "ERR")
            return False

    def stop(self):
        """Stop the event tap and clean up."""
        # Wait for a mid-flight start() to reach its run loop first: a stop
        # issued during startup would otherwise be a silent no-op and leave
        # the tap thread alive forever.
        if self._thread and self._thread.is_alive():
            self._started_event.wait(timeout=2.0)

        with self._lock:
            if not self._running:
                return
            self._running = False

        # Stop the run loop if it exists
        if self._run_loop:
            try:
                CFRunLoopStop(self._run_loop)
            except Exception:
                pass
            self._run_loop = None

        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _run(self):
        """Run the event tap (called in background thread)."""
        try:
            # Create the event tap
            # We're interested in key down events
            event_mask = CGEventMaskBit(kCGEventKeyDown)

            tap = CGEventTapCreate(
                kCGSessionEventTap,      # Tap at session level
                kCGHeadInsertEventTap,   # Insert at head (before other taps)
                kCGEventTapOptionDefault,  # Active tap (can modify/suppress events)
                event_mask,
                self._callback,
                None  # User info (not needed)
            )

            if tap is None:
                log("CGEventTap creation failed (check Accessibility permissions)", "ERR")
                request_accessibility_permission()  # fallback: trigger system dialog if not already shown
                return

            # Create run loop source
            run_loop_source = CFMachPortCreateRunLoopSource(None, tap, 0)
            if run_loop_source is None:
                log("Failed to create run loop source", "ERR")
                return

            # Add to current thread's run loop
            self._run_loop = CFRunLoopGetCurrent()
            CFRunLoopAddSource(self._run_loop, run_loop_source, kCFRunLoopCommonModes)

            # Enable the tap
            self._tap = tap
            CGEventTapEnable(tap, True)

            with self._lock:
                self._running = True
            self._started_event.set()

            log("KeyInterceptor started", "OK")

            # Run the loop (blocks until stopped)
            CFRunLoopRun()

        except Exception as e:
            log(f"KeyInterceptor error: {e}", "ERR")
        finally:
            self._started_event.set()
            self._tap = None
            with self._lock:
                self._running = False
            log("KeyInterceptor stopped", "INFO")

    def _callback(self, proxy, event_type, event, refcon):
        """
        CGEventTap callback.

        Returns:
            None to suppress the event, or event to pass through.
        """
        try:
            # macOS disables a tap it considers unresponsive (or on certain
            # secure input transitions) and delivers these marker events
            # instead of key events. Without re-enabling, recording-key
            # suppression and all shortcuts silently die until restart.
            if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
                tap = self._tap
                if tap is not None:
                    CGEventTapEnable(tap, True)
                    log("KeyInterceptor: event tap disabled by macOS — re-enabled", "WARN")
                return event

            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            flags = CGEventGetFlags(event)

            with self._lock:
                recording_active = self._recording_active
                recording_handler = self._recording_handler
                speaking_active = self._speaking_active
                speaking_handler = self._speaking_handler
                record_keycode = self._record_keycode

            # Space/Esc control an active recording; a non-modifier trigger
            # key (e.g. F6) is suppressed whenever it is configured so the
            # dictation trigger never leaks a keystroke into the frontmost
            # app. Modifier triggers emit flagsChanged and never reach here.
            recording_keys = {KEY_SPACE, KEY_ESC}
            if record_keycode is not None:
                recording_keys.add(record_keycode)

            if recording_active and keycode in recording_keys:
                if recording_handler:
                    threading.Thread(target=recording_handler, args=(keycode, flags), daemon=True).start()
                return None

            if not recording_active and record_keycode is not None and keycode == record_keycode:
                # Idle press of the dedicated trigger key: the pynput listener
                # (a separate listen-only tap) sees the same event and starts
                # the recording; we only swallow the keystroke.
                return None

            if speaking_active and keycode == KEY_ESC and speaking_handler is not None:
                threading.Thread(target=speaking_handler, daemon=True).start()
                return None

            char = VK_TO_CHAR.get(keycode)
            if char is None:
                return event

            with self._lock:
                bindings = list(self._shortcuts.get(char, ()))
            if not bindings:
                return event

            active_modifiers = set()
            if flags & kCGEventFlagMaskControl:
                active_modifiers.add("ctrl")
            if flags & kCGEventFlagMaskShift:
                active_modifiers.add("shift")
            if flags & kCGEventFlagMaskCommand:
                active_modifiers.add("cmd")
            if flags & kCGEventFlagMaskAlternate:
                active_modifiers.add("alt")

            # Exact modifier match: ctrl+shift+g must not also fire (and
            # steal) ctrl+shift+cmd+g, which may belong to another app.
            callback = None
            for required_modifiers, bound_callback in bindings:
                if active_modifiers == required_modifiers:
                    callback = bound_callback
                    break
            if callback is None:
                return event
            if self._enabled_guard and not self._enabled_guard():
                # This combo is OURS but the app is busy (recording or mid-
                # transform). Swallow it instead of passing it through —
                # otherwise the press types a stray character (Opt+T = '†')
                # into the user's document at the worst possible moment.
                return None

            # Off-thread so the event tap keeps pumping during the callback.
            threading.Thread(target=callback, daemon=True).start()
            return None

        except Exception as e:
            log(f"KeyInterceptor callback error: {e}", "ERR")
            return event

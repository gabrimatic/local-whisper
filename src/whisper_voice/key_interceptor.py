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
from typing import Callable, Dict, Optional, Set, Tuple

from Quartz import (
    CGEventTapCreate,
    kCGSessionEventTap,
    kCGHeadInsertEventTap,
    kCGEventTapOptionDefault,
    CGEventMaskBit,
    kCGEventKeyDown,
    CGEventTapEnable,
    CGEventGetIntegerValueField,
    CGEventGetFlags,
    kCGKeyboardEventKeycode,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskShift,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskAlternate,
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRun,
    CFRunLoopStop,
    kCFRunLoopCommonModes,
)

from .utils import log, request_accessibility_permission


# macOS virtual key codes to character mapping
VK_TO_CHAR = {
    0x00: 'a', 0x0B: 'b', 0x08: 'c', 0x02: 'd', 0x0E: 'e', 0x03: 'f',
    0x05: 'g', 0x04: 'h', 0x22: 'i', 0x26: 'j', 0x28: 'k', 0x25: 'l',
    0x2E: 'm', 0x2D: 'n', 0x1F: 'o', 0x23: 'p', 0x0C: 'q', 0x0F: 'r',
    0x01: 's', 0x11: 't', 0x20: 'u', 0x09: 'v', 0x0D: 'w', 0x07: 'x',
    0x10: 'y', 0x06: 'z',
}


class KeyInterceptor:
    """
    Intercepts and optionally suppresses keyboard shortcuts using CGEventTap.

    CGEventTap allows intercepting events before they reach applications.
    By returning None from the callback, events are suppressed.
    By returning the event, they pass through normally.
    """

    def __init__(self):
        self._shortcuts: Dict[str, Tuple[Set[str], Callable]] = {}  # key -> (modifiers, callback)
        self._enabled_guard: Optional[Callable[[], bool]] = None
        self._run_loop = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

    def register_shortcut(self, modifiers: Set[str], key: str, callback: Callable):
        """
        Register a shortcut to intercept.

        Args:
            modifiers: Set of modifier keys (e.g., {"ctrl", "shift"})
            key: The trigger key (lowercase, e.g., "g")
            callback: Function to call when shortcut is pressed
        """
        with self._lock:
            self._shortcuts[key.lower()] = (modifiers, callback)

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
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            return True
        except Exception as e:
            log(f"Failed to start KeyInterceptor: {e}", "ERR")
            return False

    def stop(self):
        """Stop the event tap and clean up."""
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
            CGEventTapEnable(tap, True)

            with self._lock:
                self._running = True

            log("KeyInterceptor started", "OK")

            # Run the loop (blocks until stopped)
            CFRunLoopRun()

        except Exception as e:
            log(f"KeyInterceptor error: {e}", "ERR")
        finally:
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
            # Get the key code
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            char = VK_TO_CHAR.get(keycode)

            if char is None:
                # Not an alphabetic key we care about
                return event

            # Check if we have a shortcut registered for this key
            with self._lock:
                if char not in self._shortcuts:
                    return event
                required_modifiers, callback = self._shortcuts[char]

            # Check modifier flags
            flags = CGEventGetFlags(event)
            active_modifiers = set()

            if flags & kCGEventFlagMaskControl:
                active_modifiers.add("ctrl")
            if flags & kCGEventFlagMaskShift:
                active_modifiers.add("shift")
            if flags & kCGEventFlagMaskCommand:
                active_modifiers.add("cmd")
            if flags & kCGEventFlagMaskAlternate:
                active_modifiers.add("alt")

            # Check if required modifiers are held
            if not (active_modifiers >= required_modifiers):
                return event

            # Check enabled guard
            if self._enabled_guard and not self._enabled_guard():
                return event

            # Trigger callback in a separate thread to avoid blocking
            threading.Thread(target=callback, daemon=True).start()

            # Suppress the event
            return None

        except Exception as e:
            log(f"KeyInterceptor callback error: {e}", "ERR")
            return event

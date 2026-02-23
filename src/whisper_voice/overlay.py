# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Floating overlay window for Local Whisper.

Shows recording status in a transparent window at center-bottom of screen.
"""

import threading
import queue
from typing import Optional, Callable

from .config import get_config
from .utils import ICON_IMAGE, OVERLAY_WAVE_FRAMES, log

# Will be imported lazily to avoid issues on non-macOS
_AppKit = None
_Foundation = None
_Quartz = None
_Performer = None
# Bounded queue to prevent unbounded memory growth in long sessions
_callback_queue = queue.Queue(maxsize=100)


def _import_macos():
    """Lazily import macOS frameworks and create Performer class."""
    global _AppKit, _Foundation, _Quartz, _Performer
    if _AppKit is None:
        import AppKit as _AppKit
        import Foundation as _Foundation
        import Quartz as _Quartz

        # Define Performer class once at module level
        class _PerformerClass(_Foundation.NSObject):
            def perform_(self, _):
                try:
                    while True:
                        func = _callback_queue.get_nowait()
                        try:
                            func()
                        except Exception as e:
                            # Log overlay errors but don't crash - UI errors are non-fatal
                            log(f"Overlay callback error: {e}", "WARN")
                except queue.Empty:
                    pass

        _Performer = _PerformerClass


def _perform_on_main_thread(func: Callable, wait: bool = False):
    """Execute a function on the main thread."""
    _import_macos()
    try:
        _callback_queue.put_nowait(func)
    except queue.Full:
        # Queue full, skip this update (non-critical for UI)
        return
    performer = _Performer.alloc().init()
    performer.performSelectorOnMainThread_withObject_waitUntilDone_(
        _Foundation.NSSelectorFromString("perform:"),
        None,
        wait
    )


class RecordingOverlay:
    """
    Transparent floating window that shows during recording.

    Displays:
    - Recording indicator (red dot)
    - Duration counter
    - Active app name
    """

    def __init__(self):
        self._window = None
        self._text_field = None
        self._duration_field = None
        self._app_field = None
        self._wave_view = None
        self._font = None
        self._lock = threading.Lock()
        self._visible = False

    def _create_window(self):
        """Create the overlay window on the main thread."""
        _import_macos()

        config = get_config()

        # Get screen dimensions
        screen = _AppKit.NSScreen.mainScreen()
        screen_frame = screen.frame()
        screen_width = screen_frame.size.width
        screen_height = screen_frame.size.height

        # Compact pill (expands for status text)
        window_width = 160
        window_height = 32

        # Center, lower third
        x = (screen_width - window_width) / 2
        y = screen_height * 0.33

        # Window
        self._window = _AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            _Foundation.NSMakeRect(x, y, window_width, window_height),
            _AppKit.NSWindowStyleMaskBorderless,
            _AppKit.NSBackingStoreBuffered,
            False
        )
        self._window.setLevel_(_AppKit.NSStatusWindowLevel)
        self._window.setOpaque_(False)
        self._window.setAlphaValue_(config.ui.overlay_opacity)
        self._window.setBackgroundColor_(_AppKit.NSColor.clearColor())
        self._window.setIgnoresMouseEvents_(True)
        self._window.setHasShadow_(True)
        self._window.setCollectionBehavior_(
            _AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces |
            _AppKit.NSWindowCollectionBehaviorStationary
        )

        # Frosted dark background
        content = _AppKit.NSView.alloc().initWithFrame_(
            _Foundation.NSMakeRect(0, 0, window_width, window_height)
        )
        content.setWantsLayer_(True)
        layer = content.layer()
        layer.setCornerRadius_(window_height / 2)
        layer.setBackgroundColor_(
            _Quartz.CGColorCreateGenericRGB(0.12, 0.12, 0.14, 0.88)
        )

        # Wave image
        self._wave_size = 22
        self._wave_gap = 8
        wave_x = 12
        wave_y = (window_height - self._wave_size) / 2
        self._wave_view = _AppKit.NSImageView.alloc().initWithFrame_(
            _Foundation.NSMakeRect(wave_x, wave_y, self._wave_size, self._wave_size)
        )
        self._wave_view.setImage_(_AppKit.NSImage.alloc().initWithContentsOfFile_(OVERLAY_WAVE_FRAMES[0]))
        self._wave_view.setImageScaling_(_AppKit.NSImageScaleProportionallyUpOrDown)
        content.addSubview_(self._wave_view)

        # Text field
        text_x = wave_x + self._wave_size + self._wave_gap
        self._duration_field = _AppKit.NSTextField.alloc().initWithFrame_(
            _Foundation.NSMakeRect(text_x, (window_height - 18) / 2, window_width - text_x - 10, 18)
        )
        self._duration_field.setStringValue_("0.0")
        self._duration_field.setBezeled_(False)
        self._duration_field.setDrawsBackground_(False)
        self._duration_field.setEditable_(False)
        self._duration_field.setSelectable_(False)
        self._duration_field.setTextColor_(_AppKit.NSColor.whiteColor())
        self._font = _AppKit.NSFont.monospacedSystemFontOfSize_weight_(13, _AppKit.NSFontWeightSemibold)
        self._duration_field.setFont_(self._font)
        self._duration_field.setAlignment_(_AppKit.NSTextAlignmentLeft)
        content.addSubview_(self._duration_field)

        self._text_field = None
        self._app_field = None
        self._window.setContentView_(content)
        self._window_width = window_width
        self._window_height = window_height

    def _layout_row(self, text: str):
        if not self._duration_field or not self._wave_view or not self._font:
            return
        attrs = {_AppKit.NSFontAttributeName: self._font}
        text_width = _Foundation.NSString.stringWithString_(text).sizeWithAttributes_(attrs).width
        total = self._wave_size + self._wave_gap + text_width
        start_x = (self._window_width - total) / 2
        if start_x < 8:
            start_x = 8
        wave_y = (self._window_height - self._wave_size) / 2
        self._wave_view.setFrame_(_Foundation.NSMakeRect(start_x, wave_y, self._wave_size, self._wave_size))
        text_x = start_x + self._wave_size + self._wave_gap
        text_width = self._window_width - text_x - 8
        self._duration_field.setFrame_(
            _Foundation.NSMakeRect(text_x, (self._window_height - 18) / 2, text_width, 18)
        )

    def show(self):
        """Show the overlay window."""
        config = get_config()
        if not config.ui.show_overlay:
            return

        def _show():
            with self._lock:
                if self._window is None:
                    self._create_window()
                if self._duration_field:
                    text = "0.0"
                    self._duration_field.setStringValue_(text)
                    self._layout_row(text)
                    self._duration_field.setTextColor_(
                        _AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.35, 0.35, 1.0)
                    )
                if self._wave_view:
                    self._wave_view.setImage_(
                        _AppKit.NSImage.alloc().initWithContentsOfFile_(OVERLAY_WAVE_FRAMES[0])
                    )
                self._window.orderFront_(None)
                self._visible = True

        _perform_on_main_thread(_show, wait=True)

    def hide(self):
        """Hide the overlay window."""
        def _hide():
            with self._lock:
                if self._window:
                    self._window.orderOut_(None)
                self._visible = False

        _perform_on_main_thread(_hide)

    def update_duration(self, seconds: float, frame: str = ""):
        """Update the duration display."""
        config = get_config()
        if not config.ui.show_overlay:
            return

        with self._lock:
            if not self._visible or self._duration_field is None:
                return

        _import_macos()

        def _update():
            if self._duration_field:
                text = f"{seconds:.1f}"
                self._duration_field.setStringValue_(text)
                self._layout_row(text)
                self._duration_field.setTextColor_(
                    _AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.35, 0.35, 1.0)
                )
            if self._wave_view and frame:
                self._wave_view.setImage_(_AppKit.NSImage.alloc().initWithContentsOfFile_(frame))

        _perform_on_main_thread(_update, wait=True)

    def set_status_text(self, text: str):
        """Update overlay with custom status text."""
        config = get_config()
        if not config.ui.show_overlay:
            return
        _import_macos()

        def _update():
            with self._lock:
                if self._window is None:
                    self._create_window()
                if self._duration_field is None:
                    return

                self._duration_field.setStringValue_(text)
                self._layout_row(text)
                self._duration_field.setTextColor_(_AppKit.NSColor.whiteColor())

                # Show static wave image
                if self._wave_view and OVERLAY_WAVE_FRAMES:
                    self._wave_view.setImage_(
                        _AppKit.NSImage.alloc().initWithContentsOfFile_(OVERLAY_WAVE_FRAMES[0])
                    )

                self._window.orderFront_(None)
                self._visible = True

        _perform_on_main_thread(_update, wait=True)

    def set_status(self, status: str):
        """Update overlay: 'processing', 'done', 'error'."""
        config = get_config()
        if not config.ui.show_overlay:
            return
        _import_macos()

        def _update():
            with self._lock:
                # Ensure window exists
                if self._window is None:
                    self._create_window()
                if self._duration_field is None:
                    return

                if status == "processing":
                    text = "···"
                    self._duration_field.setStringValue_(text)
                    self._layout_row(text)
                    self._duration_field.setTextColor_(_AppKit.NSColor.lightGrayColor())
                    if self._wave_view:
                        self._wave_view.setImage_(_AppKit.NSImage.alloc().initWithContentsOfFile_(OVERLAY_WAVE_FRAMES[0]))
                elif status == "done":
                    text = "Copied"
                    self._duration_field.setStringValue_(text)
                    self._layout_row(text)
                    self._duration_field.setTextColor_(
                        _AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.4, 0.9, 0.5, 1.0)
                    )
                    if self._wave_view:
                        self._wave_view.setImage_(_AppKit.NSImage.alloc().initWithContentsOfFile_(OVERLAY_WAVE_FRAMES[0]))
                elif status == "error":
                    text = "Failed"
                    self._duration_field.setStringValue_(text)
                    self._layout_row(text)
                    self._duration_field.setTextColor_(
                        _AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.4, 0.4, 1.0)
                    )
                    if self._wave_view:
                        self._wave_view.setImage_(_AppKit.NSImage.alloc().initWithContentsOfFile_(OVERLAY_WAVE_FRAMES[0]))

                # Ensure visible
                self._window.orderFront_(None)
                self._visible = True

        _perform_on_main_thread(_update, wait=True)

    def set_processing_frame(self, frame: str):
        """Update overlay during processing with a waveform frame."""
        config = get_config()
        if not config.ui.show_overlay:
            return
        _import_macos()

        def _update():
            with self._lock:
                if self._window is None:
                    self._create_window()
                if self._duration_field is None:
                    return
                text = "···"
                self._duration_field.setStringValue_(text)
                self._layout_row(text)
                self._duration_field.setTextColor_(_AppKit.NSColor.lightGrayColor())
                if self._wave_view and frame:
                    self._wave_view.setImage_(_AppKit.NSImage.alloc().initWithContentsOfFile_(frame))
                self._window.orderFront_(None)
                self._visible = True

        _perform_on_main_thread(_update, wait=True)


# Global overlay instance
_overlay: Optional[RecordingOverlay] = None


def get_overlay() -> RecordingOverlay:
    """Get the global overlay instance."""
    global _overlay
    if _overlay is None:
        _overlay = RecordingOverlay()
    return _overlay

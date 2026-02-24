# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Central theme module for Local Whisper's GUI.

Defines all shared visual constants, color helpers, typography helpers,
layout dimensions, and glass-effect utilities used by the overlay and
settings window.
"""

# Will be imported lazily to avoid issues on non-macOS
_AppKit = None
_Foundation = None
_Quartz = None


def _ensure_imports():
    global _AppKit, _Foundation, _Quartz
    if _AppKit is not None:
        return
    import AppKit as _ak
    import Foundation as _fd
    import Quartz as _qz
    _AppKit = _ak
    _Foundation = _fd
    _Quartz = _qz


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

class Colors:
    """Static methods returning NSColor instances for consistent UI theming."""

    @staticmethod
    def recording():
        """Vibrant red used while recording is active."""
        _ensure_imports()
        return _AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            1.0, 0.33, 0.33, 1.0
        )

    @staticmethod
    def processing():
        """Secondary label color used during processing state."""
        _ensure_imports()
        return _AppKit.NSColor.secondaryLabelColor()

    @staticmethod
    def done():
        """System green used when transcription completes successfully."""
        _ensure_imports()
        return _AppKit.NSColor.systemGreenColor()

    @staticmethod
    def error():
        """System red used for error states."""
        _ensure_imports()
        return _AppKit.NSColor.systemRedColor()

    @staticmethod
    def warning():
        """System orange used for warning states (replaces hardcoded amber)."""
        _ensure_imports()
        return _AppKit.NSColor.systemOrangeColor()

    @staticmethod
    def label():
        """Primary label color for body text."""
        _ensure_imports()
        return _AppKit.NSColor.labelColor()

    @staticmethod
    def secondary_label():
        """Secondary label color for supporting text."""
        _ensure_imports()
        return _AppKit.NSColor.secondaryLabelColor()

    @staticmethod
    def link():
        """Link color for clickable text."""
        _ensure_imports()
        return _AppKit.NSColor.linkColor()

    @staticmethod
    def level_silence():
        """Dim gray used for the audio level indicator when silent."""
        _ensure_imports()
        return _AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.5, 0.5, 0.5, 0.5
        )

    @staticmethod
    def level_speech():
        """Green used for the audio level indicator during normal speech."""
        _ensure_imports()
        return _AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.35, 0.85, 0.45, 0.85
        )

    @staticmethod
    def level_loud():
        """Orange used for the audio level indicator when input is loud."""
        _ensure_imports()
        return _AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            1.0, 0.6, 0.2, 0.9
        )

    @staticmethod
    def glass_border():
        """White at 15% alpha for the 0.5px glass panel border."""
        _ensure_imports()
        return _AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            1.0, 1.0, 1.0, 0.15
        )

    @staticmethod
    def status_text():
        """White text used on the overlay for status labels."""
        _ensure_imports()
        return _AppKit.NSColor.whiteColor()


# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------

class Typography:
    """Static methods returning NSFont instances for consistent text styling."""

    @staticmethod
    def overlay_duration():
        """Monospaced bold 14pt font for the recording duration counter."""
        _ensure_imports()
        return _AppKit.NSFont.monospacedDigitSystemFontOfSize_weight_(
            14, _AppKit.NSFontWeightBold
        )

    @staticmethod
    def body():
        """System 13pt font for general body text."""
        _ensure_imports()
        return _AppKit.NSFont.systemFontOfSize_(13)

    @staticmethod
    def caption():
        """System 11pt font for captions and secondary descriptions."""
        _ensure_imports()
        return _AppKit.NSFont.systemFontOfSize_(11)

    @staticmethod
    def section_header():
        """Bold 10pt font for section headers in settings."""
        _ensure_imports()
        return _AppKit.NSFont.boldSystemFontOfSize_(10)

    @staticmethod
    def row_label():
        """System 12pt font for row labels in settings."""
        _ensure_imports()
        return _AppKit.NSFont.systemFontOfSize_(12)

    @staticmethod
    def input_field():
        """System 12pt font for text input fields."""
        _ensure_imports()
        return _AppKit.NSFont.systemFontOfSize_(12)

    @staticmethod
    def about_title():
        """Bold 20pt font for the app name in the About tab."""
        _ensure_imports()
        return _AppKit.NSFont.boldSystemFontOfSize_(20)

    @staticmethod
    def about_version():
        """System 11pt font for the version string in the About tab."""
        _ensure_imports()
        return _AppKit.NSFont.systemFontOfSize_(11)

    @staticmethod
    def button():
        """System 11pt font for button labels."""
        _ensure_imports()
        return _AppKit.NSFont.systemFontOfSize_(11)

    @staticmethod
    def note():
        """System 10pt font for fine-print notes and footnotes."""
        _ensure_imports()
        return _AppKit.NSFont.systemFontOfSize_(10)


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

class Dimensions:
    """Layout and sizing constants shared across overlay and settings window."""

    # -- Overlay --------------------------------------------------------------
    # Overall pill shape
    OVERLAY_WIDTH = 200
    OVERLAY_HEIGHT = 40
    OVERLAY_CORNER_RADIUS = 20
    # Waveform / level indicator bars
    OVERLAY_WAVE_SIZE = 24
    OVERLAY_WAVE_X = 16
    OVERLAY_WAVE_GAP = 9
    OVERLAY_BAR_HEIGHT = 3.5
    OVERLAY_BAR_MARGIN = 18
    # Vertical position as a fraction of screen height from the bottom
    OVERLAY_VERTICAL_POSITION = 0.22

    # -- Settings window ------------------------------------------------------
    SETTINGS_WIDTH = 560
    SETTINGS_HEIGHT = 650
    SETTINGS_CORNER_RADIUS = 12
    SETTINGS_TAB_MARGIN = 12
    SETTINGS_BAR_H = 52

    # Settings scroll content dimensions
    SETTINGS_CONTENT_W = 516
    SETTINGS_CONTENT_H = 560
    SETTINGS_GRAMMAR_DOC_H = 880

    # Settings layout grid
    SETTINGS_LEFT_MARGIN = 20
    SETTINGS_LABEL_W = 155
    SETTINGS_FIELD_X = 185
    SETTINGS_FIELD_W = 311
    SETTINGS_ROW_H = 22
    SETTINGS_ROW_GAP = 8
    SETTINGS_SECTION_GAP = 20

    # -- Glass effect ---------------------------------------------------------
    GLASS_BORDER_WIDTH = 0.5
    GLASS_SHADOW_BLUR = 20
    GLASS_SHADOW_OFFSET = (0, -2)
    GLASS_SHADOW_ALPHA = 0.15

    # -- Buttons --------------------------------------------------------------
    BUTTON_WIDTH = 80
    BUTTON_HEIGHT = 28
    BUTTON_MARGIN = 16
    BUTTON_GAP = 8


# ---------------------------------------------------------------------------
# Glass-effect helpers
# ---------------------------------------------------------------------------

def create_glass_background(frame, corner_radius=None, material=None):
    """
    Create an NSVisualEffectView with a frosted-glass HUD appearance.

    Uses HUDWindow material (13) by default, behindWindow blending, and
    active state. Applies a continuous corner curve and clips to bounds.
    Returns the configured NSVisualEffectView.
    """
    _ensure_imports()
    radius = corner_radius if corner_radius is not None else Dimensions.OVERLAY_CORNER_RADIUS
    mat = material if material is not None else 13  # NSVisualEffectMaterialHUDWindow

    view = _AppKit.NSVisualEffectView.alloc().initWithFrame_(frame)
    view.setMaterial_(mat)
    view.setBlendingMode_(1)   # NSVisualEffectBlendingModeBehindWindow
    view.setState_(1)          # NSVisualEffectStateActive
    view.setWantsLayer_(True)
    apply_continuous_corners(view, radius)
    view.layer().setMasksToBounds_(True)
    return view


def apply_glass_border(view, width=None):
    """
    Add a thin white border at 15% alpha to a view's CALayer.

    Draws a 0.5px (default) border that gives glass panels a subtle edge.
    Silently skips on older macOS where CGColorCreateGenericRGB is absent.
    """
    _ensure_imports()
    border_width = width if width is not None else Dimensions.GLASS_BORDER_WIDTH
    try:
        view.setWantsLayer_(True)
        border_color = _Quartz.CGColorCreateGenericRGB(1.0, 1.0, 1.0, 0.15)
        view.layer().setBorderColor_(border_color)
        view.layer().setBorderWidth_(border_width)
    except Exception:
        pass


def apply_shadow(window):
    """
    Enable the window drop shadow and configure its CALayer shadow properties.

    Sets hasShadow to True then applies opacity, blur radius, offset, and
    color to the window's backing layer. Silently degrades on older macOS.
    """
    _ensure_imports()
    try:
        window.setHasShadow_(True)
        layer = window.contentView().layer()
        if layer is not None:
            layer.setShadowOpacity_(Dimensions.GLASS_SHADOW_ALPHA)
            layer.setShadowRadius_(Dimensions.GLASS_SHADOW_BLUR)
            ox, oy = Dimensions.GLASS_SHADOW_OFFSET
            layer.setShadowOffset_(_Foundation.NSMakeSize(ox, oy))
            shadow_color = _Quartz.CGColorCreateGenericRGB(0.0, 0.0, 0.0, 1.0)
            layer.setShadowColor_(shadow_color)
    except Exception:
        pass


def apply_continuous_corners(view, radius):
    """
    Apply a continuous (squircle-style) corner curve to a view's CALayer.

    Falls back gracefully on macOS versions that do not expose
    kCACornerCurveContinuous (pre-Catalina).
    """
    _ensure_imports()
    try:
        view.setWantsLayer_(True)
        view.layer().setCornerRadius_(radius)
        # kCACornerCurveContinuous = 'continuous'
        view.layer().setCornerCurve_("continuous")
    except Exception:
        pass

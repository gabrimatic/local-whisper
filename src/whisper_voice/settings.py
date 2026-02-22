"""
Settings window for Local Whisper.

Comprehensive NSPanel covering every configurable option across 5 tabs:
Recording, Transcription, Grammar, Interface, Advanced.
"""

import queue
import subprocess
import threading
from typing import Optional, Callable

from .config import get_config, update_config_field
from .utils import log

# Lazily imported macOS frameworks
_AppKit = None
_Foundation = None
_Performer = None
_callback_queue = queue.Queue(maxsize=100)

# Hotkey options: (display_label, config_value)
_HOTKEY_OPTIONS = [
    ("Right Option (alt_r)", "alt_r"),
    ("Left Option (alt_l)", "alt_l"),
    ("Right Control (ctrl_r)", "ctrl_r"),
    ("Left Control (ctrl_l)", "ctrl_l"),
    ("Right Command (cmd_r)", "cmd_r"),
    ("Left Command (cmd_l)", "cmd_l"),
    ("Right Shift (shift_r)", "shift_r"),
    ("Left Shift (shift_l)", "shift_l"),
    ("Caps Lock (caps_lock)", "caps_lock"),
    ("F1", "f1"), ("F2", "f2"), ("F3", "f3"), ("F4", "f4"),
    ("F5", "f5"), ("F6", "f6"), ("F7", "f7"), ("F8", "f8"),
    ("F9", "f9"), ("F10", "f10"), ("F11", "f11"), ("F12", "f12"),
]

# Language options: (display_label, config_value)
_LANGUAGE_OPTIONS = [
    ("Auto-detect", "auto"),
    ("English (en)", "en"),
    ("Persian (fa)", "fa"),
    ("Spanish (es)", "es"),
    ("French (fr)", "fr"),
    ("German (de)", "de"),
    ("Arabic (ar)", "ar"),
    ("Chinese (zh)", "zh"),
    ("Japanese (ja)", "ja"),
    ("Korean (ko)", "ko"),
    ("Italian (it)", "it"),
    ("Portuguese (pt)", "pt"),
    ("Russian (ru)", "ru"),
]

# Fields that require a service restart to take effect
_RESTART_REQUIRED_FIELDS = {
    ("hotkey", "key"),
    ("hotkey", "double_tap_threshold"),
    ("whisper", "model"),
    ("whisper", "url"),
    ("whisper", "check_url"),
    ("shortcuts", "enabled"),
    ("shortcuts", "proofread"),
    ("shortcuts", "rewrite"),
    ("shortcuts", "prompt_engineer"),
}


def _import_macos():
    """Lazily import macOS frameworks and create Performer class."""
    global _AppKit, _Foundation, _Performer
    if _AppKit is None:
        import AppKit as _AppKit
        import Foundation as _Foundation

        class _PerformerClass(_Foundation.NSObject):
            def perform_(self, _):
                try:
                    while True:
                        func = _callback_queue.get_nowait()
                        try:
                            func()
                        except Exception as e:
                            log(f"Settings callback error: {e}", "WARN")
                except queue.Empty:
                    pass

        _Performer = _PerformerClass


def _perform_on_main_thread(func: Callable, wait: bool = False):
    """Execute a function on the main thread."""
    _import_macos()
    try:
        _callback_queue.put_nowait(func)
    except queue.Full:
        return
    performer = _Performer.alloc().init()
    performer.performSelectorOnMainThread_withObject_waitUntilDone_(
        _Foundation.NSSelectorFromString("perform:"),
        None,
        wait,
    )


def _make_button_delegate_class():
    """Create the NSObject subclass for button callbacks after AppKit is loaded."""
    _import_macos()

    class _ButtonDelegateImpl(_Foundation.NSObject):
        def initWithCallback_(self, cb):
            self = super().init()
            if self is None:
                return None
            self._cb = cb
            return self

        def clicked_(self, sender):
            if self._cb:
                self._cb(sender)

    return _ButtonDelegateImpl


def _make_slider_delegate_class():
    """Create the NSObject subclass for slider change callbacks."""
    _import_macos()

    class _SliderDelegateImpl(_Foundation.NSObject):
        def initWithCallback_(self, cb):
            self = super().init()
            if self is None:
                return None
            self._cb = cb
            return self

        def sliderChanged_(self, sender):
            if self._cb:
                self._cb(sender)

    return _SliderDelegateImpl


class SettingsWindow:
    """
    Floating settings panel covering all configurable options.
    """

    # Window dimensions
    WIDTH = 560
    HEIGHT = 520

    def __init__(self):
        self._panel = None
        self._lock = threading.Lock()
        # Delegates stored to prevent GC
        self._delegates = []
        # Config snapshot taken when window opens, for change detection
        self._snapshot: dict = {}
        # Tracks whether any restart-required field was changed
        self._restart_required_changed = False

        # UI element references - Recording tab
        self._hotkey_popup = None
        self._tap_threshold_slider = None
        self._tap_threshold_label = None
        self._min_duration_field = None
        self._max_duration_field = None
        self._min_rms_slider = None
        self._min_rms_label = None

        # UI element references - Transcription tab
        self._whisper_model_field = None
        self._whisper_language_popup = None
        self._whisper_prompt_view = None
        self._whisper_timeout_field = None

        # UI element references - Grammar tab
        self._grammar_enabled_checkbox = None
        self._ollama_model_field = None
        self._ollama_url_field = None
        self._ollama_keep_alive_field = None
        self._ollama_max_chars_field = None
        self._ollama_timeout_field = None
        self._ollama_unload_checkbox = None
        self._ollama_model_popup = None
        self._ollama_status_label = None
        self._ai_max_chars_field = None
        self._ai_timeout_field = None
        self._lm_model_field = None
        self._lm_url_field = None
        self._lm_max_chars_field = None
        self._lm_max_tokens_field = None
        self._lm_timeout_field = None
        self._shortcuts_enabled_checkbox = None
        self._shortcuts_proofread_field = None
        self._shortcuts_rewrite_field = None
        self._shortcuts_prompt_field = None

        # UI element references - Interface tab
        self._show_overlay_checkbox = None
        self._overlay_opacity_slider = None
        self._overlay_opacity_label = None
        self._sounds_checkbox = None

        # UI element references - Advanced tab
        self._backup_dir_field = None
        self._whisper_url_field = None
        self._whisper_check_url_field = None

        # Bottom bar
        self._restart_label = None

        self._ButtonDelegate = None
        self._SliderDelegate = None

    # ------------------------------------------------------------------ #
    # Layout helpers                                                       #
    # ------------------------------------------------------------------ #

    def _make_label(self, text: str, frame, small: bool = False, bold: bool = False,
                    secondary: bool = False):
        """Create a non-editable text label."""
        _import_macos()
        label = _AppKit.NSTextField.alloc().initWithFrame_(frame)
        label.setStringValue_(text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        size = 11 if small else 12
        if bold:
            label.setFont_(_AppKit.NSFont.boldSystemFontOfSize_(size))
        else:
            label.setFont_(_AppKit.NSFont.systemFontOfSize_(size))
        if secondary:
            label.setTextColor_(_AppKit.NSColor.secondaryLabelColor())
        return label

    def _make_text_field(self, value: str, frame, enabled: bool = True):
        """Create an editable (or read-only) NSTextField."""
        _import_macos()
        field = _AppKit.NSTextField.alloc().initWithFrame_(frame)
        field.setStringValue_(value)
        field.setBezeled_(True)
        field.setBezelStyle_(_AppKit.NSTextFieldRoundedBezel)
        field.setDrawsBackground_(True)
        field.setEditable_(enabled)
        field.setSelectable_(True)
        field.setFont_(_AppKit.NSFont.systemFontOfSize_(12))
        if not enabled:
            field.setTextColor_(_AppKit.NSColor.secondaryLabelColor())
        return field

    def _make_checkbox(self, title: str, state: bool, frame):
        """Create an NSButton checkbox."""
        _import_macos()
        btn = _AppKit.NSButton.alloc().initWithFrame_(frame)
        btn.setTitle_(title)
        btn.setButtonType_(_AppKit.NSButtonTypeSwitch)
        btn.setState_(_AppKit.NSControlStateValueOn if state else _AppKit.NSControlStateValueOff)
        btn.setFont_(_AppKit.NSFont.systemFontOfSize_(12))
        return btn

    def _make_slider(self, value: float, min_val: float, max_val: float, frame):
        """Create a continuous NSSlider."""
        _import_macos()
        slider = _AppKit.NSSlider.alloc().initWithFrame_(frame)
        slider.setMinValue_(min_val)
        slider.setMaxValue_(max_val)
        slider.setFloatValue_(value)
        slider.setContinuous_(True)
        return slider

    def _make_popup(self, options: list, selected_value: str, frame):
        """Create an NSPopUpButton from a list of (label, value) tuples."""
        _import_macos()
        popup = _AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(frame, False)
        for label, _ in options:
            popup.addItemWithTitle_(label)
        # Select the matching option
        for i, (_, val) in enumerate(options):
            if val == selected_value:
                popup.selectItemAtIndex_(i)
                break
        popup.setFont_(_AppKit.NSFont.systemFontOfSize_(12))
        return popup

    def _make_section_header(self, text: str, frame):
        """Create a bold section header label."""
        return self._make_label(text, frame, bold=True)

    def _make_separator(self, x: float, y: float, width: float):
        """Create a thin horizontal NSBox separator."""
        _import_macos()
        sep = _AppKit.NSBox.alloc().initWithFrame_(
            _Foundation.NSMakeRect(x, y, width, 1)
        )
        sep.setBoxType_(_AppKit.NSBoxSeparator)
        return sep

    def _connect_slider(self, slider, callback):
        """Attach a callback to a slider's action."""
        _import_macos()
        delegate = self._SliderDelegate.alloc().initWithCallback_(callback)
        self._delegates.append(delegate)
        slider.setTarget_(delegate)
        slider.setAction_(_Foundation.NSSelectorFromString("sliderChanged:"))

    def _connect_button(self, btn, callback):
        """Attach a callback to a button's action."""
        _import_macos()
        delegate = self._ButtonDelegate.alloc().initWithCallback_(callback)
        self._delegates.append(delegate)
        btn.setTarget_(delegate)
        btn.setAction_(_Foundation.NSSelectorFromString("clicked:"))

    # ------------------------------------------------------------------ #
    # Window creation                                                      #
    # ------------------------------------------------------------------ #

    def _create_window(self):
        """Create the settings panel. Must run on main thread."""
        _import_macos()
        self._ButtonDelegate = _make_button_delegate_class()
        self._SliderDelegate = _make_slider_delegate_class()

        W, H = self.WIDTH, self.HEIGHT

        screen = _AppKit.NSScreen.mainScreen()
        sf = screen.frame()
        x = (sf.size.width - W) / 2
        y = (sf.size.height - H) / 2

        style = (
            _AppKit.NSWindowStyleMaskTitled
            | _AppKit.NSWindowStyleMaskClosable
            | _AppKit.NSWindowStyleMaskMiniaturizable
        )

        self._panel = _AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            _Foundation.NSMakeRect(x, y, W, H),
            style,
            _AppKit.NSBackingStoreBuffered,
            False,
        )
        self._panel.setTitle_("Local Whisper \u2014 Settings")
        self._panel.setLevel_(_AppKit.NSFloatingWindowLevel)
        self._panel.setReleasedWhenClosed_(False)

        content = self._panel.contentView()

        # Bottom bar height
        bar_h = 48

        # Tab view
        tab_margin = 12
        tab_view = _AppKit.NSTabView.alloc().initWithFrame_(
            _Foundation.NSMakeRect(tab_margin, bar_h, W - tab_margin * 2, H - bar_h - 8)
        )
        content.addSubview_(tab_view)

        # Build tabs
        tabs = [
            ("recording", "Recording", self._build_recording_tab),
            ("transcription", "Transcription", self._build_transcription_tab),
            ("grammar", "Grammar", self._build_grammar_tab),
            ("interface", "Interface", self._build_interface_tab),
            ("advanced", "Advanced", self._build_advanced_tab),
        ]
        for ident, label, builder in tabs:
            item = _AppKit.NSTabViewItem.alloc().initWithIdentifier_(ident)
            item.setLabel_(label)
            tab_view.addTabViewItem_(item)
            builder(item.view())

        # Bottom bar elements
        margin = 16
        btn_w = 80
        btn_h = 28

        # Restart-required warning label
        self._restart_label = self._make_label(
            "\u26a0 Some changes require restart",
            _Foundation.NSMakeRect(margin, (bar_h - 16) / 2, 260, 16),
            small=True,
        )
        self._restart_label.setTextColor_(
            _AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.9, 0.5, 0.1, 1.0)
        )
        self._restart_label.setHidden_(True)
        content.addSubview_(self._restart_label)

        # Cancel button
        cancel_btn = _AppKit.NSButton.alloc().initWithFrame_(
            _Foundation.NSMakeRect(W - margin - btn_w * 2 - 8, (bar_h - btn_h) / 2, btn_w, btn_h)
        )
        cancel_btn.setTitle_("Cancel")
        cancel_btn.setBezelStyle_(_AppKit.NSBezelStyleRounded)
        cancel_btn.setButtonType_(_AppKit.NSButtonTypeMomentaryPushIn)
        cancel_btn.setKeyEquivalent_("\x1b")
        self._connect_button(cancel_btn, lambda _: self._cancel())
        content.addSubview_(cancel_btn)

        # Save button
        save_btn = _AppKit.NSButton.alloc().initWithFrame_(
            _Foundation.NSMakeRect(W - margin - btn_w, (bar_h - btn_h) / 2, btn_w, btn_h)
        )
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(_AppKit.NSBezelStyleRounded)
        save_btn.setButtonType_(_AppKit.NSButtonTypeMomentaryPushIn)
        save_btn.setKeyEquivalent_("\r")
        self._connect_button(save_btn, self._on_save)
        content.addSubview_(save_btn)

    # ------------------------------------------------------------------ #
    # Tab builders                                                         #
    # ------------------------------------------------------------------ #

    # Each builder receives the tab's view (NSView). AppKit uses bottom-left
    # origin, so we track y starting near the top and subtract row heights.

    def _tab_layout(self, tab_view):
        """Return (tab_width, label_width, field_x, field_width, row_h, row_gap, y_start)."""
        # tab_view.frame() gives us the view bounds including tab chrome
        tab_w = tab_view.frame().size.width
        tab_h = tab_view.frame().size.height

        label_w = 170
        field_x = label_w + 12
        field_w = tab_w - field_x - 16
        row_h = 22
        row_gap = 10
        y_start = int(tab_h) - 20
        return tab_w, label_w, field_x, field_w, row_h, row_gap, y_start

    def _add_row(self, view, y, label_w, field_x, field_w, row_h,
                 label_text, widget, note_text=None):
        """Add a label + widget row to view, return new y (decremented)."""
        lbl = self._make_label(
            label_text,
            _Foundation.NSMakeRect(12, y, label_w, row_h),
        )
        view.addSubview_(lbl)
        view.addSubview_(widget)
        if note_text:
            note = self._make_label(
                note_text,
                _Foundation.NSMakeRect(field_x, y - 14, field_w, 14),
                small=True, secondary=True,
            )
            view.addSubview_(note)
            return y - row_h - 18
        return y - row_h - 10

    # -- Tab 1: Recording ------------------------------------------------

    def _build_recording_tab(self, view):
        config = get_config()
        tab_w, lbl_w, field_x, field_w, row_h, row_gap, y = self._tab_layout(view)

        # Section: Hotkey
        header = self._make_section_header("Hotkey", _Foundation.NSMakeRect(12, y, tab_w - 24, row_h))
        view.addSubview_(header)
        y -= row_h + 4

        sep = self._make_separator(12, y, tab_w - 24)
        view.addSubview_(sep)
        y -= 8

        # Trigger key popup
        self._hotkey_popup = self._make_popup(
            _HOTKEY_OPTIONS,
            config.hotkey.key,
            _Foundation.NSMakeRect(field_x, y - 2, field_w, row_h + 4),
        )
        self._connect_button(self._hotkey_popup, self._on_restart_required_change)
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Trigger key", self._hotkey_popup)

        # Double-tap threshold slider
        threshold = config.hotkey.double_tap_threshold
        slider_w = field_w - 48
        self._tap_threshold_slider = self._make_slider(
            threshold, 0.1, 1.0,
            _Foundation.NSMakeRect(field_x, y, slider_w, row_h),
        )
        self._tap_threshold_label = self._make_label(
            f"{threshold:.2f}s",
            _Foundation.NSMakeRect(field_x + slider_w + 6, y, 40, row_h),
        )

        def _tap_changed(sender):
            val = round(sender.floatValue() / 0.05) * 0.05
            self._tap_threshold_label.setStringValue_(f"{val:.2f}s")
            self._on_restart_required_change(sender)

        self._connect_slider(self._tap_threshold_slider, _tap_changed)
        view.addSubview_(self._tap_threshold_slider)
        view.addSubview_(self._tap_threshold_label)
        lbl = self._make_label("Double-tap window", _Foundation.NSMakeRect(12, y, lbl_w, row_h))
        view.addSubview_(lbl)
        y -= row_h + row_gap

        note = self._make_label(
            "Restart required to apply hotkey changes",
            _Foundation.NSMakeRect(field_x, y, field_w, 14),
            small=True, secondary=True,
        )
        view.addSubview_(note)
        y -= 20

        # Section: Audio
        y -= 4
        header2 = self._make_section_header("Audio", _Foundation.NSMakeRect(12, y, tab_w - 24, row_h))
        view.addSubview_(header2)
        y -= row_h + 4

        sep2 = self._make_separator(12, y, tab_w - 24)
        view.addSubview_(sep2)
        y -= 8

        # Min duration
        self._min_duration_field = self._make_text_field(
            str(config.audio.min_duration),
            _Foundation.NSMakeRect(field_x, y, 80, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Min recording duration (s)", self._min_duration_field)

        # Max duration
        self._max_duration_field = self._make_text_field(
            str(config.audio.max_duration),
            _Foundation.NSMakeRect(field_x, y, 80, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Max recording duration (s)", self._max_duration_field)

        # Min RMS slider
        rms = config.audio.min_rms
        rms_slider_w = field_w - 60
        self._min_rms_slider = self._make_slider(
            rms, 0.0, 0.05,
            _Foundation.NSMakeRect(field_x, y, rms_slider_w, row_h),
        )
        self._min_rms_label = self._make_label(
            f"{rms:.4f}",
            _Foundation.NSMakeRect(field_x + rms_slider_w + 6, y, 52, row_h),
        )

        def _rms_changed(sender):
            self._min_rms_label.setStringValue_(f"{sender.floatValue():.4f}")

        self._connect_slider(self._min_rms_slider, _rms_changed)
        view.addSubview_(self._min_rms_slider)
        view.addSubview_(self._min_rms_label)
        lbl3 = self._make_label("Min silence RMS", _Foundation.NSMakeRect(12, y, lbl_w, row_h))
        view.addSubview_(lbl3)
        y -= row_h + row_gap

        note2 = self._make_label(
            "0 = disabled / unlimited for duration fields",
            _Foundation.NSMakeRect(field_x, y, field_w, 14),
            small=True, secondary=True,
        )
        view.addSubview_(note2)

    # -- Tab 2: Transcription -------------------------------------------

    def _build_transcription_tab(self, view):
        config = get_config()
        tab_w, lbl_w, field_x, field_w, row_h, row_gap, y = self._tab_layout(view)

        # Section header
        header = self._make_section_header("WhisperKit", _Foundation.NSMakeRect(12, y, tab_w - 24, row_h))
        view.addSubview_(header)
        y -= row_h + 4

        sep = self._make_separator(12, y, tab_w - 24)
        view.addSubview_(sep)
        y -= 8

        # Whisper model
        self._whisper_model_field = self._make_text_field(
            config.whisper.model,
            _Foundation.NSMakeRect(field_x, y, field_w, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Model", self._whisper_model_field,
                          note_text="Restart required")

        # Language popup
        self._whisper_language_popup = self._make_popup(
            _LANGUAGE_OPTIONS,
            config.whisper.language,
            _Foundation.NSMakeRect(field_x, y - 2, field_w, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Language", self._whisper_language_popup)

        # Prompt (multi-line)
        prompt_h = 60
        lbl_prompt = self._make_label("Vocabulary hint (prompt)", _Foundation.NSMakeRect(12, y + prompt_h - row_h, lbl_w, row_h))
        view.addSubview_(lbl_prompt)

        scroll = _AppKit.NSScrollView.alloc().initWithFrame_(
            _Foundation.NSMakeRect(field_x, y, field_w, prompt_h)
        )
        scroll.setBorderType_(_AppKit.NSBezelBorder)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)

        self._whisper_prompt_view = _AppKit.NSTextView.alloc().initWithFrame_(
            _Foundation.NSMakeRect(0, 0, field_w, prompt_h)
        )
        self._whisper_prompt_view.setString_(config.whisper.prompt or "")
        self._whisper_prompt_view.setFont_(_AppKit.NSFont.systemFontOfSize_(12))
        self._whisper_prompt_view.setAutomaticSpellingCorrectionEnabled_(False)
        self._whisper_prompt_view.setAutomaticTextReplacementEnabled_(False)
        scroll.setDocumentView_(self._whisper_prompt_view)
        view.addSubview_(scroll)

        y -= prompt_h + 4

        warning = self._make_label(
            "For technical terms only (names, jargon). Conversational text causes truncated results.",
            _Foundation.NSMakeRect(field_x, y, field_w, 28),
            small=True, secondary=True,
        )
        warning.setWraps_(True)
        view.addSubview_(warning)
        y -= 32

        # Timeout
        self._whisper_timeout_field = self._make_text_field(
            str(config.whisper.timeout),
            _Foundation.NSMakeRect(field_x, y, 80, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Timeout (s, 0 = auto)", self._whisper_timeout_field)

    # -- Tab 3: Grammar -------------------------------------------------

    def _build_grammar_tab(self, view):
        config = get_config()
        tab_w, lbl_w, field_x, field_w, row_h, row_gap, y = self._tab_layout(view)

        # Grammar enabled toggle
        self._grammar_enabled_checkbox = self._make_checkbox(
            "Enable grammar correction",
            config.grammar.enabled,
            _Foundation.NSMakeRect(12, y, tab_w - 24, row_h),
        )
        view.addSubview_(self._grammar_enabled_checkbox)
        y -= row_h + 12

        sep0 = self._make_separator(12, y, tab_w - 24)
        view.addSubview_(sep0)
        y -= 10

        # --- Ollama ---
        hdr_ollama = self._make_section_header("Ollama", _Foundation.NSMakeRect(12, y, tab_w - 24, row_h))
        view.addSubview_(hdr_ollama)
        y -= row_h + 4

        # Model field + fetch button
        btn_w = 70
        self._ollama_model_field = self._make_text_field(
            config.ollama.model,
            _Foundation.NSMakeRect(field_x, y, field_w - btn_w - 6, row_h + 4),
        )
        fetch_btn = _AppKit.NSButton.alloc().initWithFrame_(
            _Foundation.NSMakeRect(field_x + field_w - btn_w, y, btn_w, row_h + 4)
        )
        fetch_btn.setTitle_("Fetch \u25be")
        fetch_btn.setBezelStyle_(_AppKit.NSBezelStyleRounded)
        fetch_btn.setButtonType_(_AppKit.NSButtonTypeMomentaryPushIn)
        fetch_btn.setFont_(_AppKit.NSFont.systemFontOfSize_(11))
        self._connect_button(fetch_btn, self._on_fetch_ollama_models)
        lbl_m = self._make_label("Model", _Foundation.NSMakeRect(12, y, lbl_w, row_h))
        view.addSubview_(lbl_m)
        view.addSubview_(self._ollama_model_field)
        view.addSubview_(fetch_btn)
        y -= row_h + 6

        # Model picker popup (populated after fetch)
        self._ollama_model_popup = _AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(
            _Foundation.NSMakeRect(field_x, y - 2, field_w, row_h + 4), False
        )
        self._ollama_model_popup.addItemWithTitle_("Pick model...")
        self._connect_button(self._ollama_model_popup, self._on_ollama_popup_select)
        lbl_pick = self._make_label("", _Foundation.NSMakeRect(12, y, lbl_w, row_h))
        view.addSubview_(lbl_pick)
        view.addSubview_(self._ollama_model_popup)
        y -= row_h + 4

        # Status label
        self._ollama_status_label = self._make_label(
            "", _Foundation.NSMakeRect(field_x, y, field_w, 14),
            small=True, secondary=True,
        )
        view.addSubview_(self._ollama_status_label)
        y -= 16

        # API URL
        self._ollama_url_field = self._make_text_field(
            config.ollama.url,
            _Foundation.NSMakeRect(field_x, y, field_w, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "API URL", self._ollama_url_field)

        # Keep alive
        self._ollama_keep_alive_field = self._make_text_field(
            config.ollama.keep_alive,
            _Foundation.NSMakeRect(field_x, y, 100, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Keep alive", self._ollama_keep_alive_field)

        # Max chars
        self._ollama_max_chars_field = self._make_text_field(
            str(config.ollama.max_chars),
            _Foundation.NSMakeRect(field_x, y, 80, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Max chars (0 = unlimited)", self._ollama_max_chars_field)

        # Timeout
        self._ollama_timeout_field = self._make_text_field(
            str(config.ollama.timeout),
            _Foundation.NSMakeRect(field_x, y, 80, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Timeout (s)", self._ollama_timeout_field)

        # Unload on exit checkbox
        self._ollama_unload_checkbox = self._make_checkbox(
            "Unload model on exit",
            config.ollama.unload_on_exit,
            _Foundation.NSMakeRect(field_x, y, field_w, row_h),
        )
        view.addSubview_(self._ollama_unload_checkbox)
        y -= row_h + 8

        sep1 = self._make_separator(12, y, tab_w - 24)
        view.addSubview_(sep1)
        y -= 10

        # --- Apple Intelligence ---
        hdr_ai = self._make_section_header("Apple Intelligence", _Foundation.NSMakeRect(12, y, tab_w - 24, row_h))
        view.addSubview_(hdr_ai)
        y -= row_h + 4

        self._ai_max_chars_field = self._make_text_field(
            str(config.apple_intelligence.max_chars),
            _Foundation.NSMakeRect(field_x, y, 80, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Max chars (0 = unlimited)", self._ai_max_chars_field)

        self._ai_timeout_field = self._make_text_field(
            str(config.apple_intelligence.timeout),
            _Foundation.NSMakeRect(field_x, y, 80, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Timeout (s)", self._ai_timeout_field)

        ai_note = self._make_label(
            "Requires macOS 26+, Apple Silicon",
            _Foundation.NSMakeRect(field_x, y, field_w, 14),
            small=True, secondary=True,
        )
        view.addSubview_(ai_note)
        y -= 20

        sep2 = self._make_separator(12, y, tab_w - 24)
        view.addSubview_(sep2)
        y -= 10

        # --- LM Studio ---
        hdr_lm = self._make_section_header("LM Studio", _Foundation.NSMakeRect(12, y, tab_w - 24, row_h))
        view.addSubview_(hdr_lm)
        y -= row_h + 4

        self._lm_model_field = self._make_text_field(
            config.lm_studio.model,
            _Foundation.NSMakeRect(field_x, y, field_w, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Model", self._lm_model_field)

        self._lm_url_field = self._make_text_field(
            config.lm_studio.url,
            _Foundation.NSMakeRect(field_x, y, field_w, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "API URL", self._lm_url_field)

        self._lm_max_chars_field = self._make_text_field(
            str(config.lm_studio.max_chars),
            _Foundation.NSMakeRect(field_x, y, 80, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Max chars (0 = unlimited)", self._lm_max_chars_field)

        self._lm_max_tokens_field = self._make_text_field(
            str(config.lm_studio.max_tokens),
            _Foundation.NSMakeRect(field_x, y, 80, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Max tokens (0 = default)", self._lm_max_tokens_field)

        self._lm_timeout_field = self._make_text_field(
            str(config.lm_studio.timeout),
            _Foundation.NSMakeRect(field_x, y, 80, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Timeout (s)", self._lm_timeout_field)

        sep3 = self._make_separator(12, y, tab_w - 24)
        view.addSubview_(sep3)
        y -= 10

        # --- Shortcuts ---
        hdr_sc = self._make_section_header("Shortcuts", _Foundation.NSMakeRect(12, y, tab_w - 24, row_h))
        view.addSubview_(hdr_sc)
        y -= row_h + 4

        self._shortcuts_enabled_checkbox = self._make_checkbox(
            "Enable shortcuts",
            config.shortcuts.enabled,
            _Foundation.NSMakeRect(field_x, y, field_w, row_h),
        )
        self._connect_button(self._shortcuts_enabled_checkbox, self._on_restart_required_change)
        lbl_sc_en = self._make_label("", _Foundation.NSMakeRect(12, y, lbl_w, row_h))
        view.addSubview_(lbl_sc_en)
        view.addSubview_(self._shortcuts_enabled_checkbox)
        y -= row_h + row_gap

        self._shortcuts_proofread_field = self._make_text_field(
            config.shortcuts.proofread,
            _Foundation.NSMakeRect(field_x, y, 140, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Proofread", self._shortcuts_proofread_field)

        self._shortcuts_rewrite_field = self._make_text_field(
            config.shortcuts.rewrite,
            _Foundation.NSMakeRect(field_x, y, 140, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Rewrite", self._shortcuts_rewrite_field)

        self._shortcuts_prompt_field = self._make_text_field(
            config.shortcuts.prompt_engineer,
            _Foundation.NSMakeRect(field_x, y, 140, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Prompt engineer", self._shortcuts_prompt_field)

        sc_note = self._make_label(
            "Shortcut changes require restart",
            _Foundation.NSMakeRect(field_x, y, field_w, 14),
            small=True, secondary=True,
        )
        view.addSubview_(sc_note)

    # -- Tab 4: Interface -----------------------------------------------

    def _build_interface_tab(self, view):
        config = get_config()
        tab_w, lbl_w, field_x, field_w, row_h, row_gap, y = self._tab_layout(view)

        header = self._make_section_header("Overlay", _Foundation.NSMakeRect(12, y, tab_w - 24, row_h))
        view.addSubview_(header)
        y -= row_h + 4

        sep = self._make_separator(12, y, tab_w - 24)
        view.addSubview_(sep)
        y -= 8

        self._show_overlay_checkbox = self._make_checkbox(
            "Show recording overlay",
            config.ui.show_overlay,
            _Foundation.NSMakeRect(field_x, y, field_w, row_h),
        )
        lbl_ov = self._make_label("", _Foundation.NSMakeRect(12, y, lbl_w, row_h))
        view.addSubview_(lbl_ov)
        view.addSubview_(self._show_overlay_checkbox)
        y -= row_h + row_gap

        # Opacity slider
        opacity = config.ui.overlay_opacity
        op_slider_w = field_w - 52
        self._overlay_opacity_slider = self._make_slider(
            opacity, 0.1, 1.0,
            _Foundation.NSMakeRect(field_x, y, op_slider_w, row_h),
        )
        self._overlay_opacity_label = self._make_label(
            f"{opacity:.2f}",
            _Foundation.NSMakeRect(field_x + op_slider_w + 6, y, 44, row_h),
        )

        def _opacity_changed(sender):
            self._overlay_opacity_label.setStringValue_(f"{sender.floatValue():.2f}")

        self._connect_slider(self._overlay_opacity_slider, _opacity_changed)
        view.addSubview_(self._overlay_opacity_slider)
        view.addSubview_(self._overlay_opacity_label)
        lbl_op = self._make_label("Overlay opacity", _Foundation.NSMakeRect(12, y, lbl_w, row_h))
        view.addSubview_(lbl_op)
        y -= row_h + 4

        op_note = self._make_label(
            "Takes effect after restart",
            _Foundation.NSMakeRect(field_x, y, field_w, 14),
            small=True, secondary=True,
        )
        view.addSubview_(op_note)
        y -= 22

        sep2 = self._make_separator(12, y, tab_w - 24)
        view.addSubview_(sep2)
        y -= 10

        header2 = self._make_section_header("Feedback", _Foundation.NSMakeRect(12, y, tab_w - 24, row_h))
        view.addSubview_(header2)
        y -= row_h + 4

        sep3 = self._make_separator(12, y, tab_w - 24)
        view.addSubview_(sep3)
        y -= 8

        self._sounds_checkbox = self._make_checkbox(
            "Sounds enabled",
            config.ui.sounds_enabled,
            _Foundation.NSMakeRect(field_x, y, field_w, row_h),
        )
        lbl_snd = self._make_label("", _Foundation.NSMakeRect(12, y, lbl_w, row_h))
        view.addSubview_(lbl_snd)
        view.addSubview_(self._sounds_checkbox)
        y -= row_h + row_gap

    # -- Tab 5: Advanced ------------------------------------------------

    def _build_advanced_tab(self, view):
        config = get_config()
        tab_w, lbl_w, field_x, field_w, row_h, row_gap, y = self._tab_layout(view)

        header = self._make_section_header("Storage", _Foundation.NSMakeRect(12, y, tab_w - 24, row_h))
        view.addSubview_(header)
        y -= row_h + 4

        sep = self._make_separator(12, y, tab_w - 24)
        view.addSubview_(sep)
        y -= 8

        self._backup_dir_field = self._make_text_field(
            config.backup.directory,
            _Foundation.NSMakeRect(field_x, y, field_w, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Backup directory", self._backup_dir_field)

        sep2 = self._make_separator(12, y, tab_w - 24)
        view.addSubview_(sep2)
        y -= 10

        header2 = self._make_section_header("WhisperKit Server", _Foundation.NSMakeRect(12, y, tab_w - 24, row_h))
        view.addSubview_(header2)
        y -= row_h + 4

        sep3 = self._make_separator(12, y, tab_w - 24)
        view.addSubview_(sep3)
        y -= 8

        self._whisper_url_field = self._make_text_field(
            config.whisper.url,
            _Foundation.NSMakeRect(field_x, y, field_w, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "API URL", self._whisper_url_field,
                          note_text="Restart required")

        self._whisper_check_url_field = self._make_text_field(
            config.whisper.check_url,
            _Foundation.NSMakeRect(field_x, y, field_w, row_h + 4),
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Check URL", self._whisper_check_url_field,
                          note_text="Restart required")

        sep4 = self._make_separator(12, y, tab_w - 24)
        view.addSubview_(sep4)
        y -= 10

        header3 = self._make_section_header("Audio Capture", _Foundation.NSMakeRect(12, y, tab_w - 24, row_h))
        view.addSubview_(header3)
        y -= row_h + 4

        sep5 = self._make_separator(12, y, tab_w - 24)
        view.addSubview_(sep5)
        y -= 8

        sample_rate_field = self._make_text_field(
            str(config.audio.sample_rate),
            _Foundation.NSMakeRect(field_x, y, 80, row_h + 4),
            enabled=False,
        )
        y = self._add_row(view, y, lbl_w, field_x, field_w, row_h,
                          "Sample rate (Hz)", sample_rate_field,
                          note_text="Fixed at 16000 Hz for Whisper")

    # ------------------------------------------------------------------ #
    # Callbacks                                                            #
    # ------------------------------------------------------------------ #

    def _on_restart_required_change(self, _sender):
        """Called when any restart-required field changes."""
        if self._restart_label:
            self._restart_label.setHidden_(False)
        self._restart_required_changed = True

    def _on_fetch_ollama_models(self, _sender):
        """Fetch available models from Ollama in a background thread."""
        if self._ollama_status_label:
            _perform_on_main_thread(
                lambda: self._ollama_status_label.setStringValue_("Fetching...")
            )

        def _fetch():
            import urllib.request
            import json
            config = get_config()
            check_url = config.ollama.check_url.rstrip("/")
            tags_url = f"{check_url}/api/tags"
            try:
                with urllib.request.urlopen(tags_url, timeout=5) as resp:
                    data = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
                if models:
                    def _update():
                        if self._ollama_model_popup:
                            self._ollama_model_popup.removeAllItems()
                            self._ollama_model_popup.addItemWithTitle_("Pick model...")
                            for name in models:
                                self._ollama_model_popup.addItemWithTitle_(name)
                            current = config.ollama.model
                            if current in models:
                                self._ollama_model_popup.selectItemWithTitle_(current)
                        if self._ollama_status_label:
                            self._ollama_status_label.setStringValue_(
                                f"{len(models)} model(s) found"
                            )
                    _perform_on_main_thread(_update)
                else:
                    _perform_on_main_thread(
                        lambda: (
                            self._ollama_status_label.setStringValue_("No models found")
                            if self._ollama_status_label else None
                        )
                    )
            except Exception as e:
                log(f"Ollama fetch failed: {e}", "WARN")
                # Capture url for lambda
                url_str = tags_url

                def _show_err():
                    if self._ollama_status_label:
                        self._ollama_status_label.setStringValue_(
                            f"Ollama not reachable at {url_str}"
                        )

                _perform_on_main_thread(_show_err)

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_ollama_popup_select(self, _sender):
        """When user picks a model from the popup, copy to the model field."""
        if self._ollama_model_popup and self._ollama_model_field:
            selected = self._ollama_model_popup.titleOfSelectedItem()
            if selected and selected != "Pick model...":
                self._ollama_model_field.setStringValue_(selected)

    # ------------------------------------------------------------------ #
    # Load / Save                                                          #
    # ------------------------------------------------------------------ #

    def _snapshot_config(self):
        """Take a snapshot of current config values for change detection."""
        config = get_config()
        self._snapshot = {
            ("hotkey", "key"): config.hotkey.key,
            ("hotkey", "double_tap_threshold"): config.hotkey.double_tap_threshold,
            ("whisper", "model"): config.whisper.model,
            ("whisper", "language"): config.whisper.language,
            ("whisper", "prompt"): config.whisper.prompt,
            ("whisper", "timeout"): config.whisper.timeout,
            ("whisper", "url"): config.whisper.url,
            ("whisper", "check_url"): config.whisper.check_url,
            ("grammar", "enabled"): config.grammar.enabled,
            ("ollama", "model"): config.ollama.model,
            ("ollama", "url"): config.ollama.url,
            ("ollama", "keep_alive"): config.ollama.keep_alive,
            ("ollama", "max_chars"): config.ollama.max_chars,
            ("ollama", "timeout"): config.ollama.timeout,
            ("ollama", "unload_on_exit"): config.ollama.unload_on_exit,
            ("apple_intelligence", "max_chars"): config.apple_intelligence.max_chars,
            ("apple_intelligence", "timeout"): config.apple_intelligence.timeout,
            ("lm_studio", "model"): config.lm_studio.model,
            ("lm_studio", "url"): config.lm_studio.url,
            ("lm_studio", "max_chars"): config.lm_studio.max_chars,
            ("lm_studio", "max_tokens"): config.lm_studio.max_tokens,
            ("lm_studio", "timeout"): config.lm_studio.timeout,
            ("audio", "min_duration"): config.audio.min_duration,
            ("audio", "max_duration"): config.audio.max_duration,
            ("audio", "min_rms"): config.audio.min_rms,
            ("ui", "show_overlay"): config.ui.show_overlay,
            ("ui", "overlay_opacity"): config.ui.overlay_opacity,
            ("ui", "sounds_enabled"): config.ui.sounds_enabled,
            ("backup", "directory"): config.backup.directory,
            ("shortcuts", "enabled"): config.shortcuts.enabled,
            ("shortcuts", "proofread"): config.shortcuts.proofread,
            ("shortcuts", "rewrite"): config.shortcuts.rewrite,
            ("shortcuts", "prompt_engineer"): config.shortcuts.prompt_engineer,
        }

    def _load_values(self):
        """Reload current config values into all UI fields."""
        if _AppKit is None:
            _import_macos()
        config = get_config()
        self._snapshot_config()
        self._restart_required_changed = False
        if self._restart_label:
            self._restart_label.setHidden_(True)

        # Recording tab
        if self._hotkey_popup:
            for i, (_, val) in enumerate(_HOTKEY_OPTIONS):
                if val == config.hotkey.key:
                    self._hotkey_popup.selectItemAtIndex_(i)
                    break
        if self._tap_threshold_slider:
            self._tap_threshold_slider.setFloatValue_(config.hotkey.double_tap_threshold)
        if self._tap_threshold_label:
            self._tap_threshold_label.setStringValue_(f"{config.hotkey.double_tap_threshold:.2f}s")
        if self._min_duration_field:
            self._min_duration_field.setStringValue_(str(config.audio.min_duration))
        if self._max_duration_field:
            self._max_duration_field.setStringValue_(str(config.audio.max_duration))
        if self._min_rms_slider:
            self._min_rms_slider.setFloatValue_(config.audio.min_rms)
        if self._min_rms_label:
            self._min_rms_label.setStringValue_(f"{config.audio.min_rms:.4f}")

        # Transcription tab
        if self._whisper_model_field:
            self._whisper_model_field.setStringValue_(config.whisper.model)
        if self._whisper_language_popup:
            for i, (_, val) in enumerate(_LANGUAGE_OPTIONS):
                if val == config.whisper.language:
                    self._whisper_language_popup.selectItemAtIndex_(i)
                    break
        if self._whisper_prompt_view:
            self._whisper_prompt_view.setString_(config.whisper.prompt or "")
        if self._whisper_timeout_field:
            self._whisper_timeout_field.setStringValue_(str(config.whisper.timeout))

        # Grammar tab
        if self._grammar_enabled_checkbox:
            state = _AppKit.NSControlStateValueOn if config.grammar.enabled else _AppKit.NSControlStateValueOff
            self._grammar_enabled_checkbox.setState_(state)
        if self._ollama_model_field:
            self._ollama_model_field.setStringValue_(config.ollama.model)
        if self._ollama_url_field:
            self._ollama_url_field.setStringValue_(config.ollama.url)
        if self._ollama_keep_alive_field:
            self._ollama_keep_alive_field.setStringValue_(config.ollama.keep_alive)
        if self._ollama_max_chars_field:
            self._ollama_max_chars_field.setStringValue_(str(config.ollama.max_chars))
        if self._ollama_timeout_field:
            self._ollama_timeout_field.setStringValue_(str(config.ollama.timeout))
        if self._ollama_unload_checkbox:
            state = _AppKit.NSControlStateValueOn if config.ollama.unload_on_exit else _AppKit.NSControlStateValueOff
            self._ollama_unload_checkbox.setState_(state)
        if self._ai_max_chars_field:
            self._ai_max_chars_field.setStringValue_(str(config.apple_intelligence.max_chars))
        if self._ai_timeout_field:
            self._ai_timeout_field.setStringValue_(str(config.apple_intelligence.timeout))
        if self._lm_model_field:
            self._lm_model_field.setStringValue_(config.lm_studio.model)
        if self._lm_url_field:
            self._lm_url_field.setStringValue_(config.lm_studio.url)
        if self._lm_max_chars_field:
            self._lm_max_chars_field.setStringValue_(str(config.lm_studio.max_chars))
        if self._lm_max_tokens_field:
            self._lm_max_tokens_field.setStringValue_(str(config.lm_studio.max_tokens))
        if self._lm_timeout_field:
            self._lm_timeout_field.setStringValue_(str(config.lm_studio.timeout))
        if self._shortcuts_enabled_checkbox:
            state = _AppKit.NSControlStateValueOn if config.shortcuts.enabled else _AppKit.NSControlStateValueOff
            self._shortcuts_enabled_checkbox.setState_(state)
        if self._shortcuts_proofread_field:
            self._shortcuts_proofread_field.setStringValue_(config.shortcuts.proofread)
        if self._shortcuts_rewrite_field:
            self._shortcuts_rewrite_field.setStringValue_(config.shortcuts.rewrite)
        if self._shortcuts_prompt_field:
            self._shortcuts_prompt_field.setStringValue_(config.shortcuts.prompt_engineer)

        # Interface tab
        if self._show_overlay_checkbox:
            state = _AppKit.NSControlStateValueOn if config.ui.show_overlay else _AppKit.NSControlStateValueOff
            self._show_overlay_checkbox.setState_(state)
        if self._overlay_opacity_slider:
            self._overlay_opacity_slider.setFloatValue_(config.ui.overlay_opacity)
        if self._overlay_opacity_label:
            self._overlay_opacity_label.setStringValue_(f"{config.ui.overlay_opacity:.2f}")
        if self._sounds_checkbox:
            state = _AppKit.NSControlStateValueOn if config.ui.sounds_enabled else _AppKit.NSControlStateValueOff
            self._sounds_checkbox.setState_(state)

        # Advanced tab
        if self._backup_dir_field:
            self._backup_dir_field.setStringValue_(config.backup.directory)
        if self._whisper_url_field:
            self._whisper_url_field.setStringValue_(config.whisper.url)
        if self._whisper_check_url_field:
            self._whisper_check_url_field.setStringValue_(config.whisper.check_url)

    def _checkbox_bool(self, checkbox) -> bool:
        """Read boolean state from an NSButton checkbox."""
        return checkbox.state() == _AppKit.NSControlStateValueOn

    def _popup_value(self, popup, options: list) -> str:
        """Get the config value for the currently selected popup item."""
        idx = popup.indexOfSelectedItem()
        if 0 <= idx < len(options):
            return options[idx][1]
        return options[0][1]

    def _parse_float(self, text: str, default: float) -> float:
        try:
            return float(text)
        except (ValueError, TypeError):
            return default

    def _parse_int(self, text: str, default: int) -> int:
        try:
            return int(float(text))
        except (ValueError, TypeError):
            return default

    def _on_save(self, _sender):
        """Collect all field values, write changed ones to config, close window."""
        _import_macos()

        # Collect new values
        new_values: dict = {}

        # Recording
        if self._hotkey_popup:
            new_values[("hotkey", "key")] = self._popup_value(self._hotkey_popup, _HOTKEY_OPTIONS)
        if self._tap_threshold_slider:
            raw = self._tap_threshold_slider.floatValue()
            new_values[("hotkey", "double_tap_threshold")] = round(raw / 0.05) * 0.05
        if self._min_duration_field:
            new_values[("audio", "min_duration")] = self._parse_float(
                self._min_duration_field.stringValue(), 0)
        if self._max_duration_field:
            new_values[("audio", "max_duration")] = self._parse_int(
                self._max_duration_field.stringValue(), 0)
        if self._min_rms_slider:
            new_values[("audio", "min_rms")] = round(self._min_rms_slider.floatValue(), 5)

        # Transcription
        if self._whisper_model_field:
            new_values[("whisper", "model")] = self._whisper_model_field.stringValue().strip()
        if self._whisper_language_popup:
            new_values[("whisper", "language")] = self._popup_value(
                self._whisper_language_popup, _LANGUAGE_OPTIONS)
        if self._whisper_prompt_view:
            new_values[("whisper", "prompt")] = self._whisper_prompt_view.string()
        if self._whisper_timeout_field:
            new_values[("whisper", "timeout")] = self._parse_int(
                self._whisper_timeout_field.stringValue(), 0)

        # Grammar
        if self._grammar_enabled_checkbox:
            new_values[("grammar", "enabled")] = self._checkbox_bool(self._grammar_enabled_checkbox)
        if self._ollama_model_field:
            new_values[("ollama", "model")] = self._ollama_model_field.stringValue().strip()
        if self._ollama_url_field:
            new_values[("ollama", "url")] = self._ollama_url_field.stringValue().strip()
        if self._ollama_keep_alive_field:
            new_values[("ollama", "keep_alive")] = self._ollama_keep_alive_field.stringValue().strip()
        if self._ollama_max_chars_field:
            new_values[("ollama", "max_chars")] = self._parse_int(
                self._ollama_max_chars_field.stringValue(), 0)
        if self._ollama_timeout_field:
            new_values[("ollama", "timeout")] = self._parse_int(
                self._ollama_timeout_field.stringValue(), 0)
        if self._ollama_unload_checkbox:
            new_values[("ollama", "unload_on_exit")] = self._checkbox_bool(self._ollama_unload_checkbox)
        if self._ai_max_chars_field:
            new_values[("apple_intelligence", "max_chars")] = self._parse_int(
                self._ai_max_chars_field.stringValue(), 0)
        if self._ai_timeout_field:
            new_values[("apple_intelligence", "timeout")] = self._parse_int(
                self._ai_timeout_field.stringValue(), 0)
        if self._lm_model_field:
            new_values[("lm_studio", "model")] = self._lm_model_field.stringValue().strip()
        if self._lm_url_field:
            new_values[("lm_studio", "url")] = self._lm_url_field.stringValue().strip()
        if self._lm_max_chars_field:
            new_values[("lm_studio", "max_chars")] = self._parse_int(
                self._lm_max_chars_field.stringValue(), 0)
        if self._lm_max_tokens_field:
            new_values[("lm_studio", "max_tokens")] = self._parse_int(
                self._lm_max_tokens_field.stringValue(), 0)
        if self._lm_timeout_field:
            new_values[("lm_studio", "timeout")] = self._parse_int(
                self._lm_timeout_field.stringValue(), 0)
        if self._shortcuts_enabled_checkbox:
            new_values[("shortcuts", "enabled")] = self._checkbox_bool(self._shortcuts_enabled_checkbox)
        if self._shortcuts_proofread_field:
            new_values[("shortcuts", "proofread")] = self._shortcuts_proofread_field.stringValue().strip()
        if self._shortcuts_rewrite_field:
            new_values[("shortcuts", "rewrite")] = self._shortcuts_rewrite_field.stringValue().strip()
        if self._shortcuts_prompt_field:
            new_values[("shortcuts", "prompt_engineer")] = self._shortcuts_prompt_field.stringValue().strip()

        # Interface
        if self._show_overlay_checkbox:
            new_values[("ui", "show_overlay")] = self._checkbox_bool(self._show_overlay_checkbox)
        if self._overlay_opacity_slider:
            new_values[("ui", "overlay_opacity")] = round(self._overlay_opacity_slider.floatValue(), 3)
        if self._sounds_checkbox:
            new_values[("ui", "sounds_enabled")] = self._checkbox_bool(self._sounds_checkbox)

        # Advanced
        if self._backup_dir_field:
            new_values[("backup", "directory")] = self._backup_dir_field.stringValue().strip()
        if self._whisper_url_field:
            new_values[("whisper", "url")] = self._whisper_url_field.stringValue().strip()
        if self._whisper_check_url_field:
            new_values[("whisper", "check_url")] = self._whisper_check_url_field.stringValue().strip()

        # Write only changed fields
        any_changed = False
        restart_fields_changed = False
        failed_fields = []

        for (section, key), new_val in new_values.items():
            old_val = self._snapshot.get((section, key))
            if old_val == new_val:
                continue
            ok = update_config_field(section, key, new_val)
            if ok:
                log(f"Settings: {section}.{key} -> {new_val!r}", "INFO")
                any_changed = True
                if (section, key) in _RESTART_REQUIRED_FIELDS:
                    restart_fields_changed = True
            else:
                failed_fields.append(f"{section}.{key}")

        if failed_fields:
            alert = _AppKit.NSAlert.alloc().init()
            alert.setMessageText_("Save failed")
            alert.setInformativeText_(
                f"Could not write the following fields:\n{', '.join(failed_fields)}"
            )
            alert.addButtonWithTitle_("OK")
            alert.runModal()
            return

        if any_changed:
            log("Settings saved", "OK")

        self._panel.orderOut_(None)

        # Offer restart if needed
        if restart_fields_changed:
            def _offer_restart():
                alert = _AppKit.NSAlert.alloc().init()
                alert.setMessageText_("Restart required")
                alert.setInformativeText_(
                    "Some changes require a restart to take effect. Restart now?"
                )
                alert.addButtonWithTitle_("Restart")
                alert.addButtonWithTitle_("Later")
                resp = alert.runModal()
                # NSAlertFirstButtonReturn = 1000
                if resp == 1000:
                    self._do_restart()
            _perform_on_main_thread(_offer_restart)

    def _do_restart(self):
        """Trigger a service restart via wh restart."""
        import os
        venv_wh = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)
            ))),
            ".venv", "bin", "wh"
        )
        try:
            subprocess.Popen(
                [venv_wh, "restart"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as e:
            log(f"Restart failed: {e}", "WARN")

    def _cancel(self):
        """Close without saving."""
        if self._panel:
            self._panel.orderOut_(None)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def show(self):
        """Show the settings window. Safe to call from any thread."""
        def _show():
            with self._lock:
                if self._panel is None:
                    self._create_window()
            self._load_values()
            self._panel.makeKeyAndOrderFront_(None)

        _perform_on_main_thread(_show, wait=False)


# Global singleton
_settings_window: Optional[SettingsWindow] = None


def get_settings_window() -> SettingsWindow:
    """Get the global settings window instance."""
    global _settings_window
    if _settings_window is None:
        _settings_window = SettingsWindow()
    return _settings_window

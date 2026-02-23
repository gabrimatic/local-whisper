# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Settings window for Local Whisper.

Comprehensive NSPanel covering every configurable option across 6 tabs:
Recording, Transcription, Grammar, Interface, Advanced, About.
"""

import objc
import queue
import subprocess
import threading
from typing import Optional, Callable

from .config import get_config, update_config_field, _is_valid_url
from .utils import log

# Lazily imported macOS frameworks
_AppKit = None
_Foundation = None
_Performer = None
_FlippedViewClass = None  # Defined in _import_macos(); module-level to survive GC
_callback_queue = queue.Queue(maxsize=100)

# Layout constants (based on known tab content dimensions — never queried at runtime)
CONTENT_W = 516    # tab content width
CONTENT_H = 560    # tab content height
GRAMMAR_DOC_H = 880  # grammar scrollable doc height
BAR_H = 52         # bottom button bar height
LEFT_MARGIN = 20
LABEL_W = 155
FIELD_X = 185
FIELD_W = 311      # CONTENT_W - FIELD_X - LEFT_MARGIN
ROW_H = 22
ROW_GAP = 8
SECTION_GAP = 20

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
    ("whisper", "temperature"),
    ("whisper", "compression_ratio_threshold"),
    ("whisper", "no_speech_threshold"),
    ("whisper", "logprob_threshold"),
    ("whisper", "temperature_fallback_count"),
    ("whisper", "prompt_preset"),
    ("ui", "overlay_opacity"),
    ("shortcuts", "enabled"),
    ("shortcuts", "proofread"),
    ("shortcuts", "rewrite"),
    ("shortcuts", "prompt_engineer"),
}

# Prompt preset options: (display_label, config_value)
_PROMPT_PRESET_OPTIONS = [
    ("None", "none"),
    ("Technical", "technical"),
    ("Dictation", "dictation"),
    ("Custom", "custom"),
]

# Preset prompt texts keyed by config value — must match what is sent to WhisperKit
_PROMPT_PRESET_TEXTS = {
    "none": "",
    "technical": (
        "function, variable, API, JSON, HTTP, async, await, "
        "TypeScript, Python, React, Node.js, Git, Docker, Kubernetes"
    ),
    "dictation": (
        "Hello, I'd like to dictate a message. "
        "Please transcribe the following text with proper punctuation and formatting."
    ),
    "custom": "",
}


def _import_macos():
    """Lazily import macOS frameworks and create Performer/FlippedView classes."""
    global _AppKit, _Foundation, _Performer, _FlippedViewClass
    if _AppKit is None:
        import AppKit as _AppKit
        import Foundation as _Foundation

        class _SettingsPerformerClass(_Foundation.NSObject):
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

        _Performer = _SettingsPerformerClass

        # Flipped view: y=0 is TOP, y increases DOWNWARD.
        # Stored as module-level global to survive GC.
        class _SettingsFlippedView(_AppKit.NSView):
            def isFlipped(self):
                return True

        _FlippedViewClass = _SettingsFlippedView


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
            self = objc.super(_ButtonDelegateImpl, self).init()
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
            self = objc.super(_SliderDelegateImpl, self).init()
            if self is None:
                return None
            self._cb = cb
            return self

        def sliderChanged_(self, sender):
            if self._cb:
                self._cb(sender)

    return _SliderDelegateImpl


class SettingsWindow:
    """Floating settings panel covering all configurable options."""

    WIDTH = 560
    HEIGHT = 650

    def __init__(self):
        self._panel = None
        self._lock = threading.Lock()
        self._delegates = []
        self._snapshot: dict = {}
        self._restart_required_changed = False

        # Recording tab
        self._hotkey_popup = None
        self._tap_threshold_slider = None
        self._tap_threshold_label = None
        self._min_duration_field = None
        self._max_duration_field = None
        self._min_rms_slider = None
        self._min_rms_label = None
        self._vad_enabled_checkbox = None
        self._noise_reduction_checkbox = None
        self._normalize_audio_checkbox = None
        self._pre_buffer_field = None

        # Transcription tab
        self._whisper_model_field = None
        self._whisper_language_popup = None
        self._whisper_prompt_view = None
        self._whisper_timeout_field = None
        self._whisper_temperature_field = None
        self._whisper_compression_ratio_field = None
        self._whisper_no_speech_threshold_field = None
        self._whisper_logprob_threshold_field = None
        self._whisper_temperature_fallback_field = None
        self._whisper_prompt_preset_popup = None

        # Grammar tab
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
        self._grammar_scroll_view = None
        self._shortcuts_enabled_checkbox = None
        self._shortcuts_proofread_field = None
        self._shortcuts_rewrite_field = None
        self._shortcuts_prompt_field = None

        # Interface tab
        self._show_overlay_checkbox = None
        self._overlay_opacity_slider = None
        self._overlay_opacity_label = None
        self._sounds_checkbox = None
        self._notifications_checkbox = None

        # Advanced tab
        self._backup_dir_field = None
        self._whisper_url_field = None
        self._whisper_check_url_field = None

        # Bottom bar
        self._restart_label = None

        self._ButtonDelegate = None
        self._SliderDelegate = None

    # ------------------------------------------------------------------ #
    # Low-level layout helpers                                             #
    # ------------------------------------------------------------------ #

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
    # High-level layout helpers (flipped-view aware)                      #
    # ------------------------------------------------------------------ #

    def _add_section_header(self, parent, y: float, text: str) -> float:
        """Uppercase bold 10pt label + thin separator line. Returns y + 28."""
        lbl = _AppKit.NSTextField.alloc().initWithFrame_(
            _Foundation.NSMakeRect(LEFT_MARGIN, y, CONTENT_W - LEFT_MARGIN * 2, 14)
        )
        lbl.setStringValue_(text.upper())
        lbl.setBezeled_(False)
        lbl.setDrawsBackground_(False)
        lbl.setEditable_(False)
        lbl.setSelectable_(False)
        lbl.setFont_(_AppKit.NSFont.boldSystemFontOfSize_(10))
        lbl.setTextColor_(_AppKit.NSColor.secondaryLabelColor())
        parent.addSubview_(lbl)

        sep = _AppKit.NSBox.alloc().initWithFrame_(
            _Foundation.NSMakeRect(LEFT_MARGIN, y + 16, CONTENT_W - LEFT_MARGIN * 2, 1)
        )
        sep.setBoxType_(_AppKit.NSBoxSeparator)
        parent.addSubview_(sep)

        return y + 28

    def _add_row(self, parent, y: float, label_text: str, widget) -> float:
        """Right-aligned label + pre-framed widget. Returns y + ROW_H + ROW_GAP."""
        lbl = _AppKit.NSTextField.alloc().initWithFrame_(
            _Foundation.NSMakeRect(LEFT_MARGIN, y + 2, LABEL_W, ROW_H)
        )
        lbl.setStringValue_(label_text)
        lbl.setBezeled_(False)
        lbl.setDrawsBackground_(False)
        lbl.setEditable_(False)
        lbl.setSelectable_(False)
        lbl.setAlignment_(_AppKit.NSTextAlignmentRight)
        lbl.setFont_(_AppKit.NSFont.systemFontOfSize_(12))
        parent.addSubview_(lbl)
        parent.addSubview_(widget)
        return y + ROW_H + ROW_GAP

    def _add_note(self, parent, y: float, text: str, height: int = 16) -> float:
        """Secondary 10pt note at FIELD_X. Returns y + height + 4."""
        lbl = _AppKit.NSTextField.alloc().initWithFrame_(
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, height)
        )
        lbl.setStringValue_(text)
        lbl.setBezeled_(False)
        lbl.setDrawsBackground_(False)
        lbl.setEditable_(False)
        lbl.setSelectable_(False)
        lbl.setFont_(_AppKit.NSFont.systemFontOfSize_(10))
        lbl.setTextColor_(_AppKit.NSColor.secondaryLabelColor())
        lbl.cell().setWraps_(True)
        parent.addSubview_(lbl)
        return y + height + 4

    def _make_text_field_for_row(self, value, frame, enabled: bool = True):
        """Styled editable (or read-only) NSTextField."""
        field = _AppKit.NSTextField.alloc().initWithFrame_(frame)
        field.setStringValue_(str(value))
        field.setBezeled_(True)
        field.setBezelStyle_(_AppKit.NSTextFieldRoundedBezel)
        field.setDrawsBackground_(True)
        field.setEditable_(enabled)
        field.setSelectable_(True)
        field.setFont_(_AppKit.NSFont.systemFontOfSize_(12))
        if not enabled:
            field.setTextColor_(_AppKit.NSColor.secondaryLabelColor())
        return field

    def _make_checkbox_row(self, parent, y: float, title: str, state: bool):
        """Full-width checkbox at FIELD_X. Returns (button, y + ROW_H + ROW_GAP)."""
        btn = _AppKit.NSButton.alloc().initWithFrame_(
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, ROW_H)
        )
        btn.setTitle_(title)
        btn.setButtonType_(_AppKit.NSButtonTypeSwitch)
        btn.setState_(
            _AppKit.NSControlStateValueOn if state else _AppKit.NSControlStateValueOff
        )
        btn.setFont_(_AppKit.NSFont.systemFontOfSize_(12))
        parent.addSubview_(btn)
        return btn, y + ROW_H + ROW_GAP

    def _make_slider_row(self, parent, y: float, label: str,
                         value: float, min_val: float, max_val: float,
                         fmt, callback):
        """Slider + value label + row label. Returns (slider, val_lbl, new_y)."""
        slider_w = FIELD_W - 52
        slider = _AppKit.NSSlider.alloc().initWithFrame_(
            _Foundation.NSMakeRect(FIELD_X, y + 2, slider_w, ROW_H)
        )
        slider.setMinValue_(min_val)
        slider.setMaxValue_(max_val)
        slider.setFloatValue_(value)
        slider.setContinuous_(True)

        val_lbl = _AppKit.NSTextField.alloc().initWithFrame_(
            _Foundation.NSMakeRect(FIELD_X + slider_w + 6, y + 2, 44, ROW_H)
        )
        val_lbl.setStringValue_(fmt(value))
        val_lbl.setBezeled_(False)
        val_lbl.setDrawsBackground_(False)
        val_lbl.setEditable_(False)
        val_lbl.setSelectable_(False)
        val_lbl.setFont_(_AppKit.NSFont.systemFontOfSize_(12))

        self._connect_slider(slider, callback)

        row_lbl = _AppKit.NSTextField.alloc().initWithFrame_(
            _Foundation.NSMakeRect(LEFT_MARGIN, y + 2, LABEL_W, ROW_H)
        )
        row_lbl.setStringValue_(label)
        row_lbl.setBezeled_(False)
        row_lbl.setDrawsBackground_(False)
        row_lbl.setEditable_(False)
        row_lbl.setSelectable_(False)
        row_lbl.setAlignment_(_AppKit.NSTextAlignmentRight)
        row_lbl.setFont_(_AppKit.NSFont.systemFontOfSize_(12))

        parent.addSubview_(row_lbl)
        parent.addSubview_(slider)
        parent.addSubview_(val_lbl)

        return slider, val_lbl, y + ROW_H + ROW_GAP

    def _make_popup(self, options: list, selected_value: str, frame):
        """NSPopUpButton from (label, value) list."""
        popup = _AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(frame, False)
        for label, _ in options:
            popup.addItemWithTitle_(label)
        for i, (_, val) in enumerate(options):
            if val == selected_value:
                popup.selectItemAtIndex_(i)
                break
        popup.setFont_(_AppKit.NSFont.systemFontOfSize_(12))
        return popup

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

        # Tab view sits above the bottom bar
        tab_margin = 12
        tab_view = _AppKit.NSTabView.alloc().initWithFrame_(
            _Foundation.NSMakeRect(tab_margin, BAR_H, W - tab_margin * 2, H - BAR_H - 8)
        )
        content.addSubview_(tab_view)

        # Build tabs — each builder receives the NSTabViewItem, not its view
        tabs = [
            ("recording", "Recording", self._build_recording_tab),
            ("transcription", "Transcription", self._build_transcription_tab),
            ("grammar", "Grammar", self._build_grammar_tab),
            ("interface", "Interface", self._build_interface_tab),
            ("advanced", "Advanced", self._build_advanced_tab),
            ("about", "About", self._build_about_tab),
        ]
        for ident, label, builder in tabs:
            item = _AppKit.NSTabViewItem.alloc().initWithIdentifier_(ident)
            item.setLabel_(label)
            tab_view.addTabViewItem_(item)
            builder(item)

        # Bottom bar
        margin = 16
        btn_w = 80
        btn_h = 28

        # Restart-required warning label
        self._restart_label = _AppKit.NSTextField.alloc().initWithFrame_(
            _Foundation.NSMakeRect(margin, (BAR_H - 16) / 2, 260, 16)
        )
        self._restart_label.setStringValue_("\u26a0 Some changes require restart")
        self._restart_label.setBezeled_(False)
        self._restart_label.setDrawsBackground_(False)
        self._restart_label.setEditable_(False)
        self._restart_label.setSelectable_(False)
        self._restart_label.setFont_(_AppKit.NSFont.systemFontOfSize_(11))
        self._restart_label.setTextColor_(
            _AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.9, 0.5, 0.1, 1.0)
        )
        self._restart_label.setHidden_(True)
        content.addSubview_(self._restart_label)

        # Cancel button
        cancel_btn = _AppKit.NSButton.alloc().initWithFrame_(
            _Foundation.NSMakeRect(W - margin - btn_w * 2 - 8, (BAR_H - btn_h) / 2, btn_w, btn_h)
        )
        cancel_btn.setTitle_("Cancel")
        cancel_btn.setBezelStyle_(_AppKit.NSBezelStyleRounded)
        cancel_btn.setButtonType_(_AppKit.NSButtonTypeMomentaryPushIn)
        cancel_btn.setKeyEquivalent_("\x1b")
        self._connect_button(cancel_btn, lambda _: self._cancel())
        content.addSubview_(cancel_btn)

        # Save button
        save_btn = _AppKit.NSButton.alloc().initWithFrame_(
            _Foundation.NSMakeRect(W - margin - btn_w, (BAR_H - btn_h) / 2, btn_w, btn_h)
        )
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(_AppKit.NSBezelStyleRounded)
        save_btn.setButtonType_(_AppKit.NSButtonTypeMomentaryPushIn)
        save_btn.setKeyEquivalent_("\r")
        self._connect_button(save_btn, self._on_save)
        content.addSubview_(save_btn)

    # ------------------------------------------------------------------ #
    # Tab builders — each receives item (NSTabViewItem) and calls         #
    # item.setView_() with a flipped view it creates internally           #
    # ------------------------------------------------------------------ #

    def _build_recording_tab(self, item):
        config = get_config()
        view = _FlippedViewClass.alloc().initWithFrame_(
            _Foundation.NSMakeRect(0, 0, CONTENT_W, CONTENT_H)
        )
        item.setView_(view)
        y = 20.0

        # Hotkey section
        y = self._add_section_header(view, y, "Hotkey")

        self._hotkey_popup = self._make_popup(
            _HOTKEY_OPTIONS, config.hotkey.key,
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, ROW_H + 4),
        )
        self._connect_button(self._hotkey_popup, self._on_restart_required_change)
        y = self._add_row(view, y, "Trigger key", self._hotkey_popup)

        # Double-tap threshold slider
        threshold = config.hotkey.double_tap_threshold

        def _tap_changed(sender):
            val = round(sender.floatValue() / 0.05) * 0.05
            self._tap_threshold_label.setStringValue_(f"{val:.2f}s")
            self._on_restart_required_change(sender)

        self._tap_threshold_slider, self._tap_threshold_label, y = self._make_slider_row(
            view, y, "Double-tap window",
            threshold, 0.1, 1.0,
            lambda v: f"{v:.2f}s",
            _tap_changed,
        )

        y = self._add_note(view, y, "Restart required to apply hotkey changes")
        y += SECTION_GAP

        # Audio section
        y = self._add_section_header(view, y, "Audio")

        self._min_duration_field = self._make_text_field_for_row(
            config.audio.min_duration,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(view, y, "Min duration (s)", self._min_duration_field)

        self._max_duration_field = self._make_text_field_for_row(
            config.audio.max_duration,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(view, y, "Max duration (s)", self._max_duration_field)

        rms = config.audio.min_rms

        def _rms_changed(sender):
            self._min_rms_label.setStringValue_(f"{sender.floatValue():.4f}")

        self._min_rms_slider, self._min_rms_label, y = self._make_slider_row(
            view, y, "Min silence RMS",
            rms, 0.0, 0.05,
            lambda v: f"{v:.4f}",
            _rms_changed,
        )

        self._add_note(view, y, "0 = disabled / unlimited for duration fields")
        y += 20 + SECTION_GAP

        # Audio Processing section
        y = self._add_section_header(view, y, "Audio Processing")

        self._vad_enabled_checkbox, y = self._make_checkbox_row(
            view, y, "Enable VAD", config.audio.vad_enabled
        )

        self._noise_reduction_checkbox, y = self._make_checkbox_row(
            view, y, "Noise reduction", config.audio.noise_reduction
        )

        self._normalize_audio_checkbox, y = self._make_checkbox_row(
            view, y, "Normalize audio", config.audio.normalize_audio
        )

        self._pre_buffer_field = self._make_text_field_for_row(
            config.audio.pre_buffer,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(view, y, "Pre-buffer (s)", self._pre_buffer_field)
        self._add_note(view, y, "Lead-in audio captured before hotkey press (0.0\u20131.0 s)")

    def _build_transcription_tab(self, item):
        config = get_config()
        view = _FlippedViewClass.alloc().initWithFrame_(
            _Foundation.NSMakeRect(0, 0, CONTENT_W, CONTENT_H)
        )
        item.setView_(view)
        y = 20.0

        y = self._add_section_header(view, y, "WhisperKit")

        self._whisper_model_field = self._make_text_field_for_row(
            config.whisper.model,
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, ROW_H + 4),
        )
        y = self._add_row(view, y, "Model", self._whisper_model_field)
        y = self._add_note(view, y, "Restart required")
        y += ROW_GAP

        self._whisper_language_popup = self._make_popup(
            _LANGUAGE_OPTIONS, config.whisper.language,
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, ROW_H + 4),
        )
        y = self._add_row(view, y, "Language", self._whisper_language_popup)
        y += ROW_GAP

        # Vocabulary hint (NSTextView in scroll view)
        lbl_prompt = _AppKit.NSTextField.alloc().initWithFrame_(
            _Foundation.NSMakeRect(LEFT_MARGIN, y + 2, LABEL_W, ROW_H)
        )
        lbl_prompt.setStringValue_("Vocabulary hint")
        lbl_prompt.setBezeled_(False)
        lbl_prompt.setDrawsBackground_(False)
        lbl_prompt.setEditable_(False)
        lbl_prompt.setSelectable_(False)
        lbl_prompt.setAlignment_(_AppKit.NSTextAlignmentRight)
        lbl_prompt.setFont_(_AppKit.NSFont.systemFontOfSize_(12))
        view.addSubview_(lbl_prompt)

        prompt_h = 64
        prompt_scroll = _AppKit.NSScrollView.alloc().initWithFrame_(
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, prompt_h)
        )
        prompt_scroll.setBorderType_(_AppKit.NSBezelBorder)
        prompt_scroll.setHasVerticalScroller_(True)
        prompt_scroll.setAutohidesScrollers_(True)

        self._whisper_prompt_view = _AppKit.NSTextView.alloc().initWithFrame_(
            _Foundation.NSMakeRect(0, 0, FIELD_W, prompt_h)
        )
        self._whisper_prompt_view.setHorizontallyResizable_(False)
        self._whisper_prompt_view.setVerticallyResizable_(True)
        self._whisper_prompt_view.setMaxSize_(
            _Foundation.NSMakeSize(FIELD_W, 10000)
        )
        self._whisper_prompt_view.textContainer().setWidthTracksTextView_(True)
        self._whisper_prompt_view.textContainer().setContainerSize_(
            _Foundation.NSMakeSize(FIELD_W, 10000)
        )
        self._whisper_prompt_view.setString_(config.whisper.prompt or "")
        self._whisper_prompt_view.setFont_(_AppKit.NSFont.systemFontOfSize_(12))
        self._whisper_prompt_view.setAutomaticSpellingCorrectionEnabled_(False)
        self._whisper_prompt_view.setAutomaticTextReplacementEnabled_(False)
        prompt_scroll.setDocumentView_(self._whisper_prompt_view)
        view.addSubview_(prompt_scroll)
        y += prompt_h + ROW_GAP

        y = self._add_note(
            view, y,
            "For technical terms only (names, jargon). "
            "Conversational text causes truncated results.",
            height=28,
        )
        y += ROW_GAP

        self._whisper_timeout_field = self._make_text_field_for_row(
            config.whisper.timeout,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(view, y, "Timeout (s, 0=auto)", self._whisper_timeout_field)
        y += SECTION_GAP

        # Decoding Parameters section
        y = self._add_section_header(view, y, "Decoding Parameters")

        self._whisper_temperature_field = self._make_text_field_for_row(
            config.whisper.temperature,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(view, y, "Temperature", self._whisper_temperature_field)

        self._whisper_compression_ratio_field = self._make_text_field_for_row(
            config.whisper.compression_ratio_threshold,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(view, y, "Compression ratio", self._whisper_compression_ratio_field)

        self._whisper_no_speech_threshold_field = self._make_text_field_for_row(
            config.whisper.no_speech_threshold,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(view, y, "No-speech threshold", self._whisper_no_speech_threshold_field)

        self._whisper_logprob_threshold_field = self._make_text_field_for_row(
            config.whisper.logprob_threshold,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(view, y, "Log prob threshold", self._whisper_logprob_threshold_field)

        self._whisper_temperature_fallback_field = self._make_text_field_for_row(
            config.whisper.temperature_fallback_count,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(view, y, "Temp fallback count", self._whisper_temperature_fallback_field)

        self._whisper_prompt_preset_popup = self._make_popup(
            _PROMPT_PRESET_OPTIONS, config.whisper.prompt_preset,
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, ROW_H + 4),
        )
        self._connect_button(self._whisper_prompt_preset_popup, self._on_prompt_preset_change)
        self._connect_button(self._whisper_prompt_preset_popup, self._on_restart_required_change)
        y = self._add_row(view, y, "Prompt preset", self._whisper_prompt_preset_popup)

        y = self._add_note(view, y, "All decoding parameters require restart. Preset updates the vocabulary hint above.")
        self._update_prompt_preset_ui(config.whisper.prompt_preset, config.whisper.prompt)

    def _build_grammar_tab(self, item):
        config = get_config()

        # Outer NSScrollView fills the entire tab content area
        scroll_view = _AppKit.NSScrollView.alloc().initWithFrame_(
            _Foundation.NSMakeRect(0, 0, CONTENT_W, CONTENT_H)
        )
        scroll_view.setHasVerticalScroller_(True)
        scroll_view.setAutohidesScrollers_(True)
        scroll_view.setBorderType_(_AppKit.NSNoBorder)
        item.setView_(scroll_view)

        # Flipped document view — taller than the scroll view
        doc = _FlippedViewClass.alloc().initWithFrame_(
            _Foundation.NSMakeRect(0, 0, CONTENT_W, GRAMMAR_DOC_H)
        )
        scroll_view.setDocumentView_(doc)
        self._grammar_scroll_view = scroll_view
        scroll_view.contentView().scrollToPoint_(_Foundation.NSMakePoint(0, 0))
        scroll_view.reflectScrolledClipView_(scroll_view.contentView())

        y = 20.0

        # Grammar enabled toggle
        self._grammar_enabled_checkbox, y = self._make_checkbox_row(
            doc, y, "Enable grammar correction", config.grammar.enabled
        )
        y += SECTION_GAP

        # ---- Ollama ----
        y = self._add_section_header(doc, y, "Ollama")

        # Model field + Fetch button side-by-side
        btn_w = 72
        self._ollama_model_field = self._make_text_field_for_row(
            config.ollama.model,
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W - btn_w - 4, ROW_H + 4),
        )
        fetch_btn = _AppKit.NSButton.alloc().initWithFrame_(
            _Foundation.NSMakeRect(FIELD_X + FIELD_W - btn_w, y, btn_w, ROW_H + 4)
        )
        fetch_btn.setTitle_("Fetch \u25be")
        fetch_btn.setBezelStyle_(_AppKit.NSBezelStyleRounded)
        fetch_btn.setButtonType_(_AppKit.NSButtonTypeMomentaryPushIn)
        fetch_btn.setFont_(_AppKit.NSFont.systemFontOfSize_(11))
        self._connect_button(fetch_btn, self._on_fetch_ollama_models)
        doc.addSubview_(fetch_btn)
        y = self._add_row(doc, y, "Model", self._ollama_model_field)

        # Model picker popup (hidden until fetch populates it)
        self._ollama_model_popup = _AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, ROW_H + 4), False
        )
        self._ollama_model_popup.addItemWithTitle_("Pick model...")
        self._ollama_model_popup.setHidden_(True)
        self._connect_button(self._ollama_model_popup, self._on_ollama_popup_select)
        # Empty label placeholder to consume row space
        blank_lbl = _AppKit.NSTextField.alloc().initWithFrame_(
            _Foundation.NSMakeRect(LEFT_MARGIN, y, LABEL_W, ROW_H)
        )
        blank_lbl.setStringValue_("")
        blank_lbl.setBezeled_(False)
        blank_lbl.setDrawsBackground_(False)
        blank_lbl.setEditable_(False)
        blank_lbl.setSelectable_(False)
        doc.addSubview_(blank_lbl)
        doc.addSubview_(self._ollama_model_popup)
        y += ROW_H + ROW_GAP

        # Status label (shown during/after fetch)
        self._ollama_status_label = _AppKit.NSTextField.alloc().initWithFrame_(
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, 14)
        )
        self._ollama_status_label.setStringValue_("")
        self._ollama_status_label.setBezeled_(False)
        self._ollama_status_label.setDrawsBackground_(False)
        self._ollama_status_label.setEditable_(False)
        self._ollama_status_label.setSelectable_(False)
        self._ollama_status_label.setFont_(_AppKit.NSFont.systemFontOfSize_(10))
        self._ollama_status_label.setTextColor_(_AppKit.NSColor.secondaryLabelColor())
        doc.addSubview_(self._ollama_status_label)
        y += 18

        self._ollama_url_field = self._make_text_field_for_row(
            config.ollama.url,
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, ROW_H + 4),
        )
        y = self._add_row(doc, y, "API URL", self._ollama_url_field)

        self._ollama_keep_alive_field = self._make_text_field_for_row(
            config.ollama.keep_alive,
            _Foundation.NSMakeRect(FIELD_X, y, 100, ROW_H + 4),
        )
        y = self._add_row(doc, y, "Keep alive", self._ollama_keep_alive_field)

        self._ollama_max_chars_field = self._make_text_field_for_row(
            config.ollama.max_chars,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(doc, y, "Max chars (0=unlimited)", self._ollama_max_chars_field)

        self._ollama_timeout_field = self._make_text_field_for_row(
            config.ollama.timeout,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(doc, y, "Timeout (s)", self._ollama_timeout_field)

        self._ollama_unload_checkbox, y = self._make_checkbox_row(
            doc, y, "Unload model on exit", config.ollama.unload_on_exit
        )
        y += SECTION_GAP

        # ---- Apple Intelligence ----
        y = self._add_section_header(doc, y, "Apple Intelligence")

        self._ai_max_chars_field = self._make_text_field_for_row(
            config.apple_intelligence.max_chars,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(doc, y, "Max chars (0=unlimited)", self._ai_max_chars_field)

        self._ai_timeout_field = self._make_text_field_for_row(
            config.apple_intelligence.timeout,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(doc, y, "Timeout (s)", self._ai_timeout_field)

        y = self._add_note(doc, y, "Requires macOS 26+, Apple Silicon")
        y += SECTION_GAP

        # ---- LM Studio ----
        y = self._add_section_header(doc, y, "LM Studio")

        self._lm_model_field = self._make_text_field_for_row(
            config.lm_studio.model,
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, ROW_H + 4),
        )
        y = self._add_row(doc, y, "Model", self._lm_model_field)

        self._lm_url_field = self._make_text_field_for_row(
            config.lm_studio.url,
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, ROW_H + 4),
        )
        y = self._add_row(doc, y, "API URL", self._lm_url_field)

        self._lm_max_chars_field = self._make_text_field_for_row(
            config.lm_studio.max_chars,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(doc, y, "Max chars (0=unlimited)", self._lm_max_chars_field)

        self._lm_max_tokens_field = self._make_text_field_for_row(
            config.lm_studio.max_tokens,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(doc, y, "Max tokens (0=default)", self._lm_max_tokens_field)

        self._lm_timeout_field = self._make_text_field_for_row(
            config.lm_studio.timeout,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
        )
        y = self._add_row(doc, y, "Timeout (s)", self._lm_timeout_field)
        y += SECTION_GAP

        # ---- Shortcuts ----
        y = self._add_section_header(doc, y, "Shortcuts")

        self._shortcuts_enabled_checkbox, y = self._make_checkbox_row(
            doc, y, "Enable shortcuts", config.shortcuts.enabled
        )
        self._connect_button(self._shortcuts_enabled_checkbox, self._on_restart_required_change)

        self._shortcuts_proofread_field = self._make_text_field_for_row(
            config.shortcuts.proofread,
            _Foundation.NSMakeRect(FIELD_X, y, 140, ROW_H + 4),
        )
        y = self._add_row(doc, y, "Proofread", self._shortcuts_proofread_field)

        self._shortcuts_rewrite_field = self._make_text_field_for_row(
            config.shortcuts.rewrite,
            _Foundation.NSMakeRect(FIELD_X, y, 140, ROW_H + 4),
        )
        y = self._add_row(doc, y, "Rewrite", self._shortcuts_rewrite_field)

        self._shortcuts_prompt_field = self._make_text_field_for_row(
            config.shortcuts.prompt_engineer,
            _Foundation.NSMakeRect(FIELD_X, y, 140, ROW_H + 4),
        )
        y = self._add_row(doc, y, "Prompt engineer", self._shortcuts_prompt_field)

        self._add_note(doc, y, "Shortcut changes require restart")

    def _build_interface_tab(self, item):
        config = get_config()
        view = _FlippedViewClass.alloc().initWithFrame_(
            _Foundation.NSMakeRect(0, 0, CONTENT_W, CONTENT_H)
        )
        item.setView_(view)
        y = 20.0

        y = self._add_section_header(view, y, "Overlay")

        self._show_overlay_checkbox, y = self._make_checkbox_row(
            view, y, "Show recording overlay", config.ui.show_overlay
        )

        opacity = config.ui.overlay_opacity

        def _opacity_changed(sender):
            self._overlay_opacity_label.setStringValue_(f"{sender.floatValue():.2f}")

        self._overlay_opacity_slider, self._overlay_opacity_label, y = self._make_slider_row(
            view, y, "Overlay opacity",
            opacity, 0.1, 1.0,
            lambda v: f"{v:.2f}",
            _opacity_changed,
        )

        y = self._add_note(view, y, "Takes effect after restart")
        y += SECTION_GAP

        y = self._add_section_header(view, y, "Feedback")

        self._sounds_checkbox, y = self._make_checkbox_row(
            view, y, "Sounds enabled", config.ui.sounds_enabled
        )

        self._notifications_checkbox, y = self._make_checkbox_row(
            view, y, "Notifications enabled", config.ui.notifications_enabled
        )

    def _build_advanced_tab(self, item):
        config = get_config()
        view = _FlippedViewClass.alloc().initWithFrame_(
            _Foundation.NSMakeRect(0, 0, CONTENT_W, CONTENT_H)
        )
        item.setView_(view)
        y = 20.0

        y = self._add_section_header(view, y, "Storage")

        self._backup_dir_field = self._make_text_field_for_row(
            config.backup.directory,
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, ROW_H + 4),
        )
        y = self._add_row(view, y, "Backup directory", self._backup_dir_field)
        y += SECTION_GAP

        y = self._add_section_header(view, y, "WhisperKit Server")

        self._whisper_url_field = self._make_text_field_for_row(
            config.whisper.url,
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, ROW_H + 4),
        )
        y = self._add_row(view, y, "API URL", self._whisper_url_field)
        y = self._add_note(view, y, "Restart required")
        y += ROW_GAP

        self._whisper_check_url_field = self._make_text_field_for_row(
            config.whisper.check_url,
            _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, ROW_H + 4),
        )
        y = self._add_row(view, y, "Check URL", self._whisper_check_url_field)
        y = self._add_note(view, y, "Restart required")
        y += SECTION_GAP

        y = self._add_section_header(view, y, "Audio Capture")

        sample_rate_field = self._make_text_field_for_row(
            config.audio.sample_rate,
            _Foundation.NSMakeRect(FIELD_X, y, 80, ROW_H + 4),
            enabled=False,
        )
        y = self._add_row(view, y, "Sample rate (Hz)", sample_rate_field)
        self._add_note(view, y, "Fixed at 16000 Hz for Whisper")

    def _build_about_tab(self, item):
        view = _FlippedViewClass.alloc().initWithFrame_(
            _Foundation.NSMakeRect(0, 0, CONTENT_W, CONTENT_H)
        )
        item.setView_(view)

        LABEL_W = FIELD_X - LEFT_MARGIN - 8  # match other tabs' label width

        def _sep(y):
            """Thin horizontal separator line."""
            box = _AppKit.NSBox.alloc().initWithFrame_(
                _Foundation.NSMakeRect(LEFT_MARGIN, y, CONTENT_W - LEFT_MARGIN * 2, 1)
            )
            box.setBoxType_(_AppKit.NSBoxSeparator)
            view.addSubview_(box)

        def _center_lbl(text, y, h, size, bold=False, secondary=False):
            tf = _AppKit.NSTextField.alloc().initWithFrame_(
                _Foundation.NSMakeRect(LEFT_MARGIN, y, CONTENT_W - LEFT_MARGIN * 2, h)
            )
            tf.setStringValue_(text)
            tf.setBezeled_(False)
            tf.setDrawsBackground_(False)
            tf.setEditable_(False)
            tf.setSelectable_(False)
            tf.setAlignment_(_AppKit.NSTextAlignmentCenter)
            tf.setFont_(
                _AppKit.NSFont.boldSystemFontOfSize_(size) if bold
                else _AppKit.NSFont.systemFontOfSize_(size)
            )
            if secondary:
                tf.setTextColor_(_AppKit.NSColor.secondaryLabelColor())
            view.addSubview_(tf)

        def _row_label(text, y):
            """Right-aligned row label (matches other tabs)."""
            tf = _AppKit.NSTextField.alloc().initWithFrame_(
                _Foundation.NSMakeRect(LEFT_MARGIN, y + 1, LABEL_W, ROW_H)
            )
            tf.setStringValue_(text)
            tf.setBezeled_(False)
            tf.setDrawsBackground_(False)
            tf.setEditable_(False)
            tf.setSelectable_(False)
            tf.setAlignment_(_AppKit.NSTextAlignmentRight)
            tf.setFont_(_AppKit.NSFont.systemFontOfSize_(12))
            tf.setTextColor_(_AppKit.NSColor.secondaryLabelColor())
            view.addSubview_(tf)

        def _row_text(text, y):
            """Plain value text in the right column."""
            tf = _AppKit.NSTextField.alloc().initWithFrame_(
                _Foundation.NSMakeRect(FIELD_X, y + 1, FIELD_W, ROW_H)
            )
            tf.setStringValue_(text)
            tf.setBezeled_(False)
            tf.setDrawsBackground_(False)
            tf.setEditable_(False)
            tf.setSelectable_(False)
            tf.setFont_(_AppKit.NSFont.systemFontOfSize_(12))
            view.addSubview_(tf)

        def _row_link(text, y, url):
            """Clickable link in the right column."""
            btn = _AppKit.NSButton.alloc().initWithFrame_(
                _Foundation.NSMakeRect(FIELD_X, y, FIELD_W, ROW_H + 2)
            )
            btn.setBordered_(False)
            btn.setButtonType_(_AppKit.NSButtonTypeMomentaryPushIn)
            btn.setAlignment_(_AppKit.NSTextAlignmentLeft)
            attr = _Foundation.NSAttributedString.alloc().initWithString_attributes_(
                text,
                {
                    _AppKit.NSForegroundColorAttributeName: _AppKit.NSColor.linkColor(),
                    _AppKit.NSFontAttributeName: _AppKit.NSFont.systemFontOfSize_(12),
                },
            )
            btn.setAttributedTitle_(attr)
            self._connect_button(btn, lambda _, u=url: (
                _AppKit.NSWorkspace.sharedWorkspace().openURL_(
                    _Foundation.NSURL.URLWithString_(u)
                )
            ))
            view.addSubview_(btn)

        # ── App identity header ──────────────────────────────────────────
        y = 32.0
        _center_lbl("Local Whisper", y, 26, 20, bold=True)
        y += 28
        try:
            from whisper_voice import __version__
            _center_lbl(f"Version {__version__}", y, 16, 11, secondary=True)
            y += 18
        except Exception:
            pass
        y += 18

        _sep(y)
        y += 16

        # ── Author ───────────────────────────────────────────────────────
        _row_label("Author", y)
        _row_text("Soroush Yousefpour", y)
        y += ROW_H + ROW_GAP

        _row_label("Website", y)
        _row_link("gabrimatic.info", y, "https://gabrimatic.info")
        y += ROW_H + ROW_GAP

        _row_label("Source", y)
        _row_link("github.com/gabrimatic/local-whisper", y,
                  "https://github.com/gabrimatic/local-whisper")
        y += ROW_H + ROW_GAP

        y += 6
        _sep(y)
        y += 16

        # ── Credits ──────────────────────────────────────────────────────
        credits = [
            ("Speech",   "WhisperKit by Argmax",  "https://github.com/argmaxinc/WhisperKit"),
            ("Grammar",  "Apple Intelligence",     None),
            ("LLM",      "Ollama",                 "https://ollama.ai"),
            ("Menu bar", "rumps",                  "https://github.com/jaredks/rumps"),
            ("Local LLM","LM Studio",              "https://lmstudio.ai"),
        ]
        for row_label, name, url in credits:
            _row_label(row_label, y)
            if url:
                _row_link(name, y, url)
            else:
                _row_text(name, y)
            y += ROW_H + ROW_GAP

    # ------------------------------------------------------------------ #
    # Callbacks                                                            #
    # ------------------------------------------------------------------ #

    def _on_restart_required_change(self, _sender):
        """Called when any restart-required field changes."""
        if self._restart_label:
            self._restart_label.setHidden_(False)
        self._restart_required_changed = True

    def _on_prompt_preset_change(self, sender):
        """Update the vocabulary hint text view when the prompt preset changes."""
        if not self._whisper_prompt_preset_popup or not self._whisper_prompt_view:
            return
        idx = self._whisper_prompt_preset_popup.indexOfSelectedItem()
        if 0 <= idx < len(_PROMPT_PRESET_OPTIONS):
            preset_value = _PROMPT_PRESET_OPTIONS[idx][1]
            self._update_prompt_preset_ui(preset_value, None)

    def _update_prompt_preset_ui(self, preset_value: str, current_prompt):
        """Apply preset text and editable state to the prompt text view."""
        if not self._whisper_prompt_view:
            return
        is_custom = (preset_value == "custom")
        self._whisper_prompt_view.setEditable_(is_custom)
        if preset_value != "custom":
            preset_text = _PROMPT_PRESET_TEXTS.get(preset_value, "")
            self._whisper_prompt_view.setString_(preset_text)
        elif current_prompt is not None:
            self._whisper_prompt_view.setString_(current_prompt)
        color = (
            _AppKit.NSColor.labelColor() if is_custom
            else _AppKit.NSColor.secondaryLabelColor()
        )
        self._whisper_prompt_view.setTextColor_(color)

    def _on_fetch_ollama_models(self, _sender):
        """Fetch available Ollama models in a background thread."""
        if self._ollama_status_label:
            _perform_on_main_thread(
                lambda: self._ollama_status_label.setStringValue_("Fetching...")
            )

        def _fetch():
            import urllib.request
            import json
            from urllib.parse import urlparse
            typed_url = (
                self._ollama_url_field.stringValue().strip()
                if self._ollama_url_field else ""
            )
            if typed_url:
                parsed = urlparse(typed_url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
            else:
                base_url = get_config().ollama.check_url.rstrip("/")
            tags_url = f"{base_url}/api/tags"
            config = get_config()
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
                            self._ollama_model_popup.setHidden_(False)
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
                url_str = tags_url

                def _show_err():
                    if self._ollama_status_label:
                        self._ollama_status_label.setStringValue_(
                            f"Ollama not reachable at {url_str}"
                        )

                _perform_on_main_thread(_show_err)

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_ollama_popup_select(self, _sender):
        """Copy selected model from popup to the model field."""
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
            ("audio", "vad_enabled"): config.audio.vad_enabled,
            ("audio", "noise_reduction"): config.audio.noise_reduction,
            ("audio", "normalize_audio"): config.audio.normalize_audio,
            ("audio", "pre_buffer"): config.audio.pre_buffer,
            ("whisper", "temperature"): config.whisper.temperature,
            ("whisper", "compression_ratio_threshold"): config.whisper.compression_ratio_threshold,
            ("whisper", "no_speech_threshold"): config.whisper.no_speech_threshold,
            ("whisper", "logprob_threshold"): config.whisper.logprob_threshold,
            ("whisper", "temperature_fallback_count"): config.whisper.temperature_fallback_count,
            ("whisper", "prompt_preset"): config.whisper.prompt_preset,
            ("ui", "show_overlay"): config.ui.show_overlay,
            ("ui", "overlay_opacity"): config.ui.overlay_opacity,
            ("ui", "sounds_enabled"): config.ui.sounds_enabled,
            ("ui", "notifications_enabled"): config.ui.notifications_enabled,
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
        if self._vad_enabled_checkbox:
            state = _AppKit.NSControlStateValueOn if config.audio.vad_enabled else _AppKit.NSControlStateValueOff
            self._vad_enabled_checkbox.setState_(state)
        if self._noise_reduction_checkbox:
            state = _AppKit.NSControlStateValueOn if config.audio.noise_reduction else _AppKit.NSControlStateValueOff
            self._noise_reduction_checkbox.setState_(state)
        if self._normalize_audio_checkbox:
            state = _AppKit.NSControlStateValueOn if config.audio.normalize_audio else _AppKit.NSControlStateValueOff
            self._normalize_audio_checkbox.setState_(state)
        if self._pre_buffer_field:
            self._pre_buffer_field.setStringValue_(str(config.audio.pre_buffer))

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
        if self._whisper_temperature_field:
            self._whisper_temperature_field.setStringValue_(str(config.whisper.temperature))
        if self._whisper_compression_ratio_field:
            self._whisper_compression_ratio_field.setStringValue_(
                str(config.whisper.compression_ratio_threshold))
        if self._whisper_no_speech_threshold_field:
            self._whisper_no_speech_threshold_field.setStringValue_(
                str(config.whisper.no_speech_threshold))
        if self._whisper_logprob_threshold_field:
            self._whisper_logprob_threshold_field.setStringValue_(
                str(config.whisper.logprob_threshold))
        if self._whisper_temperature_fallback_field:
            self._whisper_temperature_fallback_field.setStringValue_(
                str(config.whisper.temperature_fallback_count))
        if self._whisper_prompt_preset_popup:
            for i, (_, val) in enumerate(_PROMPT_PRESET_OPTIONS):
                if val == config.whisper.prompt_preset:
                    self._whisper_prompt_preset_popup.selectItemAtIndex_(i)
                    break
            self._update_prompt_preset_ui(config.whisper.prompt_preset, config.whisper.prompt)

        # Grammar tab
        if self._ollama_model_popup:
            self._ollama_model_popup.removeAllItems()
            self._ollama_model_popup.addItemWithTitle_("Pick model...")
            self._ollama_model_popup.setHidden_(True)
        if self._ollama_status_label:
            self._ollama_status_label.setStringValue_("")
        if self._grammar_scroll_view:
            self._grammar_scroll_view.contentView().scrollToPoint_(
                _Foundation.NSMakePoint(0, 0)
            )
            self._grammar_scroll_view.reflectScrolledClipView_(
                self._grammar_scroll_view.contentView()
            )
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
        if self._notifications_checkbox:
            state = _AppKit.NSControlStateValueOn if config.ui.notifications_enabled else _AppKit.NSControlStateValueOff
            self._notifications_checkbox.setState_(state)

        # Advanced tab
        if self._backup_dir_field:
            self._backup_dir_field.setStringValue_(config.backup.directory)
        if self._whisper_url_field:
            self._whisper_url_field.setStringValue_(config.whisper.url)
        if self._whisper_check_url_field:
            self._whisper_check_url_field.setStringValue_(config.whisper.check_url)

    def _checkbox_bool(self, checkbox) -> bool:
        return checkbox.state() == _AppKit.NSControlStateValueOn

    def _popup_value(self, popup, options: list) -> str:
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

        # Validate required string fields before writing anything
        validation_errors = []
        for label, field in [
            ("Whisper model", self._whisper_model_field),
            ("Ollama model", self._ollama_model_field),
            ("LM Studio model", self._lm_model_field),
            ("Proofread shortcut", self._shortcuts_proofread_field),
            ("Rewrite shortcut", self._shortcuts_rewrite_field),
            ("Prompt Engineer shortcut", self._shortcuts_prompt_field),
        ]:
            if field and not field.stringValue().strip():
                validation_errors.append(f"{label} cannot be empty")
        if validation_errors:
            alert = _AppKit.NSAlert.alloc().init()
            alert.setMessageText_("Invalid settings")
            alert.setInformativeText_("\n".join(validation_errors))
            alert.addButtonWithTitle_("OK")
            alert.runModal()
            return

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
        if self._vad_enabled_checkbox:
            new_values[("audio", "vad_enabled")] = self._checkbox_bool(self._vad_enabled_checkbox)
        if self._noise_reduction_checkbox:
            new_values[("audio", "noise_reduction")] = self._checkbox_bool(self._noise_reduction_checkbox)
        if self._normalize_audio_checkbox:
            new_values[("audio", "normalize_audio")] = self._checkbox_bool(self._normalize_audio_checkbox)
        if self._pre_buffer_field:
            new_values[("audio", "pre_buffer")] = round(
                self._parse_float(self._pre_buffer_field.stringValue(), 0.2), 3)

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
        if self._whisper_temperature_field:
            new_values[("whisper", "temperature")] = self._parse_float(
                self._whisper_temperature_field.stringValue(), 0.0)
        if self._whisper_compression_ratio_field:
            new_values[("whisper", "compression_ratio_threshold")] = self._parse_float(
                self._whisper_compression_ratio_field.stringValue(), 2.4)
        if self._whisper_no_speech_threshold_field:
            new_values[("whisper", "no_speech_threshold")] = self._parse_float(
                self._whisper_no_speech_threshold_field.stringValue(), 0.6)
        if self._whisper_logprob_threshold_field:
            new_values[("whisper", "logprob_threshold")] = self._parse_float(
                self._whisper_logprob_threshold_field.stringValue(), -1.0)
        if self._whisper_temperature_fallback_field:
            new_values[("whisper", "temperature_fallback_count")] = self._parse_int(
                self._whisper_temperature_fallback_field.stringValue(), 5)
        if self._whisper_prompt_preset_popup:
            preset_val = self._popup_value(self._whisper_prompt_preset_popup, _PROMPT_PRESET_OPTIONS)
            new_values[("whisper", "prompt_preset")] = preset_val
            # When preset is not custom, save the preset text as the prompt too
            if preset_val != "custom" and self._whisper_prompt_view:
                new_values[("whisper", "prompt")] = _PROMPT_PRESET_TEXTS.get(preset_val, "")

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
        if self._notifications_checkbox:
            new_values[("ui", "notifications_enabled")] = self._checkbox_bool(self._notifications_checkbox)

        # Advanced
        if self._backup_dir_field:
            new_values[("backup", "directory")] = self._backup_dir_field.stringValue().strip()
        if self._whisper_url_field:
            new_values[("whisper", "url")] = self._whisper_url_field.stringValue().strip()
        if self._whisper_check_url_field:
            new_values[("whisper", "check_url")] = self._whisper_check_url_field.stringValue().strip()

        # Validate URL fields before writing
        url_errors = []
        for field_key in [("ollama", "url"), ("lm_studio", "url"),
                          ("whisper", "url"), ("whisper", "check_url")]:
            if field_key in new_values:
                url_val = new_values[field_key]
                if url_val and not _is_valid_url(url_val):
                    url_errors.append(f"Invalid URL: {url_val}")
        if url_errors:
            alert = _AppKit.NSAlert.alloc().init()
            alert.setMessageText_("Invalid settings")
            alert.setInformativeText_("\n".join(url_errors))
            alert.addButtonWithTitle_("OK")
            alert.runModal()
            return

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
            alert.setMessageText_("Some fields could not be saved")
            alert.setInformativeText_(
                "The following fields could not be written to config "
                "(other changes were saved successfully):\n"
                + ", ".join(failed_fields)
            )
            alert.addButtonWithTitle_("OK")
            alert.runModal()
            return

        if any_changed:
            log("Settings saved", "OK")

        self._panel.orderOut_(None)

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
                if resp == 1000:  # NSAlertFirstButtonReturn
                    self._do_restart()
            _perform_on_main_thread(_offer_restart)

    def _do_restart(self):
        """Trigger a service restart via wh restart."""
        import os, shutil
        wh_path = shutil.which("wh")
        if not wh_path:
            venv_wh = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)
                ))),
                ".venv", "bin", "wh"
            )
            if os.path.isfile(venv_wh):
                wh_path = venv_wh
        if not wh_path:
            log("Restart failed: wh not found", "WARN")
            def _err():
                alert = _AppKit.NSAlert.alloc().init()
                alert.setMessageText_("Restart failed")
                alert.setInformativeText_(
                    "Could not find the wh executable. Please restart manually."
                )
                alert.addButtonWithTitle_("OK")
                alert.runModal()
            _perform_on_main_thread(_err)
            return
        try:
            subprocess.Popen(
                [wh_path, "restart"],
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
            _AppKit.NSApp.activateIgnoringOtherApps_(True)
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

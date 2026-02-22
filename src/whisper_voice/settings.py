"""
Settings window for Local Whisper.

Native AppKit NSPanel for configuring grammar backend parameters
(Ollama model/URL, LM Studio model/URL).
"""

import queue
import threading
from typing import Optional, Callable

from .config import get_config, update_config_field
from .utils import log

# Lazily imported macOS frameworks
_AppKit = None
_Foundation = None
_Performer = None
_callback_queue = queue.Queue(maxsize=100)


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


class SettingsWindow:
    """
    Floating settings panel for configuring Ollama and LM Studio backends.
    """

    def __init__(self):
        self._panel = None
        self._lock = threading.Lock()
        # Store delegates to prevent GC
        self._delegates = []
        # UI field references
        self._ollama_model_field = None
        self._ollama_url_field = None
        self._ollama_check_url_field = None
        self._ollama_popup = None
        self._ollama_status_label = None
        self._lm_model_field = None
        self._lm_url_field = None
        self._lm_check_url_field = None
        self._ButtonDelegate = None

    def _create_window(self):
        """Create the settings panel. Must run on main thread."""
        _import_macos()
        self._ButtonDelegate = _make_button_delegate_class()

        config = get_config()

        # Panel dimensions
        width = 480
        height = 380

        # Center on screen
        screen = _AppKit.NSScreen.mainScreen()
        sf = screen.frame()
        x = (sf.size.width - width) / 2
        y = (sf.size.height - height) / 2

        style = (
            _AppKit.NSWindowStyleMaskTitled
            | _AppKit.NSWindowStyleMaskClosable
            | _AppKit.NSWindowStyleMaskMiniaturizable
        )

        self._panel = _AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            _Foundation.NSMakeRect(x, y, width, height),
            style,
            _AppKit.NSBackingStoreBuffered,
            False,
        )
        self._panel.setTitle_("Local Whisper - Settings")
        self._panel.setLevel_(_AppKit.NSFloatingWindowLevel)
        self._panel.setReleasedWhenClosed_(False)

        content_view = self._panel.contentView()
        content_view.setAutoresizingMask_(
            _AppKit.NSViewWidthSizable | _AppKit.NSViewHeightSizable
        )

        # Tab view
        tab_view = _AppKit.NSTabView.alloc().initWithFrame_(
            _Foundation.NSMakeRect(12, 52, width - 24, height - 68)
        )
        tab_view.setAutoresizingMask_(
            _AppKit.NSViewWidthSizable | _AppKit.NSViewHeightSizable
        )
        content_view.addSubview_(tab_view)

        # Ollama tab
        ollama_tab = _AppKit.NSTabViewItem.alloc().initWithIdentifier_("ollama")
        ollama_tab.setLabel_("Ollama")
        tab_view.addTabViewItem_(ollama_tab)
        self._build_ollama_tab(ollama_tab, config, width)

        # LM Studio tab
        lm_tab = _AppKit.NSTabViewItem.alloc().initWithIdentifier_("lm_studio")
        lm_tab.setLabel_("LM Studio")
        tab_view.addTabViewItem_(lm_tab)
        self._build_lm_tab(lm_tab, config, width)

        # Bottom buttons
        btn_width = 80
        btn_height = 28
        margin = 16

        cancel_btn = _AppKit.NSButton.alloc().initWithFrame_(
            _Foundation.NSMakeRect(margin, margin, btn_width, btn_height)
        )
        cancel_btn.setTitle_("Cancel")
        cancel_btn.setBezelStyle_(_AppKit.NSBezelStyleRounded)
        cancel_btn.setButtonType_(_AppKit.NSButtonTypeMomentaryPushIn)
        cancel_btn.setKeyEquivalent_("\x1b")  # Escape
        cancel_delegate = self._ButtonDelegate.alloc().initWithCallback_(
            lambda _: self._panel.orderOut_(None)
        )
        self._delegates.append(cancel_delegate)
        cancel_btn.setTarget_(cancel_delegate)
        cancel_btn.setAction_(_Foundation.NSSelectorFromString("clicked:"))
        content_view.addSubview_(cancel_btn)

        save_btn = _AppKit.NSButton.alloc().initWithFrame_(
            _Foundation.NSMakeRect(margin + btn_width + 8, margin, btn_width, btn_height)
        )
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(_AppKit.NSBezelStyleRounded)
        save_btn.setButtonType_(_AppKit.NSButtonTypeMomentaryPushIn)
        save_btn.setKeyEquivalent_("\r")  # Return
        save_delegate = self._ButtonDelegate.alloc().initWithCallback_(self._on_save)
        self._delegates.append(save_delegate)
        save_btn.setTarget_(save_delegate)
        save_btn.setAction_(_Foundation.NSSelectorFromString("clicked:"))
        content_view.addSubview_(save_btn)

    def _make_label(self, text: str, frame, bold: bool = False):
        """Create a non-editable text label."""
        _import_macos()
        label = _AppKit.NSTextField.alloc().initWithFrame_(frame)
        label.setStringValue_(text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        if bold:
            label.setFont_(_AppKit.NSFont.boldSystemFontOfSize_(12))
        else:
            label.setFont_(_AppKit.NSFont.systemFontOfSize_(12))
        return label

    def _make_text_field(self, value: str, frame):
        """Create an editable NSTextField."""
        _import_macos()
        field = _AppKit.NSTextField.alloc().initWithFrame_(frame)
        field.setStringValue_(value)
        field.setBezeled_(True)
        field.setBezelStyle_(_AppKit.NSTextFieldRoundedBezel)
        field.setDrawsBackground_(True)
        field.setEditable_(True)
        field.setSelectable_(True)
        field.setFont_(_AppKit.NSFont.systemFontOfSize_(12))
        return field

    def _build_ollama_tab(self, tab_item, config, parent_width):
        """Build the Ollama configuration tab."""
        _import_macos()
        tab_view = tab_item.view()
        tab_width = parent_width - 48  # inside tab margins
        label_width = 90
        field_x = label_width + 16
        field_width = tab_width - field_x - 8
        row_height = 22
        row_gap = 12

        # Row 1: Model label
        y = 220
        model_label = self._make_label("Model:", _Foundation.NSMakeRect(8, y + 2, label_width, row_height))
        tab_view.addSubview_(model_label)

        self._ollama_model_field = self._make_text_field(
            config.ollama.model,
            _Foundation.NSMakeRect(field_x, y, field_width - 90, row_height + 4),
        )
        tab_view.addSubview_(self._ollama_model_field)

        # Fetch button
        fetch_btn = _AppKit.NSButton.alloc().initWithFrame_(
            _Foundation.NSMakeRect(field_x + field_width - 88, y, 84, row_height + 4)
        )
        fetch_btn.setTitle_("Fetch Models")
        fetch_btn.setBezelStyle_(_AppKit.NSBezelStyleRounded)
        fetch_btn.setButtonType_(_AppKit.NSButtonTypeMomentaryPushIn)
        fetch_btn.setFont_(_AppKit.NSFont.systemFontOfSize_(11))
        fetch_delegate = self._ButtonDelegate.alloc().initWithCallback_(self._on_fetch_ollama_models)
        self._delegates.append(fetch_delegate)
        fetch_btn.setTarget_(fetch_delegate)
        fetch_btn.setAction_(_Foundation.NSSelectorFromString("clicked:"))
        tab_view.addSubview_(fetch_btn)

        # Row 2: Popup for fetched models
        y -= row_height + row_gap + 4
        popup_label = self._make_label("Pick model:", _Foundation.NSMakeRect(8, y + 2, label_width, row_height))
        tab_view.addSubview_(popup_label)

        self._ollama_popup = _AppKit.NSPopUpButton.alloc().initWithFrame_(
            _Foundation.NSMakeRect(field_x, y - 2, field_width, row_height + 6)
        )
        self._ollama_popup.addItemWithTitle_("(fetch to populate)")
        popup_delegate = self._ButtonDelegate.alloc().initWithCallback_(self._on_ollama_popup_select)
        self._delegates.append(popup_delegate)
        self._ollama_popup.setTarget_(popup_delegate)
        self._ollama_popup.setAction_(_Foundation.NSSelectorFromString("clicked:"))
        tab_view.addSubview_(self._ollama_popup)

        # Status label for fetch errors
        y -= row_height + row_gap - 4
        self._ollama_status_label = self._make_label(
            "", _Foundation.NSMakeRect(field_x, y, field_width, row_height)
        )
        self._ollama_status_label.setTextColor_(_AppKit.NSColor.secondaryLabelColor())
        self._ollama_status_label.setFont_(_AppKit.NSFont.systemFontOfSize_(11))
        tab_view.addSubview_(self._ollama_status_label)

        # Row 3: API URL
        y -= row_height + row_gap
        url_label = self._make_label("API URL:", _Foundation.NSMakeRect(8, y + 2, label_width, row_height))
        tab_view.addSubview_(url_label)

        self._ollama_url_field = self._make_text_field(
            config.ollama.url,
            _Foundation.NSMakeRect(field_x, y, field_width, row_height + 4),
        )
        tab_view.addSubview_(self._ollama_url_field)

        # Row 4: Check URL
        y -= row_height + row_gap
        check_label = self._make_label("Check URL:", _Foundation.NSMakeRect(8, y + 2, label_width, row_height))
        tab_view.addSubview_(check_label)

        self._ollama_check_url_field = self._make_text_field(
            config.ollama.check_url,
            _Foundation.NSMakeRect(field_x, y, field_width, row_height + 4),
        )
        tab_view.addSubview_(self._ollama_check_url_field)

        # Description
        desc = self._make_label(
            "Ollama must be running at the API URL. Model must be pulled.",
            _Foundation.NSMakeRect(8, 12, tab_width - 8, row_height),
        )
        desc.setTextColor_(_AppKit.NSColor.secondaryLabelColor())
        desc.setFont_(_AppKit.NSFont.systemFontOfSize_(11))
        tab_view.addSubview_(desc)

    def _build_lm_tab(self, tab_item, config, parent_width):
        """Build the LM Studio configuration tab."""
        _import_macos()
        tab_view = tab_item.view()
        tab_width = parent_width - 48
        label_width = 90
        field_x = label_width + 16
        field_width = tab_width - field_x - 8
        row_height = 22
        row_gap = 12

        # Row 1: Model
        y = 220
        model_label = self._make_label("Model:", _Foundation.NSMakeRect(8, y + 2, label_width, row_height))
        tab_view.addSubview_(model_label)

        self._lm_model_field = self._make_text_field(
            config.lm_studio.model,
            _Foundation.NSMakeRect(field_x, y, field_width, row_height + 4),
        )
        tab_view.addSubview_(self._lm_model_field)

        # Row 2: API URL
        y -= row_height + row_gap
        url_label = self._make_label("API URL:", _Foundation.NSMakeRect(8, y + 2, label_width, row_height))
        tab_view.addSubview_(url_label)

        self._lm_url_field = self._make_text_field(
            config.lm_studio.url,
            _Foundation.NSMakeRect(field_x, y, field_width, row_height + 4),
        )
        tab_view.addSubview_(self._lm_url_field)

        # Row 3: Check URL
        y -= row_height + row_gap
        check_label = self._make_label("Check URL:", _Foundation.NSMakeRect(8, y + 2, label_width, row_height))
        tab_view.addSubview_(check_label)

        self._lm_check_url_field = self._make_text_field(
            config.lm_studio.check_url,
            _Foundation.NSMakeRect(field_x, y, field_width, row_height + 4),
        )
        tab_view.addSubview_(self._lm_check_url_field)

        # Description
        desc = self._make_label(
            "LM Studio must be running with a model loaded and local server started.",
            _Foundation.NSMakeRect(8, 12, tab_width - 8, row_height),
        )
        desc.setTextColor_(_AppKit.NSColor.secondaryLabelColor())
        desc.setFont_(_AppKit.NSFont.systemFontOfSize_(11))
        tab_view.addSubview_(desc)

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
            # Derive tags URL from check_url (e.g. http://localhost:11434/)
            check_url = config.ollama.check_url.rstrip("/")
            tags_url = f"{check_url}/api/tags"
            try:
                with urllib.request.urlopen(tags_url, timeout=5) as resp:
                    data = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
                if models:
                    def _update():
                        if self._ollama_popup:
                            self._ollama_popup.removeAllItems()
                            for name in models:
                                self._ollama_popup.addItemWithTitle_(name)
                            # Select current model if present
                            current = config.ollama.model
                            if current in models:
                                self._ollama_popup.selectItemWithTitle_(current)
                        if self._ollama_status_label:
                            self._ollama_status_label.setStringValue_(
                                f"{len(models)} model(s) found"
                            )
                    _perform_on_main_thread(_update)
                else:
                    _perform_on_main_thread(
                        lambda: self._ollama_status_label.setStringValue_("No models found") if self._ollama_status_label else None
                    )
            except Exception as e:
                log(f"Ollama fetch failed: {e}", "WARN")
                _perform_on_main_thread(
                    lambda: self._ollama_status_label.setStringValue_("Ollama not reachable") if self._ollama_status_label else None
                )

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_ollama_popup_select(self, _sender):
        """When user picks a model from the popup, fill in the model field."""
        if self._ollama_popup and self._ollama_model_field:
            selected = self._ollama_popup.titleOfSelectedItem()
            if selected and selected != "(fetch to populate)":
                self._ollama_model_field.setStringValue_(selected)

    def _on_save(self, _sender):
        """Save changed values to config and close window."""
        config = get_config()
        changed = False

        # Ollama
        if self._ollama_model_field:
            val = self._ollama_model_field.stringValue()
            if val and val != config.ollama.model:
                update_config_field("ollama", "model", val)
                log(f"Settings: ollama.model -> {val}", "INFO")
                changed = True

        if self._ollama_url_field:
            val = self._ollama_url_field.stringValue()
            if val and val != config.ollama.url:
                update_config_field("ollama", "url", val)
                log(f"Settings: ollama.url -> {val}", "INFO")
                changed = True

        if self._ollama_check_url_field:
            val = self._ollama_check_url_field.stringValue()
            if val and val != config.ollama.check_url:
                update_config_field("ollama", "check_url", val)
                log(f"Settings: ollama.check_url -> {val}", "INFO")
                changed = True

        # LM Studio
        if self._lm_model_field:
            val = self._lm_model_field.stringValue()
            if val and val != config.lm_studio.model:
                update_config_field("lm_studio", "model", val)
                log(f"Settings: lm_studio.model -> {val}", "INFO")
                changed = True

        if self._lm_url_field:
            val = self._lm_url_field.stringValue()
            if val and val != config.lm_studio.url:
                update_config_field("lm_studio", "url", val)
                log(f"Settings: lm_studio.url -> {val}", "INFO")
                changed = True

        if self._lm_check_url_field:
            val = self._lm_check_url_field.stringValue()
            if val and val != config.lm_studio.check_url:
                update_config_field("lm_studio", "check_url", val)
                log(f"Settings: lm_studio.check_url -> {val}", "INFO")
                changed = True

        if changed:
            log("Settings saved", "OK")

        self._panel.orderOut_(None)

    def show(self):
        """Show the settings window. Must be called on main thread."""
        with self._lock:
            if self._panel is None:
                self._create_window()
        self._panel.makeKeyAndOrderFront_(None)
        _AppKit.NSApp.activateIgnoringOtherApps_(True)


# Global singleton
_settings_window: Optional[SettingsWindow] = None


def get_settings_window() -> SettingsWindow:
    """Get the global settings window instance."""
    global _settings_window
    if _settings_window is None:
        _settings_window = SettingsWindow()
    return _settings_window

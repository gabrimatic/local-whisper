# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
TTS processor: reads selected text and speaks it aloud.

Triggered by the speak shortcut (default Option+T). Pressing again stops playback.
"""

import subprocess
import threading
import time
from typing import Callable, Optional

from ApplicationServices import (
    AXUIElementCopyAttributeValue,
    AXUIElementCreateSystemWide,
    kAXFocusedUIElementAttribute,
    kAXSelectedTextAttribute,
)

from .utils import log, play_sound

CLIPBOARD_TIMEOUT = 5
CLIPBOARD_DELAY = 0.15
STATUS_DISPLAY_DURATION = 1.5


class TTSProcessor:
    """
    Handles the TTS shortcut (Option+T by default).

    On trigger:
      - If currently speaking: stops playback immediately.
      - Otherwise: reads selected text and speaks it via the configured TTS provider.

    Text selection uses the same Accessibility API approach as ShortcutProcessor,
    with a Cmd+C clipboard fallback for apps that don't support AX.
    """

    def __init__(self, status_callback: Optional[Callable] = None):
        self._status_callback = status_callback
        self._provider = None
        self._provider_id: str = ""
        self._lock = threading.Lock()
        self._speaking = False
        self._stop_event = threading.Event()

    def is_speaking(self) -> bool:
        with self._lock:
            return self._speaking

    def stop(self):
        """Stop current speech immediately (Esc or recording start)."""
        self._stop_event.set()

    def trigger(self):
        """Called when the speak shortcut fires. Toggles speaking."""
        with self._lock:
            if self._speaking:
                self._stop_event.set()
                return
            self._speaking = True
            self._stop_event.clear()

        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        """Main TTS flow. Runs in background thread."""
        try:
            if self._status_callback:
                self._status_callback("processing", "Reading selection...")

            text = self._get_selected_text()
            if not text:
                log("TTS: no text selected", "WARN")
                self._show_status("No text selected", is_error=True)
                return

            log(f"TTS: speaking {len(text)} chars", "INFO")

            provider = self.get_provider()
            if provider is None:
                self._show_status("TTS unavailable", is_error=True)
                return

            # Show "Generating..." while model is loading / synthesizing audio
            if self._status_callback:
                self._status_callback("processing", "Generating speech...")

            play_sound("Pop")

            # Called right before the first audio chunk starts playing
            def _on_playback_start():
                if self._status_callback:
                    self._status_callback("speaking", "Speaking...")

            # Read fresh config for per-call settings
            from .config import get_config
            cfg = get_config()
            provider.refresh(cfg.kokoro_tts.model)
            provider.speak(
                text,
                self._stop_event,
                speaker=cfg.kokoro_tts.voice,
                on_playback_start=_on_playback_start,
            )

            if self._stop_event.is_set():
                log("TTS: stopped by user", "INFO")
                play_sound("Pop")
            else:
                log("TTS: done", "OK")

        except Exception as e:
            log(f"TTS error: {type(e).__name__}: {e}", "ERR")
            if self._status_callback:
                self._status_callback("error", "TTS error")
            play_sound("Basso")
            time.sleep(STATUS_DISPLAY_DURATION)

        finally:
            with self._lock:
                self._speaking = False
                self._stop_event.clear()
            if self._status_callback:
                self._status_callback("idle", "")

    def get_provider(self):
        """Return the cached TTS provider, recreating it if the provider changed."""
        from .config import get_config
        cfg = get_config()
        provider_id = cfg.tts.provider

        with self._lock:
            if self._provider is not None and self._provider_id == provider_id:
                return self._provider

        try:
            from .tts import create_tts_provider
            provider = create_tts_provider(provider_id)
            provider.start()
            with self._lock:
                if self._provider is not None:
                    try:
                        self._provider.close()
                    except Exception:
                        pass
                self._provider = provider
                self._provider_id = provider_id
            return provider
        except Exception as e:
            log(f"TTS provider init failed: {e}", "ERR")
            return None

    # ------------------------------------------------------------------
    # Text selection (Accessibility API + Cmd+C fallback)
    # ------------------------------------------------------------------

    def _get_selected_text(self) -> Optional[str]:
        text = self._get_selected_text_accessibility()
        if text:
            return text
        log("TTS: Accessibility API failed, trying clipboard fallback", "INFO")
        return self._get_selected_text_clipboard()

    def _get_selected_text_accessibility(self) -> Optional[str]:
        try:
            system = AXUIElementCreateSystemWide()
            err, focused = AXUIElementCopyAttributeValue(
                system, kAXFocusedUIElementAttribute, None
            )
            if err != 0 or focused is None:
                return None
            err, selected_text = AXUIElementCopyAttributeValue(
                focused, kAXSelectedTextAttribute, None
            )
            if err != 0 or selected_text is None:
                return None
            text = str(selected_text).strip()
            return text if text else None
        except Exception as e:
            log(f"TTS Accessibility error: {type(e).__name__}: {e}", "INFO")
            return None

    def _get_selected_text_clipboard(self) -> Optional[str]:
        """Clipboard-based fallback: send Cmd+C and read the result."""
        try:
            time.sleep(0.3)
            subprocess.run([
                'osascript', '-e',
                'tell application "System Events" to keystroke "c" using command down'
            ], capture_output=True, timeout=CLIPBOARD_TIMEOUT)
            time.sleep(CLIPBOARD_DELAY)
            result = subprocess.run(
                ['pbpaste'], capture_output=True, text=True, timeout=CLIPBOARD_TIMEOUT
            )
            content = result.stdout.strip()
            return content if content else None
        except Exception as e:
            log(f"TTS clipboard error: {type(e).__name__}: {e}", "INFO")
            return None

    def _show_status(self, message: str, is_error: bool = False):
        try:
            phase = "error" if is_error else "done"
            if self._status_callback:
                self._status_callback(phase, message)
            if is_error:
                play_sound("Basso")
            time.sleep(STATUS_DISPLAY_DURATION)
        except Exception as e:
            log(f"TTS status error: {e}", "WARN")

    def close(self):
        """Stop speaking and release resources."""
        self._stop_event.set()
        with self._lock:
            if self._provider:
                try:
                    self._provider.close()
                except Exception:
                    pass
                self._provider = None

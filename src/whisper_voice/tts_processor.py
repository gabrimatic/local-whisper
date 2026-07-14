# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
TTS processor: reads selected text and speaks it aloud.

Triggered by the speak shortcut (default Option+T). Pressing again stops playback.
"""

import threading
from typing import Callable, Optional

from .selection import ClipboardSnapshot, get_selected_text
from .utils import log, play_sound

STATUS_DISPLAY_DURATION = 1.5

# Speaking an accidental select-all would synthesize for minutes; cap it.
MAX_TTS_CHARS = 20_000


class TTSProcessor:
    """
    Handles the TTS shortcut (Option+T by default).

    On trigger:
      - If currently speaking: stops playback immediately.
      - Otherwise: reads selected text and speaks it via the configured TTS provider.

    Text selection goes through the shared selection module: Accessibility
    API first, then a marker-verified Cmd+C fallback — the marker guarantees
    stale clipboard content is never spoken when nothing is selected.
    """

    def __init__(self, status_callback: Optional[Callable] = None):
        self._status_callback = status_callback
        self._provider = None
        self._provider_id: str = ""
        self._lock = threading.Lock()
        self._provider_lock = threading.Lock()
        self._speaking = False
        self._stop_event = threading.Event()
        # Status generation counter (see ShortcutProcessor): delayed idle
        # resets only fire if no newer status replaced them, so a rapid
        # stop-then-retrigger never has its Esc interception or overlay
        # state cleared by the previous session's teardown.
        self._status_gen = 0

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

    # ------------------------------------------------------------------
    # Status plumbing
    # ------------------------------------------------------------------

    def _emit_status(self, phase: str, message: str) -> int:
        with self._lock:
            self._status_gen += 1
            gen = self._status_gen
        if self._status_callback:
            self._status_callback(phase, message)
        return gen

    def _schedule_idle_reset(self, gen: int):
        def _reset():
            with self._lock:
                if gen != self._status_gen:
                    return
            if self._status_callback:
                self._status_callback("idle", "")

        timer = threading.Timer(STATUS_DISPLAY_DURATION, _reset)
        timer.daemon = True
        timer.start()

    def _show_error(self, message: str):
        gen = self._emit_status("error", message)
        play_sound("Basso")
        self._schedule_idle_reset(gen)

    # ------------------------------------------------------------------
    # Main flow
    # ------------------------------------------------------------------

    def _process(self):
        """Main TTS flow. Runs in background thread."""
        # Error paths schedule their own delayed idle reset; every other
        # exit goes idle immediately. Tracked so finally sends exactly one
        # terminal status, always BEFORE _speaking releases — a rapid
        # retrigger can then never have its fresh status clobbered by this
        # session's teardown (the generation guard covers delayed resets).
        terminal_status_sent = False
        try:
            self._emit_status("processing", "Reading selection...")

            snapshot = ClipboardSnapshot.capture()
            text = get_selected_text(snapshot)
            if not text or not text.strip():
                log("TTS: no text selected", "WARN")
                self._show_error("No text selected")
                terminal_status_sent = True
                return
            # The Cmd+C fallback leaves the selection on the clipboard;
            # give the user their clipboard back before we start speaking.
            snapshot.restore()

            if len(text) > MAX_TTS_CHARS:
                log(f"TTS: selection too long ({len(text)} chars)", "WARN")
                self._show_error("Selection too long")
                terminal_status_sent = True
                return

            log(f"TTS: speaking {len(text)} chars", "INFO")

            if self._stop_event.is_set():
                log("TTS: stopped before synthesis", "INFO")
                return

            provider = self.get_provider()
            if provider is None:
                self._show_error("TTS unavailable")
                terminal_status_sent = True
                return

            # Show "Generating..." while model is loading / synthesizing audio
            self._emit_status("processing", "Generating speech...")

            play_sound("Pop")

            # Called right before the first audio chunk starts playing
            def _on_playback_start():
                self._emit_status("speaking", "Speaking...")

            # Read fresh config for per-call settings
            from .config import get_config
            cfg = get_config()
            provider.refresh(cfg.kokoro_tts.model)
            if self._stop_event.is_set():
                log("TTS: stopped during model preparation", "INFO")
                return
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
            self._show_error("TTS error")
            terminal_status_sent = True

        finally:
            if not terminal_status_sent:
                self._emit_status("idle", "")
            with self._lock:
                self._speaking = False
                self._stop_event.clear()

    def get_provider(self):
        """Return the cached TTS provider, recreating it if the provider changed.

        Creation is serialized by _provider_lock so a trigger racing the
        eager preload can't double-load the Kokoro model.
        """
        from .config import get_config
        cfg = get_config()
        provider_id = cfg.tts.provider

        with self._provider_lock:
            with self._lock:
                if self._provider is not None and self._provider_id == provider_id:
                    return self._provider

            try:
                from .tts import create_tts_provider
                provider = create_tts_provider(provider_id)
                provider.start()
            except Exception as e:
                log(f"TTS provider init failed: {e}", "ERR")
                return None
            with self._lock:
                old = self._provider
                self._provider = provider
                self._provider_id = provider_id
            if old is not None:
                try:
                    old.close()
                except Exception:
                    pass
            return provider

    def unload_model(self) -> None:
        """Release TTS model from RAM."""
        with self._lock:
            provider = self._provider
        if provider and hasattr(provider, 'unload'):
            provider.unload()

    def close(self):
        """Stop speaking and release resources."""
        self._stop_event.set()
        with self._lock:
            provider = self._provider
            self._provider = None
        if provider:
            try:
                provider.close()
            except Exception:
                pass

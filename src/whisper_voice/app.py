# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Whisper - 100% Local Voice Transcription + Grammar Correction

Double-tap Right Option (⌥) to start recording, single tap to stop.
Transcribed and polished text is copied to clipboard.

Architecture:
    Voice -> WhisperKit (localhost:50060) -> Grammar Backend -> Clipboard

Supported grammar backends:
    - apple_intelligence: Apple's on-device Foundation Models (macOS 15+)
    - ollama: Local Ollama server with configurable LLM models
    - lm_studio: LM Studio local server (OpenAI-compatible API)

Privacy: All processing on-device. No internet. No cloud. No tracking.
"""

import atexit
import fcntl
import os
import subprocess
import signal
import sys
import time
import threading
import warnings
from pathlib import Path
from typing import Optional

import numpy as np

import rumps
from pynput import keyboard

from .config import get_config, CONFIG_FILE
from .utils import (
    log, play_sound, is_hallucination, hide_dock_icon, truncate,
    strip_hallucination_lines, check_microphone_permission,
    check_accessibility_trusted, request_accessibility_permission, send_notification,
    ICON_IDLE, ICON_RECORDING, ICON_PROCESSING, ICON_SUCCESS, ICON_ERROR,
    ICON_IMAGE, ICON_FRAMES, ICON_PROCESS_FRAMES, OVERLAY_WAVE_FRAMES,
    ICON_RESET_SUCCESS, ICON_RESET_ERROR, LOG_TRUNCATE, PREVIEW_TRUNCATE,
    ANIM_INTERVAL_RECORDING, ANIM_INTERVAL_PROCESSING, DURATION_UPDATE_INTERVAL,
    CLIPBOARD_TIMEOUT,
    C_RESET, C_BOLD, C_DIM, C_CYAN, C_GREEN, C_YELLOW
)
from .audio import Recorder
from .audio_processor import AudioProcessor
from .backup import Backup
from .transcriber import Transcriber
from .grammar import Grammar
from .overlay import get_overlay, _perform_on_main_thread
from .backends import BACKEND_REGISTRY
from .shortcuts import ShortcutProcessor, build_shortcut_map
from .key_interceptor import KeyInterceptor

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")


# Key name to pynput key mapping
KEY_MAP = {
    "alt_r": keyboard.Key.alt_r,
    "alt_l": keyboard.Key.alt_l,
    "ctrl_r": keyboard.Key.ctrl_r,
    "ctrl_l": keyboard.Key.ctrl_l,
    "cmd_r": keyboard.Key.cmd_r,
    "cmd_l": keyboard.Key.cmd_l,
    "shift_r": keyboard.Key.shift_r,
    "shift_l": keyboard.Key.shift_l,
    "caps_lock": keyboard.Key.caps_lock,
    "f1": keyboard.Key.f1,
    "f2": keyboard.Key.f2,
    "f3": keyboard.Key.f3,
    "f4": keyboard.Key.f4,
    "f5": keyboard.Key.f5,
    "f6": keyboard.Key.f6,
    "f7": keyboard.Key.f7,
    "f8": keyboard.Key.f8,
    "f9": keyboard.Key.f9,
    "f10": keyboard.Key.f10,
    "f11": keyboard.Key.f11,
    "f12": keyboard.Key.f12,
}

class App(rumps.App):
    """Main menu bar application."""

    def __init__(self):
        super().__init__(name="Whisper", title=ICON_IDLE, icon=ICON_IMAGE, template=True, quit_button=None)

        self.config = get_config()
        self.backup = Backup()
        self.transcriber = Transcriber()
        # Only create Grammar if enabled (user selected a backend, not "Disabled")
        self.grammar = Grammar() if self.config.grammar.enabled else None
        self.recorder = Recorder()
        self.overlay = get_overlay()
        self.audio_processor = AudioProcessor(self.config)

        # Grammar submenu state
        self._grammar_lock = threading.Lock()
        self._backend_menu_items: dict = {}  # backend_id -> MenuItem
        self.grammar_menu = rumps.MenuItem("Grammar")
        self._build_backend_submenu()

        # State flags
        self._busy = False
        self._ready = False
        self._grammar_ready = False
        self._dock_hidden = False
        self._state_lock = threading.Lock()
        self._max_timer = None
        self._frame_index = 0
        self._anim_state = None
        self._anim_stop = threading.Event()
        self._anim_lock = threading.Lock()
        self._anim_thread = None  # Explicitly initialize animation thread

        # Double-tap detection
        self._last_tap_time = 0
        self._record_key = KEY_MAP.get(self.config.hotkey.key, keyboard.Key.alt_r)
        self._keyboard_listener = None
        self._key_pressed = False  # Track if hotkey is currently held down

        # Shortcut processor for text transformation modes
        self._shortcut_processor: Optional[ShortcutProcessor] = None
        self._shortcut_map: dict = {}  # key -> (modifiers, mode_id)
        self._key_interceptor: Optional[KeyInterceptor] = None

        # Build menu
        self.status = rumps.MenuItem("Starting...")
        self.menu = [
            self.status,
            self.grammar_menu,
            None,
            rumps.MenuItem("Retry Last", callback=self._retry),
            rumps.MenuItem("Copy Last", callback=self._copy),
            rumps.MenuItem("History", callback=self._open_history),
            None,
            rumps.MenuItem("Backups", callback=self._open_backups),
            rumps.MenuItem("Config", callback=self._open_config),
            rumps.MenuItem("Settings...", callback=self._open_settings),
            rumps.MenuItem("Quit", callback=self._quit)
        ]

        # Start initialization in background
        threading.Thread(target=self._init, daemon=True).start()

    @rumps.timer(0.1)
    def _hide_dock(self, _):
        """Hide dock icon once app is running."""
        if not self._dock_hidden:
            hide_dock_icon()
            self._dock_hidden = True

    def _build_backend_submenu(self):
        """Build the Grammar submenu with all backends + Settings."""
        current = self.config.grammar.backend if self.config.grammar.enabled else "none"
        self._backend_menu_items = {}

        for backend_id, info in BACKEND_REGISTRY.items():
            item = rumps.MenuItem(info.name, callback=self._on_switch_backend)
            item._backend_id = backend_id
            item.state = 1 if backend_id == current else 0
            self._backend_menu_items[backend_id] = item
            self.grammar_menu.add(item)

        # Disabled option
        disabled_item = rumps.MenuItem("Disabled", callback=self._on_switch_backend)
        disabled_item._backend_id = "none"
        disabled_item.state = 1 if not self.config.grammar.enabled else 0
        self._backend_menu_items["none"] = disabled_item
        self.grammar_menu.add(None)   # separator
        self.grammar_menu.add(disabled_item)
        # Set parent menu title
        if not self.config.grammar.enabled:
            self.grammar_menu.title = "Grammar: Disabled"
        else:
            info = BACKEND_REGISTRY.get(current)
            self.grammar_menu.title = f"Grammar: {info.name}" if info else "Grammar"

    def _update_backend_menu_checks(self, active_id: str):
        """Update checkmarks. Must run on main thread."""
        for bid, item in self._backend_menu_items.items():
            item.state = 1 if bid == active_id else 0
        info = BACKEND_REGISTRY.get(active_id)
        if active_id == "none":
            self.grammar_menu.title = "Grammar: Disabled"
        elif info:
            self.grammar_menu.title = f"Grammar: {info.name}"

    def _on_switch_backend(self, sender):
        """Menu callback for backend selection."""
        if self._busy or self.recorder.recording:
            return
        backend_id = sender._backend_id
        current = self.config.grammar.backend if self.config.grammar.enabled else "none"
        if backend_id == current and self._grammar_ready:
            return
        threading.Thread(target=self._switch_backend, args=(backend_id,), daemon=True).start()

    def _switch_backend(self, backend_id: str):
        """Switch grammar backend in-process. Runs in background thread."""
        from .config import update_config_backend
        from .grammar import Grammar

        info = BACKEND_REGISTRY.get(backend_id)
        display_name = info.name if info else ("Disabled" if backend_id == "none" else backend_id)

        # Show switching status
        _perform_on_main_thread(lambda: setattr(self.status, "title", f"Switching to {display_name}..."))
        _perform_on_main_thread(lambda: self._update_backend_menu_checks(backend_id))

        # Capture current backend for potential rollback
        previous_backend_id = self.config.grammar.backend if self.config.grammar.enabled else "none"

        # Tear down old grammar
        with self._grammar_lock:
            old_grammar = self.grammar
            self.grammar = None
            self._grammar_ready = False

        if old_grammar is not None:
            try:
                old_grammar.close()
            except Exception as e:
                log(f"Error closing grammar: {e}", "WARN")

        # Handle "disabled" case — safe to persist immediately (no start() can fail)
        if backend_id == "none":
            update_config_backend(backend_id)
            log("Grammar correction disabled")
            _perform_on_main_thread(lambda: setattr(self.status, "title", "Ready"))
            return

        # Update in-memory config to new backend so Grammar() initializes the right one.
        # If start() fails we rollback below.
        self.config.grammar.backend = backend_id
        self.config.grammar.enabled = True

        ok = False
        new_grammar = None
        try:
            new_grammar = Grammar()
            ok = new_grammar.start()
        except Exception as e:
            log(f"Failed to start {display_name}: {e}", "ERR")
            new_grammar = None
            ok = False

        with self._grammar_lock:
            if ok:
                # Persist confirmed successful start to TOML
                update_config_backend(backend_id)
                self.grammar = new_grammar
                self._grammar_ready = True
                if hasattr(self, "_shortcut_processor") and self._shortcut_processor is not None:
                    from .shortcuts import ShortcutProcessor
                    self._shortcut_processor = ShortcutProcessor(self.grammar)
            else:
                # Rollback in-memory config to previous backend
                update_config_backend(previous_backend_id)
                self.grammar = None
                self._grammar_ready = False

        if ok:
            log(f"Switched to {display_name}")
            _perform_on_main_thread(lambda: setattr(self.status, "title", "Ready"))
        else:
            log(f"{display_name} unavailable", "ERR")
            # Rollback menu checkmarks to the previous backend
            prev = previous_backend_id
            _perform_on_main_thread(lambda: self._update_backend_menu_checks(prev))
            def _show_error():
                self.status.title = f"{display_name} unavailable"
                threading.Timer(3.0, lambda: _perform_on_main_thread(
                    lambda: setattr(self.status, "title", "Ready")
                )).start()
            _perform_on_main_thread(_show_error)

    def _open_settings(self, _=None):
        """Open the Settings window."""
        from .settings import get_settings_window
        win = get_settings_window()
        _perform_on_main_thread(win.show)

    def _set(self, icon: str, text: str):
        """Update menu bar icon and status text."""
        def _do():
            self.title = icon
            self.status.title = text
        _perform_on_main_thread(_do)

    def _set_icon(self, icon_path: Optional[str]):
        """Update menu bar icon image."""
        def _do():
            if icon_path and icon_path != self.icon:
                self.icon = icon_path
        _perform_on_main_thread(_do)

    def _start_animation(self, state: str):
        """Start or update the animation state."""
        with self._anim_lock:
            self._anim_state = state
            self._anim_stop.clear()
            if self._anim_thread is None or not self._anim_thread.is_alive():
                self._anim_thread = threading.Thread(target=self._animate, daemon=True)
                self._anim_thread.start()

    def _stop_animation(self):
        """Stop any running animation."""
        with self._anim_lock:
            self._anim_state = None
            self._anim_stop.set()

    def _animate(self):
        """Animate the menu bar icon (and overlay during processing)."""
        while not self._anim_stop.is_set():
            with self._anim_lock:
                state = self._anim_state
            if state == "recording":
                if not self.recorder.recording:
                    self._stop_animation()
                    break
                frame = ICON_FRAMES[self._frame_index % len(ICON_FRAMES)]
                self._set_icon(frame)
                self._frame_index += 1
                time.sleep(ANIM_INTERVAL_RECORDING)
            elif state == "processing":
                if not self._busy or self.recorder.recording:
                    self._stop_animation()
                    break
                frame = ICON_PROCESS_FRAMES[self._frame_index % len(ICON_PROCESS_FRAMES)]
                wave = OVERLAY_WAVE_FRAMES[self._frame_index % len(OVERLAY_WAVE_FRAMES)]
                self._set_icon(frame)
                self.overlay.set_processing_frame(wave)
                self._frame_index += 1
                time.sleep(ANIM_INTERVAL_PROCESSING)
            else:
                break

    def _init(self):
        """Initialize services (runs in background thread)."""
        log("Starting...")
        self._set(ICON_PROCESSING, "Starting servers...")

        # Start transcription engine - required
        if not self.transcriber.start():
            self._set(ICON_ERROR, f"{self.transcriber.name} failed")
            log(f"{self.transcriber.name} failed to start. Exiting.", "ERR")
            self._exit_app()
            return
        self._ready = True

        # Check grammar backend - required if enabled
        if self.config.grammar.enabled and self.grammar is not None:
            self._grammar_ready = self.grammar.start()
            if not self._grammar_ready:
                log(f"{self.grammar.name} not available.", "ERR")
                log("Exiting - all services must be available.", "ERR")
                self._exit_app()
                return

            # Start shortcuts if enabled and grammar backend available
            if self.config.shortcuts.enabled:
                self._shortcut_processor = ShortcutProcessor(self.grammar)
                self._shortcut_map = build_shortcut_map(self.config)

                # Initialize CGEventTap-based key interceptor for shortcuts
                self._key_interceptor = KeyInterceptor()
                for key, (modifiers, mode_id) in self._shortcut_map.items():
                    self._key_interceptor.register_shortcut(
                        modifiers, key,
                        lambda mid=mode_id: self._shortcut_processor.trigger(mid)
                    )
                self._key_interceptor.set_enabled_guard(
                    lambda: (not self.recorder.recording
                             and not self._busy
                             and not self._shortcut_processor.is_busy())
                )
                if self._key_interceptor.start():
                    log("Shortcuts: Ctrl+Shift+G (proofread) Ctrl+Shift+R (rewrite) Ctrl+Shift+P (prompt)", "OK")
                else:
                    log("Shortcut interception failed (shortcuts will still work but won't suppress keys)", "WARN")
        else:
            log("Grammar correction disabled", "INFO")

        self._set(ICON_IDLE, "Ready")
        key_name = self.config.hotkey.key.upper().replace("_", " ")
        log(f"Double-tap {key_name} to record, tap to stop", "OK")

        # Check Accessibility permission - required for global hotkey
        if not check_accessibility_trusted():
            request_accessibility_permission()  # triggers system dialog + opens Settings
            log("Accessibility permission required - System Settings opened", "WARN")
            log("Enable this process in Accessibility, then run: wh restart", "WARN")

        # Start keyboard listener
        self._start_keyboard_listener()

    def _exit_app(self):
        """Exit the application from any thread."""
        def do_exit():
            self._cleanup()
            rumps.quit_application()
        # Schedule exit on main thread
        threading.Timer(0.5, do_exit).start()

    def _start_keyboard_listener(self):
        """Start the keyboard listener for hotkey detection."""
        try:
            # Use both on_press and on_release to properly handle key repeat
            self._keyboard_listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release
            )
            self._keyboard_listener.daemon = True
            self._keyboard_listener.start()
        except Exception as e:
            log(f"Keyboard error: {e}", "ERR")
            self._show_accessibility_guide()

    def _show_accessibility_guide(self):
        """Show guide for enabling Accessibility permissions."""
        print()
        print(f"  {C_BOLD}{C_YELLOW}⚠ Accessibility Permission Required{C_RESET}")
        print()
        print(f"  Whisper needs Accessibility access to detect hotkeys.")
        print()
        print(f"  {C_BOLD}How to fix:{C_RESET}")
        print(f"  1. Open {C_CYAN}System Settings{C_RESET} → {C_CYAN}Privacy & Security{C_RESET} → {C_CYAN}Accessibility{C_RESET}")
        print(f"  2. Click the {C_CYAN}+{C_RESET} button")
        print(f"  3. Add {C_CYAN}Terminal{C_RESET} (or your terminal app: iTerm, VS Code, etc.)")
        print(f"  4. Restart this app")
        print()
        print(f"  {C_DIM}Tip: You can also run: open x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility{C_RESET}")
        print()

    def _on_key_press(self, key):
        """Handle key press events for double-tap / single-tap detection."""
        # Note: Shortcuts are handled by KeyInterceptor (CGEventTap) for proper suppression

        stop_keys = {self._record_key, keyboard.Key.space}

        # Stop recording on record key, Esc, or Space
        if self.recorder.recording:
            if key == keyboard.Key.esc:
                self._cancel_recording()
            elif key in stop_keys:
                self._stop_recording()
            return

        if key != self._record_key:
            return

        # Ignore key repeat events (key already pressed)
        if self._key_pressed:
            return
        self._key_pressed = True

        current_time = time.time()

        # Check for double-tap
        time_since_last = current_time - self._last_tap_time
        self._last_tap_time = current_time

        if time_since_last <= self.config.hotkey.double_tap_threshold:
            # Double-tap detected - start recording
            self._start_recording()

    def _on_key_release(self, key):
        """Handle key release events to reset key pressed state."""
        if key == self._record_key:
            self._key_pressed = False

    def _cancel_recording(self):
        """Cancel recording without processing or saving."""
        if self._max_timer:
            self._max_timer.cancel()
            self._max_timer = None
        if not self.recorder.recording:
            return
        self.recorder.stop()
        self._stop_animation()
        self._set(ICON_IDLE, "Ready")
        self._set_icon(ICON_IMAGE)
        self.overlay.hide()
        self.recorder.start_monitoring()

    def _start_recording(self):
        """Start audio recording."""
        with self._state_lock:
            if self._busy or not self._ready:
                return
            if self.recorder.recording:
                return
            self._frame_index = 0

            # Start recording while holding lock to prevent races
            if not self.recorder.start():
                self._set(ICON_ERROR, "Mic error")
                self._set_icon(ICON_IMAGE)
                self.overlay.set_status("error")
                play_sound("Basso")
                self._reset_with_overlay(ICON_RESET_ERROR)
                return

        play_sound("Pop")
        self._set(ICON_RECORDING, "Recording...")
        self._set_icon(ICON_FRAMES[0])
        self._start_animation("recording")
        log("Recording...", "REC")

        # Show overlay
        self.overlay.show()

        # Start duration update thread
        threading.Thread(target=self._update_duration, daemon=True).start()

        # Start max duration timer (auto-stop protection) - skip if max_duration is 0 (unlimited)
        if self.config.audio.max_duration > 0:
            self._max_timer = threading.Timer(
                self.config.audio.max_duration,
                self._auto_stop
            )
            self._max_timer.daemon = True
            self._max_timer.start()

    def _stop_recording(self):
        """Stop recording and process audio."""
        # Cancel max duration timer first (safe without lock)
        if self._max_timer:
            self._max_timer.cancel()
            self._max_timer = None

        # Acquire state lock early to prevent race conditions
        with self._state_lock:
            if not self.recorder.recording:
                return

            if self._busy:
                return

            try:
                audio = self.recorder.stop()
            except Exception as e:
                log(f"Recorder stop error: {e}", "ERR")
                self._set(ICON_ERROR, "Record error")
                self._set_icon(ICON_IMAGE)
                self._stop_animation()
                self.overlay.set_status("error")
                play_sound("Basso")
                self._reset_with_overlay(ICON_RESET_ERROR)
                self.recorder.start_monitoring()
                return
            dur = len(audio) / self.config.audio.sample_rate if len(audio) > 0 else 0

            # Reject truly empty recordings (no audio data)
            if len(audio) == 0:
                log("No audio captured", "WARN")
                self._set(ICON_IDLE, "Ready")
                self._set_icon(ICON_IMAGE)
                self._stop_animation()
                self.overlay.set_status("error")
                play_sound("Basso")
                self._reset_with_overlay(ICON_RESET_ERROR)
                self.recorder.start_monitoring()
                return

            # Detect all-zeros audio (mic permission issue)
            if np.max(np.abs(audio)) == 0:
                log("Mic returned silence - check microphone permissions in System Settings", "ERR")
                self._set(ICON_ERROR, "Mic permission?")
                self._set_icon(ICON_IMAGE)
                self._stop_animation()
                self.overlay.set_status("error")
                play_sound("Basso")
                self._reset_with_overlay(ICON_RESET_ERROR)
                self.recorder.start_monitoring()
                return

            # Check min_duration if configured (0 = no minimum)
            if self.config.audio.min_duration > 0 and dur < self.config.audio.min_duration:
                log(f"Too short ({dur:.1f}s)", "WARN")
                self._set(ICON_IDLE, "Ready")
                self._set_icon(ICON_IMAGE)
                self._stop_animation()
                self.overlay.set_status("error")
                play_sound("Basso")
                self._reset_with_overlay(ICON_RESET_ERROR)
                self.recorder.start_monitoring()
                return

            log(f"Recorded {dur:.1f}s", "OK")
            self._busy = True

        # Start processing outside the lock
        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _auto_stop(self):
        """Auto-stop recording if max duration exceeded."""
        if self.recorder.recording:
            log(f"Max duration ({self.config.audio.max_duration}s) reached, stopping", "WARN")
            self._stop_recording()

    def _update_duration(self):
        """Update menu bar and overlay with recording duration."""
        local_index = 0
        warned_long = False
        while self.recorder.recording:
            dur = self.recorder.duration
            wave = OVERLAY_WAVE_FRAMES[local_index % len(OVERLAY_WAVE_FRAMES)]
            def _set_title():
                self.title = ICON_RECORDING
            _perform_on_main_thread(_set_title)
            level = self.recorder.rms_level
            self.overlay.update_duration(dur, wave, level)
            local_index += 1
            # Warn about very long recordings (memory usage)
            if dur > 1800 and not warned_long:  # 30 minutes
                log("Recording is very long (>30 min) - consider stopping to avoid memory issues", "WARN")
                warned_long = True
            time.sleep(DURATION_UPDATE_INTERVAL)
        # Reset title when done (processing will update it if active)
        if self._busy:
            self._set_icon(ICON_IMAGE)
            def _set_processing():
                self.title = ICON_PROCESSING
            _perform_on_main_thread(_set_processing)
        else:
            self._set_icon(ICON_IMAGE)
            def _set_idle():
                self.title = ICON_IDLE
            _perform_on_main_thread(_set_idle)

    def _process(self, audio):
        """Process recorded audio: transcribe, fix grammar, copy to clipboard."""
        self.overlay.set_status("processing")
        self._frame_index = 0
        self._start_animation("processing")
        try:
            config = self.config

            # 0. CRITICAL: Save raw audio IMMEDIATELY before any processing.
            # If anything crashes below (VAD, noise reduction, transcription, grammar),
            # the raw recording is already safely on disk for retry/recovery.
            raw_backup_path = self.backup.save_audio(audio)
            if raw_backup_path:
                log(f"Raw audio saved ({len(audio) / config.audio.sample_rate:.1f}s)", "OK")
            else:
                # Even if save fails, continue processing (don't lose the transcription
                # just because disk write failed). Log the error prominently.
                log("CRITICAL: Raw audio save failed! Recording exists only in memory.", "ERR")

            # 1. Audio pre-processing (VAD, noise reduction, normalization)
            self._set(ICON_PROCESSING, "Processing...")
            try:
                processed = self.audio_processor.process(audio, config.audio.sample_rate)
            except Exception as e:
                log(f"Audio processing failed: {e}", "ERR")
                # Fall back to raw audio (skip VAD/noise reduction/normalization)
                log("Falling back to raw audio for transcription", "WARN")
                from .audio_processor import ProcessedAudio
                processed = ProcessedAudio(
                    audio=audio,
                    raw_audio=audio,
                    has_speech=True,
                    speech_ratio=1.0,
                    peak_level=float(np.max(np.abs(audio))) if len(audio) > 0 else 0.0,
                    duration=len(audio) / config.audio.sample_rate,
                    segments=[(0, len(audio))],
                )

            if not processed.has_speech:
                log("No speech detected (VAD)", "WARN")
                self._show_error("No speech", "No speech detected in recording")
                return

            # Use processed audio for transcription (keep raw_audio reference for retry path)
            audio = processed.audio

            # 2. Long recording segmentation
            if self.transcriber.supports_long_audio:
                # Engine handles long audio natively, no splitting needed
                segments = [audio]
            else:
                segments = self.audio_processor.segment_long_audio(audio, config.audio.sample_rate)

            if len(segments) == 1:
                # Single segment: save processed audio for transcription
                path = self.backup.save_processed_audio(segments[0])
                if not path:
                    self._show_error("Save failed", "Processed audio save failed")
                    return

                raw_text, err = self._transcribe_and_validate(path)
                if err:
                    self._show_error(err, f"Transcription failed: {err}")
                    send_notification("Transcription Failed", err)
                    return
            else:
                # Multi-segment: transcribe each and join
                log(f"Long recording: {len(segments)} segments", "INFO")
                all_text = []
                failed_segments = []
                for i, seg in enumerate(segments):
                    self._set(ICON_PROCESSING, f"Transcribing {i + 1}/{len(segments)}...")
                    path = self.backup.save_audio_segment(seg, i)
                    if not path:
                        log(f"Segment {i} save failed, skipping", "WARN")
                        failed_segments.append(i)
                        continue
                    try:
                        text, seg_err = self.transcriber.transcribe(path)
                    except Exception as e:
                        log(f"Segment {i} transcription error: {e}", "ERR")
                        failed_segments.append(i)
                        continue
                    if seg_err:
                        log(f"Segment {i} transcription failed: {seg_err}", "WARN")
                        failed_segments.append(i)
                        continue
                    if text:
                        cleaned, stripped = strip_hallucination_lines(text)
                        if stripped:
                            log(f"Segment {i}: stripped hallucination", "WARN")
                        if cleaned and not is_hallucination(cleaned):
                            all_text.append(cleaned)

                if failed_segments:
                    log(f"Warning: {len(failed_segments)}/{len(segments)} segments failed: {failed_segments}", "WARN")

                raw_text = " ".join(all_text) if all_text else None
                err = "No speech" if not raw_text else None

                if err:
                    self._show_error(err, f"Transcription failed: {err} (raw audio saved for retry)")
                    send_notification("Transcription Failed", f"{err} (raw audio saved)")
                    return

            self.backup.save_raw(raw_text)
            log(f"Raw: {truncate(raw_text, LOG_TRUNCATE)}", "OK")

            # 3. Grammar correction (lazy reconnect)
            self._check_grammar_connection()
            final_text = self._apply_grammar(raw_text)

            # 4. Copy to clipboard (non-fatal: still save text even if clipboard fails)
            clipboard_ok = self._copy_to_clipboard(final_text, show_error=False)

            # 5. Always save backup text, even if clipboard failed
            self.backup.save_text(final_text)
            self.backup.save_history(raw_text, final_text)

            # 6. Show result
            if clipboard_ok:
                self._show_success(final_text)
                send_notification("Transcription Complete", truncate(final_text, PREVIEW_TRUNCATE))
            else:
                # Clipboard failed but text is saved; user can "Copy Last" to retry
                log(f"Text saved but clipboard failed. Use 'Copy Last' to copy.", "WARN")
                send_notification("Clipboard Failed", "Text saved. Use 'Copy Last' to copy.")

        except Exception as e:
            log(f"Processing error: {e}", "ERR")
            try:
                self._show_error("Error", f"Error: {e}")
                send_notification("Transcription Error", str(e))
            except Exception:
                pass  # Don't let notification/UI errors mask the real problem
        finally:
            # Always clean up state, stop animation, and restart monitoring.
            # These must succeed even if everything above failed.
            try:
                self._stop_animation()
            except Exception:
                pass
            with self._state_lock:
                self._busy = False
            try:
                self.recorder.start_monitoring()
            except Exception:
                pass

    def _reset(self, seconds: float):
        """Reset icon to idle after delay."""
        def do_reset():
            if not self._busy and not self.recorder.recording:
                self._set(ICON_IDLE, "Ready")
                self._set_icon(ICON_IMAGE)
        timer = threading.Timer(seconds, do_reset)
        timer.daemon = True
        timer.start()

    def _reset_with_overlay(self, seconds: float):
        """Reset icon and hide overlay after delay."""
        def do_reset():
            if not self._busy and not self.recorder.recording:
                self._set(ICON_IDLE, "Ready")
                self._set_icon(ICON_IMAGE)
                self.overlay.hide()
        timer = threading.Timer(seconds, do_reset)
        timer.daemon = True
        timer.start()

    def _show_error(self, status: str, log_msg: str = None):
        """Display error state in UI."""
        self._set(ICON_ERROR, status)
        self._set_icon(ICON_IMAGE)
        self.overlay.set_status("error")
        if log_msg:
            log(log_msg, "ERR")
        play_sound("Basso")
        self._stop_animation()
        self._reset_with_overlay(ICON_RESET_ERROR)

    def _show_success(self, text: str):
        """Display success state in UI."""
        self._set(ICON_SUCCESS, "Copied!")
        self._set_icon(ICON_IMAGE)
        self._stop_animation()
        self.overlay.set_status("done")
        play_sound("Glass")
        log(f"Copied: {truncate(text, PREVIEW_TRUNCATE)}", "OK")
        self._reset_with_overlay(ICON_RESET_SUCCESS)

    def _copy_to_clipboard(self, text: str, show_error: bool = True) -> bool:
        """Copy text to clipboard. Returns True on success."""
        try:
            subprocess.run(['pbcopy'], input=text.encode(), check=True, timeout=CLIPBOARD_TIMEOUT)
            return True
        except Exception as e:
            log(f"Copy failed: {e}", "ERR")
            if show_error:
                self._show_error("Copy failed", f"Copy failed: {e}")
            return False

    def _check_grammar_connection(self):
        """Check and update grammar backend availability (lazy reconnect)."""
        with self._grammar_lock:
            grammar = self.grammar

        if not self.config.grammar.enabled or grammar is None:
            return
        backend_now = grammar.running()
        if backend_now and not self._grammar_ready:
            log(f"{grammar.name} connected! Grammar correction enabled", "OK")
            self._grammar_ready = True
        elif not backend_now and self._grammar_ready:
            log(f"{grammar.name} disconnected", "WARN")
            self._grammar_ready = False

    def _apply_grammar(self, raw_text: str) -> str:
        """Apply grammar correction if available. Returns final text."""
        with self._grammar_lock:
            grammar = self.grammar
            grammar_ready = self._grammar_ready

        if not self.config.grammar.enabled or not grammar_ready or grammar is None:
            return raw_text

        self._set(ICON_PROCESSING, "Polishing...")
        log("Polishing text...", "AI")
        final_text, g_err = grammar.fix(raw_text)
        if g_err:
            log(f"Grammar fix skipped: {g_err}", "WARN")
            return raw_text
        return final_text

    def _transcribe_and_validate(self, path) -> tuple:
        """Transcribe audio and validate result. Returns (raw_text, error)."""
        self._set(ICON_PROCESSING, "Transcribing...")
        log("Transcribing (this may take a moment)...")
        raw_text, err = self.transcriber.transcribe(path)

        if err:
            log(f"Transcription failed: {err}", "ERR")
            return None, err

        original_text = raw_text
        cleaned_text, stripped = strip_hallucination_lines(raw_text)
        if stripped:
            log(f"Stripped hallucination (raw: {original_text!r} -> {cleaned_text!r})", "WARN")
            raw_text = cleaned_text

        if not raw_text or is_hallucination(raw_text):
            log(f"Rejected as hallucination: {original_text!r}", "WARN")
            return None, "No speech"

        return raw_text, None

    def _retry(self, _):
        """Re-transcribe the last recording."""
        path = self.backup.get_audio()
        if not path or self._busy:
            return

        def go():
            self._busy = True
            self._frame_index = 0
            self._start_animation("processing")
            try:
                self.overlay.set_status("processing")
                self._set(ICON_PROCESSING, "Retrying...")
                log("Retrying...")

                # Transcribe and validate
                raw_text, err = self._transcribe_and_validate(path)
                if err:
                    self._show_error(err, f"Failed: {err}")
                    return

                # Grammar correction (lazy reconnect)
                self._check_grammar_connection()
                final_text = self._apply_grammar(raw_text)

                # Copy to clipboard
                if not self._copy_to_clipboard(final_text):
                    return

                # Success
                self._show_success(final_text)

                # Save
                self.backup.save_text(final_text)
                self.backup.save_history(raw_text, final_text)
            finally:
                self._busy = False

        threading.Thread(target=go, daemon=True).start()

    def _copy(self, _):
        """Copy last transcription to clipboard."""
        text = self.backup.get_text()
        if not text:
            return
        if not self._copy_to_clipboard(text):
            return
        play_sound("Glass")
        self._set(ICON_SUCCESS, "Copied!")
        self._set_icon(ICON_IMAGE)
        log(f"Copied: {truncate(text, LOG_TRUNCATE)}", "OK")
        self._reset(ICON_RESET_SUCCESS)

    def _open_backups(self, _):
        """Open backup folder in Finder."""
        subprocess.run(['open', str(self.config.backup.path)], timeout=5)

    def _open_history(self, _):
        """Open history folder in Finder."""
        subprocess.run(['open', str(self.backup.history_dir)], timeout=5)

    def _open_config(self, _):
        """Open config file in default editor."""
        subprocess.run(['open', str(CONFIG_FILE)], timeout=5)

    def _quit(self, _):
        """Quit application with cleanup."""
        self._cleanup()
        rumps.quit_application()

    def _cleanup(self):
        """Clean up all resources before exit."""
        log("Shutting down...", "INFO")

        # Stop monitor stream before anything else
        self.recorder.stop_monitoring()

        # Cancel any running timer
        if self._max_timer:
            self._max_timer.cancel()
            self._max_timer = None

        # Stop recording if active
        if self.recorder.recording:
            log("Stopping active recording...", "INFO")
            self.recorder.stop()

        # Stop animation and wait for thread to exit
        self._stop_animation()
        if self._anim_thread is not None:
            self._anim_thread.join(timeout=0.5)

        # Stop keyboard listener
        if self._keyboard_listener:
            try:
                self._keyboard_listener.stop()
                log("Keyboard listener stopped", "OK")
            except Exception:
                pass

        # Stop key interceptor
        if self._key_interceptor:
            try:
                self._key_interceptor.stop()
                log("Key interceptor stopped", "OK")
            except Exception:
                pass

        # Hide overlay
        try:
            self.overlay.hide()
        except Exception:
            pass

        # Clean up grammar resources
        with self._grammar_lock:
            grammar = self.grammar
            self.grammar = None
        if grammar is not None:
            try:
                grammar.close()
            except Exception as e:
                log(f"Error closing grammar: {e}", "WARN")

        # Shut down transcription engine (this logs its own messages)
        try:
            self.transcriber.close()
        except Exception as e:
            log(f"Error closing transcription engine: {e}", "ERR")

        log("Goodbye!", "OK")


LOG_FILE = Path.home() / ".whisper" / "service.log"
LOG_MAX_SIZE = 1_000_000  # ~1MB


def _setup_service_logging():
    """Redirect stdout/stderr to service log when not attached to a terminal."""
    if sys.stdout.isatty():
        return
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Truncate if too large
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_SIZE:
        LOG_FILE.write_text("")
    log_fd = open(LOG_FILE, "a", buffering=1, encoding="utf-8")
    sys.stdout = log_fd
    sys.stderr = log_fd


def service_main():
    """Entry point for the service (launched via LaunchAgent or wh start)."""
    _setup_service_logging()

    # Single-instance lock - only one instance can run at a time
    lock_path = str(Path.home() / ".whisper" / "service.lock")
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
    lock_file = os.fdopen(lock_fd, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Local Whisper is already running.", file=sys.stderr)
        sys.exit(0)
    atexit.register(lambda: (fcntl.flock(lock_file, fcntl.LOCK_UN), lock_file.close()))

    config = get_config()

    # Check Accessibility permission first - required for global hotkey.
    # Must run here (in the LaunchAgent process) so macOS prompts for THIS process,
    # not for whatever terminal the user happened to use during setup.
    if not check_accessibility_trusted():
        request_accessibility_permission()  # opens System Settings → Accessibility for this process
        log("Accessibility permission required - System Settings opened", "WARN")
        log("Grant access to this process, then run: wh restart", "WARN")

    # Check microphone permission before anything else
    mic_ok, mic_msg = check_microphone_permission()
    if not mic_ok:
        print()
        print(f"  {C_BOLD}{C_YELLOW}Microphone Permission Required{C_RESET}")
        print()
        print(f"  {mic_msg}")
        print()
        sys.exit(1)

    key_name = config.hotkey.key.upper().replace("_", " ")

    # Always read backend from config - no interactive prompt
    if config.grammar.enabled and config.grammar.backend and config.grammar.backend != "none":
        backend_id = config.grammar.backend
        backend_info = BACKEND_REGISTRY.get(backend_id)
        grammar_info = backend_info.name if backend_info else backend_id
    else:
        config.grammar.enabled = False
        grammar_info = "Disabled"

    print()
    print(f"  {C_BOLD}╭────────────────────────────────────────╮{C_RESET}")
    print(f"  {C_BOLD}│{C_RESET}  {C_CYAN}Whisper{C_RESET} · Voice → Text + Grammar     {C_BOLD}│{C_RESET}")
    print(f"  {C_BOLD}│{C_RESET}  {C_GREEN}100% Local{C_RESET} · No Cloud · Private      {C_BOLD}│{C_RESET}")
    print(f"  {C_BOLD}├────────────────────────────────────────┤{C_RESET}")
    print(f"  {C_BOLD}│{C_RESET}  Double-tap {C_YELLOW}{key_name}{C_RESET} to start       {C_BOLD}│{C_RESET}")
    print(f"  {C_BOLD}│{C_RESET}  Tap once to stop → copy to clipboard {C_BOLD}│{C_RESET}")
    print(f"  {C_BOLD}╰────────────────────────────────────────╯{C_RESET}")
    print()
    print(f"  {C_DIM}Engine:{C_RESET}  {config.transcription.engine}")
    print(f"  {C_DIM}Grammar:{C_RESET} {grammar_info}")
    print(f"  {C_DIM}Config:{C_RESET}  {CONFIG_FILE}")
    print(f"  {C_DIM}Backup:{C_RESET}  {config.backup.path}")
    print()

    app = App()

    def handle_signal(*_):
        app._cleanup()
        rumps.quit_application()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    app.run()


if __name__ == "__main__":
    service_main()

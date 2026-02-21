"""
Whisper - 100% Local Voice Transcription + Grammar Correction

Double-tap Right Option (⌥) to start recording, single tap to stop.
Transcribed and polished text is copied to clipboard.

Architecture:
    Voice -> WhisperKit (localhost:50060) -> Grammar Backend -> Clipboard

Supported grammar backends:
    - apple_intelligence: Apple's on-device Foundation Models (macOS 15+)
    - ollama: Local Ollama server with configurable LLM models

Privacy: All processing on-device. No internet. No cloud. No tracking.
"""

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
    log, play_sound, is_silent, is_hallucination, hide_dock_icon, truncate,
    strip_hallucination_lines, check_microphone_permission,
    ICON_IDLE, ICON_RECORDING, ICON_PROCESSING, ICON_SUCCESS, ICON_ERROR,
    ICON_IMAGE, ICON_FRAMES, ICON_PROCESS_FRAMES, OVERLAY_WAVE_FRAMES,
    ICON_RESET_SUCCESS, ICON_RESET_ERROR, LOG_TRUNCATE, PREVIEW_TRUNCATE,
    ANIM_INTERVAL_RECORDING, ANIM_INTERVAL_PROCESSING, DURATION_UPDATE_INTERVAL,
    CLIPBOARD_TIMEOUT,
    C_RESET, C_BOLD, C_DIM, C_CYAN, C_GREEN, C_YELLOW
)
from .audio import Recorder
from .backup import Backup
from .transcriber import Whisper
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
        self.whisper = Whisper()
        # Only create Grammar if enabled (user selected a backend, not "Disabled")
        self.grammar = Grammar() if self.config.grammar.enabled else None
        self.recorder = Recorder()
        self.overlay = get_overlay()

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
        self.grammar_status = rumps.MenuItem(self._get_grammar_menu_text())
        self.menu = [
            self.status,
            self.grammar_status,
            None,
            rumps.MenuItem("Retry Last", callback=self._retry),
            rumps.MenuItem("Copy Last", callback=self._copy),
            rumps.MenuItem("History", callback=self._open_history),
            None,
            rumps.MenuItem("Backups", callback=self._open_backups),
            rumps.MenuItem("Config", callback=self._open_config),
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

    def _get_grammar_menu_text(self) -> str:
        """Get the grammar status text for the menu."""
        if not self.config.grammar.enabled or self.grammar is None:
            return "Grammar: Disabled"
        return f"Grammar: {self.grammar.name}"

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

        # Start Whisper - required
        if not self.whisper.start():
            self._set(ICON_ERROR, "Whisper failed")
            log("Whisper server failed to start. Exiting.", "ERR")
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

            audio = self.recorder.stop()
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
                return

            if is_silent(audio):
                log("No speech detected (silent)", "WARN")
                self._set(ICON_IDLE, "Ready")
                self._set_icon(ICON_IMAGE)
                self._stop_animation()
                self.overlay.set_status("error")
                play_sound("Basso")
                self._reset_with_overlay(ICON_RESET_ERROR)
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
            self.overlay.update_duration(dur, wave)
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
            # 1. Backup audio
            self._set(ICON_PROCESSING, "Saving...")
            path = self.backup.save_audio(audio)
            if not path:
                self._show_error("Save failed", "Audio save failed")
                return
            log("Audio backed up", "OK")

            # 2. Transcribe and validate
            raw_text, err = self._transcribe_and_validate(path)
            if err:
                self._show_error(err, f"Transcription failed: {err}")
                return

            self.backup.save_raw(raw_text)
            log(f"Raw: {truncate(raw_text, LOG_TRUNCATE)}", "OK")

            # 3. Grammar correction (lazy reconnect)
            self._check_grammar_connection()
            final_text = self._apply_grammar(raw_text)

            # 4. Copy to clipboard
            if not self._copy_to_clipboard(final_text):
                return

            # 5. Success
            self._show_success(final_text)

            # 6. Backup
            self.backup.save_text(final_text)
            self.backup.save_history(raw_text, final_text)

        except Exception as e:
            self._show_error("Error", f"Error: {e}")
        finally:
            with self._state_lock:
                self._busy = False

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

    def _copy_to_clipboard(self, text: str) -> bool:
        """Copy text to clipboard. Returns True on success."""
        try:
            subprocess.run(['pbcopy'], input=text.encode(), check=True, timeout=CLIPBOARD_TIMEOUT)
            return True
        except Exception as e:
            self._show_error("Copy failed", f"Copy failed: {e}")
            return False

    def _check_grammar_connection(self):
        """Check and update grammar backend availability (lazy reconnect)."""
        if not self.config.grammar.enabled or self.grammar is None:
            return
        backend_now = self.grammar.running()
        if backend_now and not self._grammar_ready:
            log(f"{self.grammar.name} connected! Grammar correction enabled", "OK")
            self._grammar_ready = True
        elif not backend_now and self._grammar_ready:
            log(f"{self.grammar.name} disconnected", "WARN")
            self._grammar_ready = False

    def _apply_grammar(self, raw_text: str) -> str:
        """Apply grammar correction if available. Returns final text."""
        if not self.config.grammar.enabled or not self._grammar_ready or self.grammar is None:
            return raw_text

        self._set(ICON_PROCESSING, "Polishing...")
        log("Polishing text...", "AI")
        final_text, g_err = self.grammar.fix(raw_text)
        if g_err:
            log(f"Grammar fix skipped: {g_err}", "WARN")
            return raw_text
        return final_text

    def _transcribe_and_validate(self, path) -> tuple:
        """Transcribe audio and validate result. Returns (raw_text, error)."""
        self._set(ICON_PROCESSING, "Transcribing...")
        log("Transcribing (this may take a moment)...")
        raw_text, err = self.whisper.transcribe(path)

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
        if self.grammar is not None:
            try:
                self.grammar.close()
            except Exception as e:
                log(f"Error closing grammar: {e}", "WARN")

        # Kill WhisperKit server (this logs its own messages)
        try:
            self.whisper.close()
        except Exception as e:
            log(f"Error killing Whisper: {e}", "ERR")

        log("Goodbye!", "OK")


LOG_FILE = Path.home() / ".whisper" / "service.log"
LOG_MAX_SIZE = 1_000_000  # ~1MB


def _setup_service_logging():
    """Redirect stdout/stderr to service log when running as .app bundle."""
    if sys.stdout.isatty():
        return
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Truncate if too large
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_SIZE:
        LOG_FILE.write_text("")
    log_fd = open(LOG_FILE, "a", buffering=1)
    sys.stdout = log_fd
    sys.stderr = log_fd


def service_main():
    """Entry point for the service (launched as .app bundle)."""
    import fcntl, atexit

    _setup_service_logging()

    # Single-instance lock - only one instance can run at a time
    lock_path = "/tmp/local-whisper.lock"
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Local Whisper is already running.", file=sys.stderr)
        sys.exit(0)
    atexit.register(lambda: (fcntl.flock(lock_file, fcntl.LOCK_UN), lock_file.close()))

    config = get_config()

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
    print(f"  {C_DIM}Whisper:{C_RESET} {config.whisper.check_url}")
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

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Recording mixin: keyboard listener, hotkey state machine, recording lifecycle."""

import threading
import time

from pynput import keyboard

from .utils import (
    C_BOLD,
    C_CYAN,
    C_RESET,
    C_YELLOW,
    DURATION_UPDATE_INTERVAL,
    log,
    play_sound,
)


class RecordingMixin:
    """Handles the keyboard listener, hotkey state machine, and recording lifecycle."""

    # ------------------------------------------------------------------
    # Accessibility guide
    # ------------------------------------------------------------------

    def _show_accessibility_guide(self):
        """Print guide for enabling Accessibility permissions."""
        print()
        print(f"  {C_BOLD}{C_YELLOW}Accessibility Permission Required{C_RESET}")
        print()
        print("  Whisper needs Accessibility access to detect hotkeys.")
        print()
        print(f"  {C_BOLD}How to fix:{C_RESET}")
        print(f"  1. Open {C_CYAN}System Settings{C_RESET} -> {C_CYAN}Privacy & Security{C_RESET} -> {C_CYAN}Accessibility{C_RESET}")
        print(f"  2. Click the {C_CYAN}+{C_RESET} button")
        print(f"  3. Add {C_CYAN}Terminal{C_RESET} (or your terminal app: iTerm, VS Code, etc.)")
        print("  4. Restart this app")
        print()

    # ------------------------------------------------------------------
    # Keyboard listener
    # ------------------------------------------------------------------

    def _start_keyboard_listener(self):
        """Start the keyboard listener for hotkey detection."""
        try:
            self._keyboard_listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release,
            )
            self._keyboard_listener.daemon = True
            self._keyboard_listener.start()
        except Exception as e:
            log(f"Keyboard error: {e}", "ERR")
            self._show_accessibility_guide()

    def _on_key_press(self, key):
        """Handle key press for double-tap / single-tap detection."""
        stop_keys = {self._record_key, keyboard.Key.space}

        if self.recorder.recording:
            if key == keyboard.Key.esc:
                self._cancel_recording()
            elif key in stop_keys:
                self._stop_recording()
            return

        if key != self._record_key:
            return

        # Ignore key-repeat spam.
        if self._key_pressed:
            return
        self._key_pressed = True

        current_time = time.time()
        time_since_last = current_time - self._last_tap_time
        self._last_tap_time = current_time

        if time_since_last <= self.config.hotkey.double_tap_threshold:
            if self._hold_timer is not None:
                self._hold_timer.cancel()
                self._hold_timer = None
            self._start_recording()
        else:
            if self._hold_timer is not None:
                self._hold_timer.cancel()
                self._hold_timer = None
            timer = threading.Timer(
                self.config.hotkey.double_tap_threshold,
                self._on_hold_threshold_reached,
            )
            timer.daemon = True
            timer.start()
            self._hold_timer = timer

    def _on_hold_threshold_reached(self):
        """Fired when the record key is held for the hold threshold. Starts hold-to-record."""
        self._hold_timer = None
        with self._state_lock:
            if self._key_pressed and not self.recorder.recording and not self._busy:
                self._hold_recording = True
        if self._hold_recording:
            self._start_recording()

    def _on_key_release(self, key):
        """Handle key release events to reset key pressed state."""
        if key == self._record_key:
            if self._hold_timer is not None:
                self._hold_timer.cancel()
                self._hold_timer = None

            should_stop = False
            with self._state_lock:
                self._key_pressed = False
                if self._hold_recording:
                    self._hold_recording = False
                    should_stop = True

            if should_stop and self.recorder.recording:
                self._stop_recording()

    # ------------------------------------------------------------------
    # Recording lifecycle
    # ------------------------------------------------------------------

    def _on_recording_key(self, keycode: int, flags: int):
        """Called by CGEventTap during recording. All keys are already suppressed.
        Only the three defined keys act; everything else is swallowed silently."""
        if keycode == 53:  # Esc -> cancel without transcribing
            self._cancel_recording()
        elif keycode == 49 or keycode == 61:  # Space or Right Option -> stop + transcribe
            self._stop_recording()
        # Any other key: event suppressed, recording continues undisturbed

    def _cancel_recording(self):
        """Cancel recording without processing or saving."""
        self._hold_recording = False
        if self._key_interceptor:
            self._key_interceptor.set_recording_active(False)
        if self._max_timer:
            self._max_timer.cancel()
            self._max_timer = None
        if not self.recorder.recording:
            return
        self.recorder.stop()
        self.recorder.start_monitoring()
        self._current_status = "Ready"
        self._send_state_update()

    def _start_recording(self):
        """Start audio recording."""
        # Stop TTS immediately if speaking (recording takes priority)
        if self._tts_processor and self._tts_processor.is_speaking():
            self._tts_processor.stop()

        with self._state_lock:
            if self._busy or not self._ready:
                return
            if self.recorder.recording:
                return

            if not self.recorder.start():
                log("Mic error", "ERR")
                self._send_state_error("Mic error")
                play_sound("Basso")
                threading.Timer(
                    2.0,
                    lambda: self._reset_to_idle() if not self._busy and not self.recorder.recording else None,
                ).start()
                return

        if self._key_interceptor:
            self._key_interceptor.set_recording_active(True)

        play_sound("Pop")
        log("Recording...", "REC")
        self._current_status = "Recording..."
        self._send_state_update()

        # Start duration update thread
        threading.Thread(target=self._update_duration, daemon=True).start()

        # Start max duration timer
        if self.config.audio.max_duration > 0:
            self._max_timer = threading.Timer(
                self.config.audio.max_duration,
                self._auto_stop,
            )
            self._max_timer.daemon = True
            self._max_timer.start()

    def _stop_recording(self):
        """Stop recording and process audio."""
        import numpy as np

        self._hold_recording = False
        if self._key_interceptor:
            self._key_interceptor.set_recording_active(False)
        if self._max_timer:
            self._max_timer.cancel()
            self._max_timer = None

        with self._state_lock:
            if not self.recorder.recording:
                return
            if self._busy:
                return

            try:
                audio = self.recorder.stop()
            except Exception as e:
                log(f"Recorder stop error: {e}", "ERR")
                self._send_state_error("Record error")
                play_sound("Basso")
                threading.Timer(2.0, self._reset_to_idle).start()
                self.recorder.start_monitoring()
                return

            dur = len(audio) / self.config.audio.sample_rate if len(audio) > 0 else 0

            # Reject empty recordings
            if len(audio) == 0:
                log("No audio captured", "WARN")
                self._send_state_error("No audio")
                play_sound("Basso")
                threading.Timer(2.0, self._reset_to_idle).start()
                self.recorder.start_monitoring()
                return

            # Detect all-zeros audio (mic permission issue)
            if np.max(np.abs(audio)) == 0:
                log("Mic returned silence - check microphone permissions in System Settings", "ERR")
                self._send_state_error("Mic permission?")
                play_sound("Basso")
                threading.Timer(2.0, self._reset_to_idle).start()
                self.recorder.start_monitoring()
                return

            # Check min_duration
            if self.config.audio.min_duration > 0 and dur < self.config.audio.min_duration:
                log(f"Too short ({dur:.1f}s)", "WARN")
                self._send_state_error("Too short")
                play_sound("Basso")
                threading.Timer(2.0, self._reset_to_idle).start()
                self.recorder.start_monitoring()
                return

            log(f"Recorded {dur:.1f}s", "OK")
            self._busy = True

        # Start processing outside the lock
        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _auto_stop(self):
        """Auto-stop recording when max duration exceeded."""
        if self.recorder.recording:
            log(f"Max duration ({self.config.audio.max_duration}s) reached, stopping", "WARN")
            self._stop_recording()

    def _update_duration(self):
        """Send state updates with current duration and RMS while recording."""
        warned_long = False
        while self.recorder.recording:
            dur = self.recorder.duration
            level = self.recorder.rms_level
            if dur > 1800 and not warned_long:
                log("Recording is very long (>30 min) - consider stopping to avoid memory issues", "WARN")
                warned_long = True
            self.ipc.send({
                "type": "state_update",
                "phase": "recording",
                "duration_seconds": dur,
                "rms_level": level,
                "text": None,
                "status_text": "Recording...",
            })
            time.sleep(DURATION_UPDATE_INTERVAL)

    def _reset_to_idle(self):
        """Send idle state to Swift."""
        if not self._busy and not self.recorder.recording:
            self._current_status = "Ready"
            self.ipc.send({
                "type": "state_update",
                "phase": "idle",
                "duration_seconds": 0.0,
                "rms_level": 0.0,
                "text": None,
                "status_text": "Ready",
            })

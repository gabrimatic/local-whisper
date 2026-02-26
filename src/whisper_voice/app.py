# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Whisper - 100% Local Voice Transcription + Grammar Correction

Headless background service. All UI is owned by the Swift app.
Communication with Swift happens over a Unix domain socket (IPC).

Double-tap Right Option to start recording, single tap to stop.
Transcribed and polished text is copied to clipboard.

Architecture:
    Voice -> Transcription Engine (Qwen3-ASR by default) -> Grammar Backend -> Clipboard
    IPC <-> Swift UI (state updates, history, config snapshots, actions)

Supported grammar backends:
    - apple_intelligence: Apple's on-device Foundation Models (macOS 15+)
    - ollama: Local Ollama server with configurable LLM models
    - lm_studio: LM Studio local server (OpenAI-compatible API)

Privacy: All processing on-device. No internet. No cloud. No tracking.
"""

import atexit
import fcntl
import os
import signal
import subprocess
import sys
import threading
import time
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
from pynput import keyboard

from .audio import Recorder
from .audio_processor import AudioProcessor
from .backends import BACKEND_REGISTRY
from .backup import Backup
from .config import CONFIG_FILE, get_config
from .grammar import Grammar
from .ipc_server import IPCServer
from .key_interceptor import KeyInterceptor
from .shortcuts import ShortcutProcessor, build_shortcut_map
from .transcriber import Transcriber
from .utils import (
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_GREEN,
    C_RESET,
    C_YELLOW,
    CLIPBOARD_TIMEOUT,
    DURATION_UPDATE_INTERVAL,
    LOG_TRUNCATE,
    PREVIEW_TRUNCATE,
    check_accessibility_trusted,
    check_microphone_permission,
    is_hallucination,
    log,
    play_sound,
    register_notification_sender,
    request_accessibility_permission,
    send_notification,
    strip_hallucination_lines,
    truncate,
)

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


class App:
    """Headless service. No UI. All state changes go over IPC to Swift."""

    def __init__(self):
        self.config = get_config()
        self.backup = Backup()
        self.transcriber = Transcriber()
        # Only create Grammar if enabled
        self.grammar = Grammar() if self.config.grammar.enabled else None
        self.recorder = Recorder()
        self.audio_processor = AudioProcessor(self.config)

        # State flags
        self._busy = False
        self._ready = False
        self._grammar_ready = False
        self._grammar_last_check: float = 0.0
        self._grammar_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._max_timer = None
        self._last_tap_time = 0.0
        self._key_pressed = False
        self._hold_timer: Optional[threading.Timer] = None
        self._hold_recording: bool = False
        self._current_status = "Starting..."
        self._keyboard_listener = None
        self._record_key = KEY_MAP.get(self.config.hotkey.key, keyboard.Key.alt_r)

        # Shortcut processor for text transformation modes
        self._shortcut_processor: Optional[ShortcutProcessor] = None
        self._shortcut_map: dict = {}
        self._key_interceptor: Optional[KeyInterceptor] = None

        # Swift process handle
        self._swift_process = None

        # Stop event - blocks run() until shutdown
        self._stop_event = threading.Event()
        self._cleaned_up = False

        # IPC server
        self.ipc = IPCServer()
        self.ipc.set_on_connect(self._on_swift_connect)
        self.ipc.set_message_handler(self._handle_ipc_message)
        self.ipc.start()

        register_notification_sender(
            lambda title, body: self.ipc.send({"type": "notification", "title": title, "body": body})
        )

        # Start initialization in background
        threading.Thread(target=self._init, daemon=True).start()

    # ------------------------------------------------------------------
    # IPC helpers
    # ------------------------------------------------------------------

    def _on_swift_connect(self):
        """Called when the Swift client connects. Send initial state."""
        self._send_config_snapshot()
        self._send_state_update()
        self._send_history_update()

    def _send_state_update(self, phase: str = None, status_text: str = None):
        """Send current state to Swift client."""
        if phase is None:
            if self.recorder.recording:
                phase = "recording"
            elif self._busy:
                phase = "processing"
            else:
                phase = "idle"
        self.ipc.send({
            "type": "state_update",
            "phase": phase,
            "duration_seconds": self.recorder.duration if self.recorder.recording else 0.0,
            "rms_level": self.recorder.rms_level if self.recorder.recording else 0.0,
            "text": None,
            "status_text": status_text if status_text is not None else self._current_status,
        })

    def _send_state_done(self, text: str):
        """Send done state with final text."""
        self._current_status = "Copied!"
        self.ipc.send({
            "type": "state_update",
            "phase": "done",
            "duration_seconds": 0.0,
            "rms_level": 0.0,
            "text": text,
            "status_text": "Copied!",
        })

    def _send_state_error(self, msg: str):
        """Send error state."""
        self._current_status = msg
        self.ipc.send({
            "type": "state_update",
            "phase": "error",
            "duration_seconds": 0.0,
            "rms_level": 0.0,
            "text": None,
            "status_text": msg,
        })

    def _send_history_update(self):
        """Send history entries to Swift client."""
        entries = self.backup.get_history(limit=100)
        serialized = []
        audio_history = self.backup.get_audio_history()
        audio_by_stem = {a["path"].stem: str(a["path"]) for a in audio_history}
        for e in entries:
            entry_id = e["path"].stem
            audio_path = audio_by_stem.get(entry_id)
            ts = e["timestamp"]
            ts_float = ts.timestamp() if hasattr(ts, "timestamp") else float(ts)
            serialized.append({
                "id": entry_id,
                "text": e.get("fixed") or e.get("raw", ""),
                "timestamp": ts_float,
                "audio_path": audio_path,
            })
        self.ipc.send({"type": "history_update", "entries": serialized})

    def _send_config_snapshot(self):
        """Send full config snapshot to Swift client."""
        cfg = self.config
        self.ipc.send({"type": "config_snapshot", "config": {
            "hotkey": {
                "key": cfg.hotkey.key,
                "double_tap_threshold": cfg.hotkey.double_tap_threshold,
            },
            "transcription": {"engine": cfg.transcription.engine},
            "qwen3_asr": {
                "model": cfg.qwen3_asr.model,
                "language": cfg.qwen3_asr.language,
                "timeout": cfg.qwen3_asr.timeout,
                "prefill_step_size": cfg.qwen3_asr.prefill_step_size,
            },
            "whisper": {
                "url": cfg.whisper.url,
                "check_url": cfg.whisper.check_url,
                "model": cfg.whisper.model,
                "language": cfg.whisper.language,
                "timeout": cfg.whisper.timeout,
                "prompt": cfg.whisper.prompt,
                "temperature": cfg.whisper.temperature,
                "compression_ratio_threshold": cfg.whisper.compression_ratio_threshold,
                "no_speech_threshold": cfg.whisper.no_speech_threshold,
                "logprob_threshold": cfg.whisper.logprob_threshold,
                "temperature_fallback_count": cfg.whisper.temperature_fallback_count,
                "prompt_preset": cfg.whisper.prompt_preset,
            },
            "grammar": {
                "backend": cfg.grammar.backend,
                "enabled": cfg.grammar.enabled,
            },
            "ollama": {
                "url": cfg.ollama.url,
                "check_url": cfg.ollama.check_url,
                "model": cfg.ollama.model,
                "max_chars": cfg.ollama.max_chars,
                "max_predict": cfg.ollama.max_predict,
                "num_ctx": cfg.ollama.num_ctx,
                "keep_alive": cfg.ollama.keep_alive,
                "timeout": cfg.ollama.timeout,
                "unload_on_exit": cfg.ollama.unload_on_exit,
            },
            "apple_intelligence": {
                "max_chars": cfg.apple_intelligence.max_chars,
                "timeout": cfg.apple_intelligence.timeout,
            },
            "lm_studio": {
                "url": cfg.lm_studio.url,
                "check_url": cfg.lm_studio.check_url,
                "model": cfg.lm_studio.model,
                "max_chars": cfg.lm_studio.max_chars,
                "max_tokens": cfg.lm_studio.max_tokens,
                "timeout": cfg.lm_studio.timeout,
            },
            "audio": {
                "sample_rate": cfg.audio.sample_rate,
                "min_duration": cfg.audio.min_duration,
                "max_duration": cfg.audio.max_duration,
                "min_rms": cfg.audio.min_rms,
                "vad_enabled": cfg.audio.vad_enabled,
                "noise_reduction": cfg.audio.noise_reduction,
                "normalize_audio": cfg.audio.normalize_audio,
                "pre_buffer": cfg.audio.pre_buffer,
            },
            "ui": {
                "show_overlay": cfg.ui.show_overlay,
                "overlay_opacity": cfg.ui.overlay_opacity,
                "sounds_enabled": cfg.ui.sounds_enabled,
                "notifications_enabled": cfg.ui.notifications_enabled,
            },
            "backup": {
                "directory": str(cfg.backup.directory),
                "history_limit": cfg.backup.history_limit,
            },
            "shortcuts": {
                "enabled": cfg.shortcuts.enabled,
                "proofread": cfg.shortcuts.proofread,
                "rewrite": cfg.shortcuts.rewrite,
                "prompt_engineer": cfg.shortcuts.prompt_engineer,
            },
        }})

    def _handle_ipc_message(self, msg: dict):
        """Handle incoming message from Swift client."""
        msg_type = msg.get("type")
        if msg_type == "action":
            action = msg.get("action")
            if action == "retry":
                threading.Thread(target=self._retry, args=(None,), daemon=True).start()
            elif action == "copy":
                threading.Thread(target=self._copy, args=(None,), daemon=True).start()
            elif action == "quit":
                self._quit(None)
            elif action == "reveal":
                file_id = msg.get("id", "")
                audio_path = self.backup.audio_history_dir / f"{file_id}.wav"
                if audio_path.exists():
                    subprocess.Popen(["open", "-R", str(audio_path)])
            elif action == "restart":
                threading.Thread(target=self._restart_service, daemon=True).start()
            elif action == "update":
                threading.Thread(target=self._update_service, daemon=True).start()
        elif msg_type == "engine_switch":
            engine = msg.get("engine", "")
            threading.Thread(target=self._switch_engine, args=(engine,), daemon=True).start()
        elif msg_type == "backend_switch":
            backend = msg.get("backend", "")
            if backend in ("disabled", "none"):
                threading.Thread(target=self._disable_grammar, daemon=True).start()
            else:
                threading.Thread(target=self._switch_backend, args=(backend,), daemon=True).start()
        elif msg_type == "config_update":
            section = msg.get("section", "")
            key = msg.get("key", "")
            value = msg.get("value")
            if section and key and value is not None:
                from .config import update_config_field
                update_config_field(section, key, value)
                self.config = get_config()
                self._send_config_snapshot()

    # ------------------------------------------------------------------
    # Engine / backend switching
    # ------------------------------------------------------------------

    def _switch_engine(self, engine_name: str):
        """Switch transcription engine in-process with rollback on failure."""
        if self._busy:
            log("Cannot switch engine while processing", "WARN")
            return

        from .config import update_config_field
        old_transcriber = self.transcriber
        old_engine_name = old_transcriber.name if old_transcriber is not None else "qwen3_asr"

        self._current_status = f"Loading {engine_name}..."
        self._send_state_update("processing", status_text=f"Loading {engine_name}...")

        try:
            update_config_field("transcription", "engine", engine_name)
            self.config = get_config()

            new_transcriber = Transcriber()
            ok = new_transcriber.start()
            if not ok:
                raise RuntimeError(f"{engine_name} failed to start")

            # Success — swap
            old_transcriber.close()
            self.transcriber = new_transcriber
            self._send_config_snapshot()
            self._current_status = "Ready"
            self._send_state_update("idle", status_text="Ready")
            log(f"Switched engine to {engine_name}", "OK")

        except Exception as e:
            # Rollback: restore config to the old engine
            old_engine_id = self.config.transcription.engine
            try:
                update_config_field("transcription", "engine", old_engine_id if old_transcriber is None else old_engine_id)
            except Exception:
                pass
            # Re-derive old engine id from the transcriber name isn't reliable — restore from backup
            # Best effort: re-read config (which may now be mid-rollback) and force the old engine
            try:
                from .engines import ENGINE_REGISTRY
                for eid, info in ENGINE_REGISTRY.items():
                    if info.name == old_engine_name:
                        update_config_field("transcription", "engine", eid)
                        break
            except Exception:
                pass
            self.config = get_config()

            error_msg = str(e)
            log(f"Engine switch failed: {error_msg}", "ERR")
            self._send_state_error(f"Switch failed: {error_msg}")

            def _reset():
                time.sleep(2)
                if not self._busy and not self.recorder.recording:
                    self._current_status = "Ready"
                    self._send_state_update("idle", status_text="Ready")
            threading.Thread(target=_reset, daemon=True).start()

    def _switch_backend(self, backend_id: str):
        """Switch grammar backend in-process. Runs in background thread."""
        if self._busy:
            log("Cannot switch backend while processing", "WARN")
            return
        from .config import update_config_backend

        info = BACKEND_REGISTRY.get(backend_id)
        display_name = info.name if info else ("Disabled" if backend_id == "none" else backend_id)

        self._current_status = f"Switching to {display_name}..."
        self._send_state_update()

        # Capture current grammar and backend id for rollback
        with self._grammar_lock:
            old_grammar = self.grammar
            old_grammar_ready = self._grammar_ready
        previous_backend_id = self.config.grammar.backend if self.config.grammar.enabled else "none"

        # Disabled case — no need to try a new backend
        if backend_id == "none":
            with self._grammar_lock:
                self.grammar = None
                self._grammar_ready = False
            if old_grammar is not None:
                try:
                    old_grammar.close()
                except Exception as e:
                    log(f"Error closing grammar: {e}", "WARN")
            update_config_backend(backend_id)
            self.config = get_config()
            log("Grammar correction disabled")
            self._current_status = "Ready"
            self._send_state_update()
            self._send_config_snapshot()
            return

        # Update in-memory config so Grammar() initializes the right backend
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
                # Close old backend only after new one is confirmed working
                if old_grammar is not None:
                    try:
                        old_grammar.close()
                    except Exception as e:
                        log(f"Error closing old grammar: {e}", "WARN")
                update_config_backend(backend_id)
                self.grammar = new_grammar
                self._grammar_ready = True
                self._grammar_last_check = time.monotonic()
                if self._shortcut_processor is not None:
                    self._shortcut_processor = ShortcutProcessor(self.grammar, status_callback=self._shortcut_status_callback)
            else:
                # Rollback: restore old grammar and config — don't leave grammar as None
                update_config_backend(previous_backend_id)
                self.grammar = old_grammar
                self._grammar_ready = old_grammar_ready

        self.config = get_config()

        if ok:
            log(f"Switched to {display_name}")
            self._current_status = "Ready"
            self._send_state_update()
            self._send_config_snapshot()
        else:
            log(f"{display_name} unavailable", "ERR")
            self._send_state_error(f"{display_name} unavailable")
            # Send updated config snapshot so Swift reflects the rolled-back backend
            self._send_config_snapshot()
            def _reset_status():
                time.sleep(3.0)
                if not self._busy and not self.recorder.recording:
                    self._current_status = "Ready"
                    self._send_state_update()
            threading.Thread(target=_reset_status, daemon=True).start()

    def _disable_grammar(self):
        """Disable grammar correction."""
        from .config import update_config_field
        update_config_field("grammar", "enabled", False)
        self.config = get_config()
        with self._grammar_lock:
            self._grammar_ready = False
            if self.grammar:
                try:
                    self.grammar.close()
                except Exception:
                    pass
                self.grammar = None
        log("Grammar correction disabled")
        self._send_config_snapshot()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _init(self):
        """Initialize services (runs in background thread)."""
        log("Starting...")
        self._current_status = "Starting servers..."
        self._send_state_update()

        # Start transcription engine - required
        self._current_status = f"Loading {self.transcriber.name}..."
        self._send_state_update("processing", status_text=f"Loading {self.transcriber.name}...")
        if not self.transcriber.start():
            log(f"{self.transcriber.name} failed to start. Exiting.", "ERR")
            self._send_state_error(f"{self.transcriber.name} failed")
            self._exit_app()
            return
        self._ready = True

        # Check grammar backend if enabled
        if self.config.grammar.enabled and self.grammar is not None:
            self._current_status = "Initializing grammar..."
            self._send_state_update("processing", status_text="Initializing grammar...")
            try:
                self._grammar_ready = self.grammar.start()
            except Exception as e:
                log(f"Grammar backend failed to start: {e}", "ERR")
                self._grammar_ready = False
            if not self._grammar_ready:
                log(f"{self.grammar.name} not available. Continuing with grammar disabled.", "WARN")
                self.grammar = None
        else:
            log("Grammar correction disabled", "INFO")

        # Always start KeyInterceptor for recording-mode key suppression
        self._key_interceptor = KeyInterceptor()
        self._key_interceptor.set_recording_handler(self._on_recording_key)

        # Register text transformation shortcuts if enabled (only when grammar is working)
        if self._grammar_ready and self.grammar is not None and self.config.shortcuts.enabled:
            self._shortcut_processor = ShortcutProcessor(self.grammar, status_callback=self._shortcut_status_callback)
            self._shortcut_map = build_shortcut_map(self.config)
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
            if self._key_interceptor.start():
                log("Key interceptor started (recording-mode suppression active)", "OK")
            else:
                log("Key interceptor failed to start", "WARN")

        self._current_status = "Ready"
        self._send_state_update()
        key_name = self.config.hotkey.key.upper().replace("_", " ")
        log(f"Double-tap {key_name} to record, tap to stop", "OK")

        # Check Accessibility permission
        if not check_accessibility_trusted():
            request_accessibility_permission()
            log("Accessibility permission required - System Settings opened", "WARN")
            log("Enable this process in Accessibility, then run: wh restart", "WARN")

        # Start keyboard listener
        self._start_keyboard_listener()

    def _exit_app(self):
        """Exit the application from any thread."""
        threading.Timer(0.5, self._cleanup).start()

    # ------------------------------------------------------------------
    # Swift UI subprocess
    # ------------------------------------------------------------------

    def _spawn_swift_ui(self):
        """Launch the Swift UI binary as a subprocess."""
        swift_binary = (
            Path.home() / ".whisper" / "LocalWhisperUI.app" / "Contents" / "MacOS" / "LocalWhisperUI"
        )
        if not swift_binary.exists():
            log("Swift UI binary not found. Running headless.")
            return
        try:
            self._swift_process = subprocess.Popen(
                [str(swift_binary)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log(f"Swift UI started (pid {self._swift_process.pid})")
        except Exception as e:
            log(f"Failed to spawn Swift UI: {e}")

    def run(self):
        """Spawn Swift UI and block until stop."""
        self._spawn_swift_ui()
        self._stop_event.wait()

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

    def _on_key_press(self, key):
        """Handle key press events for double-tap / single-tap detection."""
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

        # Ignore key repeat events
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
        if keycode == 53:  # Esc → cancel without transcribing
            self._cancel_recording()
        elif keycode == 49 or keycode == 61:  # Space or Right Option → stop + transcribe
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

    # ------------------------------------------------------------------
    # Processing pipeline
    # ------------------------------------------------------------------

    def _process(self, audio):
        """Process recorded audio: transcribe, fix grammar, copy to clipboard."""
        self._current_status = "Processing..."
        self._send_state_update()
        try:
            config = self.config

            # 0. Save raw audio in background (independent of processing)
            _raw_save_result: list[Path | None] = [None]

            def _save_raw():
                _raw_save_result[0] = self.backup.save_audio(audio)

            _raw_save_thread = threading.Thread(target=_save_raw, daemon=True)
            _raw_save_thread.start()

            # 1. Audio pre-processing (VAD, noise reduction, normalization)
            self._current_status = "Processing..."
            self._send_state_update()
            try:
                processed = self.audio_processor.process(audio, config.audio.sample_rate)
            except Exception as e:
                log(f"Audio processing failed: {e}", "ERR")
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

            _raw_save_thread.join(timeout=5.0)
            if _raw_save_thread.is_alive():
                log("Raw audio save is taking unusually long (I/O slow?)", "WARN")
            elif _raw_save_result[0]:
                log(f"Raw audio saved ({len(audio) / config.audio.sample_rate:.1f}s)", "OK")
            else:
                log("CRITICAL: Raw audio save failed! Recording exists only in memory.", "ERR")

            if not processed.has_speech:
                log("No speech detected (VAD)", "WARN")
                self._show_error("No speech", "No speech detected in recording")
                return

            audio = processed.audio

            # 2. Long recording segmentation
            if self.transcriber.supports_long_audio:
                segments = [audio]
            else:
                segments = self.audio_processor.segment_long_audio(
                    audio, config.audio.sample_rate, segments=processed.segments
                )

            if len(segments) == 1:
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
                log(f"Long recording: {len(segments)} segments", "INFO")
                all_text = []
                failed_segments = []
                for i, seg in enumerate(segments):
                    self._current_status = f"Transcribing {i + 1}/{len(segments)}..."
                    self._send_state_update()
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

            # 3. Grammar correction
            self._check_grammar_connection()
            final_text = self._apply_grammar(raw_text)

            # 4. Copy to clipboard
            clipboard_ok = self._copy_to_clipboard(final_text, show_error=False)

            # 5. Save backup
            self.backup.save_text(final_text)
            self.backup.save_history(raw_text, final_text)

            # 6. Send result
            if clipboard_ok:
                self._show_success(final_text)
                send_notification("Transcription Complete", truncate(final_text, PREVIEW_TRUNCATE))
            else:
                log("Text saved but clipboard failed. Use 'Copy Last' to copy.", "WARN")
                send_notification("Clipboard Failed", "Text saved. Use 'Copy Last' to copy.")

        except Exception as e:
            log(f"Processing error: {e}", "ERR")
            try:
                self._show_error("Error", f"Error: {e}")
                send_notification("Transcription Error", str(e))
            except Exception:
                pass
        finally:
            with self._state_lock:
                self._busy = False
            try:
                self.recorder.start_monitoring()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Result display helpers
    # ------------------------------------------------------------------

    def _show_error(self, status: str, log_msg: str = None):
        """Display error state."""
        if log_msg:
            log(log_msg, "ERR")
        if self.config.ui.sounds_enabled:
            play_sound("Basso")
        if self.config.ui.notifications_enabled:
            send_notification("Error", status)
        self._send_state_error(status)
        threading.Timer(2.0, self._reset_to_idle).start()

    def _show_success(self, text: str):
        """Display success state."""
        if self.config.ui.sounds_enabled:
            play_sound("Glass")
        log(f"Copied: {truncate(text, PREVIEW_TRUNCATE)}", "OK")
        self._send_state_done(text)
        self._send_history_update()
        threading.Timer(1.5, self._reset_to_idle).start()

    # ------------------------------------------------------------------
    # Grammar helpers
    # ------------------------------------------------------------------

    def _check_grammar_connection(self):
        """Check and update grammar backend availability (lazy reconnect)."""
        with self._grammar_lock:
            grammar = self.grammar
        if not self.config.grammar.enabled or grammar is None:
            return

        # TTL cache: skip the expensive running() call if backend was healthy recently
        if self._grammar_ready and (time.monotonic() - self._grammar_last_check) < 30.0:
            return

        backend_now = grammar.running()
        self._grammar_last_check = time.monotonic()

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
        self._current_status = "Polishing..."
        self._send_state_update()
        log("Polishing text...", "AI")
        final_text, g_err = grammar.fix(raw_text)
        if g_err:
            log(f"Grammar fix skipped: {g_err}", "WARN")
            return raw_text
        return final_text

    def _transcribe_and_validate(self, path) -> tuple:
        """Transcribe audio and validate result. Returns (raw_text, error)."""
        self._current_status = "Transcribing..."
        self._send_state_update()
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

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Retry / copy last
    # ------------------------------------------------------------------

    def _retry(self, _):
        """Re-transcribe the last recording."""
        path = self.backup.get_audio()
        if not path:
            return

        with self._state_lock:
            if self._busy:
                return
            self._busy = True

        def go():
            try:
                self._current_status = "Retrying..."
                self._send_state_update()
                log("Retrying...")

                raw_text, err = self._transcribe_and_validate(path)
                if err:
                    self._show_error(err, f"Failed: {err}")
                    return

                self._check_grammar_connection()
                final_text = self._apply_grammar(raw_text)

                if not self._copy_to_clipboard(final_text):
                    return

                self._show_success(final_text)
                self.backup.save_text(final_text)
                self.backup.save_history(raw_text, final_text)
            finally:
                with self._state_lock:
                    self._busy = False

        threading.Thread(target=go, daemon=True).start()

    def _copy(self, _):
        """Copy last transcription to clipboard."""
        text = self.backup.get_text()
        if not text:
            return
        if not self._copy_to_clipboard(text):
            return
        if self.config.ui.sounds_enabled:
            play_sound("Glass")
        log(f"Copied: {truncate(text, LOG_TRUNCATE)}", "OK")
        self._send_state_done(text)
        threading.Timer(1.5, self._reset_to_idle).start()

    # ------------------------------------------------------------------
    # Shortcut status
    # ------------------------------------------------------------------

    def _shortcut_status_callback(self, phase: str, status_text: str):
        """Forward shortcut processor status to Swift via IPC."""
        self.ipc.send({
            "type": "state_update",
            "phase": phase,
            "duration_seconds": 0.0,
            "rms_level": 0.0,
            "text": None,
            "status_text": status_text,
        })

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def _update_service(self):
        """Pull latest changes, update dependencies, rebuild Swift targets, and restart."""
        import shutil

        repo_root = Path(__file__).resolve().parents[2]
        log("Update requested from Swift UI.")

        try:
            # Step 1: git pull
            self._send_state_update("processing", status_text="Updating: pulling latest code...")
            git = shutil.which("git")
            if git:
                result = subprocess.run(
                    [git, "pull"],
                    cwd=str(repo_root),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    log(f"git pull failed: {result.stderr.strip()}", "ERR")
                    self._send_state_update("error", status_text="Update failed: git pull error")
                    return
            else:
                log("git not found - skipping pull")

            # Step 2: update Python dependencies
            self._send_state_update("processing", status_text="Updating: installing dependencies...")
            for candidate in [
                repo_root / ".venv" / "bin" / "python",
                repo_root / "venv" / "bin" / "python",
            ]:
                if candidate.exists():
                    python = str(candidate)
                    break
            else:
                python = sys.executable

            subprocess.run(
                [python, "-m", "pip", "install", "-e", str(repo_root),
                 "--upgrade", "--upgrade-strategy", "eager",
                 "--quiet"],
                timeout=120,
            )

            # Step 3: rebuild Swift targets
            swift = shutil.which("swift")
            if swift:
                # LocalWhisperUI
                self._send_state_update("processing", status_text="Updating: rebuilding...")
                ui_dir = repo_root / "LocalWhisperUI"
                if ui_dir.exists():
                    result = subprocess.run(
                        [swift, "build", "-c", "release"],
                        cwd=str(ui_dir),
                        capture_output=True,
                        timeout=300,
                    )
                    if result.returncode == 0:
                        # Assemble .app bundle
                        built_binary = ui_dir / ".build" / "release" / "LocalWhisperUI"
                        if built_binary.exists():
                            import stat
                            macos_dir = Path.home() / ".whisper" / "LocalWhisperUI.app" / "Contents" / "MacOS"
                            macos_dir.mkdir(parents=True, exist_ok=True)
                            dest = macos_dir / "LocalWhisperUI"
                            shutil.copy2(str(built_binary), str(dest))
                            dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                    else:
                        log("LocalWhisperUI build failed - continuing", "ERR")
            else:
                log("swift not found - skipping Swift rebuild")

            # Step 4: restart via exec
            self._send_state_update("processing", status_text="Restarting...")
            self._restart_service()

        except Exception as e:
            log(f"Update failed: {e}", "ERR")
            self._send_state_update("error", status_text="Update failed")

    # ------------------------------------------------------------------
    # Restart
    # ------------------------------------------------------------------

    def _restart_service(self):
        """Restart the service process via exec."""
        log("Restart requested from Swift UI.")
        self._cleanup()
        sys.stdout.flush()
        sys.stderr.flush()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # ------------------------------------------------------------------
    # Quit / cleanup
    # ------------------------------------------------------------------

    def _quit(self, _):
        """Quit the application with cleanup."""
        self._cleanup()

    def _cleanup(self):
        """Clean up all resources before exit."""
        with self._state_lock:
            if self._cleaned_up:
                return
            self._cleaned_up = True
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

        # Clean up grammar resources
        with self._grammar_lock:
            grammar = self.grammar
            self.grammar = None
        if grammar is not None:
            try:
                grammar.close()
            except Exception as e:
                log(f"Error closing grammar: {e}", "WARN")

        # Shut down transcription engine
        try:
            self.transcriber.close()
        except Exception as e:
            log(f"Error closing transcription engine: {e}", "ERR")

        # Stop IPC server
        try:
            self.ipc.stop()
        except Exception:
            pass

        # Kill Swift UI process if running
        if self._swift_process is not None:
            try:
                self._swift_process.terminate()
                log("Swift UI process terminated", "OK")
            except Exception:
                pass

        log("Goodbye!", "OK")

        # Unblock run()
        self._stop_event.set()


# ---------------------------------------------------------------------------
# Service logging
# ---------------------------------------------------------------------------

LOG_FILE = Path.home() / ".whisper" / "service.log"
LOG_MAX_SIZE = 1_000_000  # ~1MB


def _setup_service_logging():
    """Redirect stdout/stderr to service log when not attached to a terminal."""
    if sys.stdout.isatty():
        return
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_SIZE:
        LOG_FILE.write_text("")
    log_fd = open(LOG_FILE, "a", buffering=1, encoding="utf-8")
    sys.stdout = log_fd
    sys.stderr = log_fd


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def service_main():
    """Entry point for the service (launched via LaunchAgent or wh start)."""
    _setup_service_logging()

    # Single-instance lock
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

    # Check Accessibility permission first
    if not check_accessibility_trusted():
        request_accessibility_permission()
        log("Accessibility permission required - System Settings opened", "WARN")
        log("Grant access to this process, then run: wh restart", "WARN")

    # Check microphone permission
    mic_ok, mic_msg = check_microphone_permission()
    if not mic_ok:
        print()
        print(f"  {C_BOLD}{C_YELLOW}Microphone Permission Required{C_RESET}")
        print()
        print(f"  {mic_msg}")
        print()
        sys.exit(1)

    key_name = config.hotkey.key.upper().replace("_", " ")

    if config.grammar.enabled and config.grammar.backend and config.grammar.backend != "none":
        backend_id = config.grammar.backend
        backend_info = BACKEND_REGISTRY.get(backend_id)
        grammar_info = backend_info.name if backend_info else backend_id
    else:
        config.grammar.enabled = False
        grammar_info = "Disabled"

    print()
    print(f"  {C_BOLD}╭────────────────────────────────────────╮{C_RESET}")
    print(f"  {C_BOLD}│{C_RESET}  {C_CYAN}Whisper{C_RESET} · Voice -> Text + Grammar    {C_BOLD}│{C_RESET}")
    print(f"  {C_BOLD}│{C_RESET}  {C_GREEN}100% Local{C_RESET} · No Cloud · Private      {C_BOLD}│{C_RESET}")
    print(f"  {C_BOLD}├────────────────────────────────────────┤{C_RESET}")
    print(f"  {C_BOLD}│{C_RESET}  Double-tap {C_YELLOW}{key_name}{C_RESET} to start       {C_BOLD}│{C_RESET}")
    print(f"  {C_BOLD}│{C_RESET}  Tap once to stop -> copy to clipboard {C_BOLD}│{C_RESET}")
    print(f"  {C_BOLD}╰────────────────────────────────────────╯{C_RESET}")
    print()
    print(f"  {C_DIM}Engine:{C_RESET}  {config.transcription.engine}")
    print(f"  {C_DIM}Grammar:{C_RESET} {grammar_info}")
    print(f"  {C_DIM}Config:{C_RESET}  {CONFIG_FILE}")
    print(f"  {C_DIM}Backup:{C_RESET}  {config.backup.path}")
    print()

    app = App()

    def handle_signal(*_):
        app._stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    app.run()
    app._cleanup()


if __name__ == "__main__":
    service_main()

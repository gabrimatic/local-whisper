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

from pynput import keyboard

from .app_commands import CommandsMixin
from .app_ipc import IPCMixin
from .app_pipeline import PipelineMixin
from .app_recording import RecordingMixin
from .app_switching import SwitchingMixin
from .audio import Recorder
from .audio_processor import AudioProcessor
from .backends import BACKEND_REGISTRY
from .backup import Backup
from .cmd_server import CommandServer
from .config import CONFIG_FILE, get_config
from .grammar import Grammar
from .ipc_server import IPCServer
from .key_interceptor import KeyInterceptor
from .shortcuts import ShortcutProcessor, build_shortcut_map, parse_shortcut
from .transcriber import Transcriber
from .tts_processor import TTSProcessor
from .utils import (
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_GREEN,
    C_RESET,
    C_YELLOW,
    check_accessibility_trusted,
    check_microphone_permission,
    log,
    register_notification_sender,
    request_accessibility_permission,
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


class App(IPCMixin, RecordingMixin, PipelineMixin, CommandsMixin, SwitchingMixin):
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

        # TTS processor
        self._tts_processor: Optional[TTSProcessor] = None

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

        # Command server for CLI access (wh whisper/listen/transcribe)
        self._cmd_server = CommandServer(self._handle_command)
        self._cmd_server.start()

        register_notification_sender(
            lambda title, body: self.ipc.send({"type": "notification", "title": title, "body": body})
        )

        # Start initialization in background
        threading.Thread(target=self._init, daemon=True).start()

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

        # Register text transformation shortcuts if grammar is ready and shortcuts are enabled
        has_shortcuts = False
        if self._grammar_ready and self.grammar is not None and self.config.shortcuts.enabled:
            self._shortcut_processor = ShortcutProcessor(self.grammar, status_callback=self._shortcut_status_callback)
            self._shortcut_map = build_shortcut_map(self.config)
            for key, (modifiers, mode_id) in self._shortcut_map.items():
                self._key_interceptor.register_shortcut(
                    modifiers, key,
                    lambda mid=mode_id: self._shortcut_processor.trigger(mid)
                )
            has_shortcuts = True

        # Register TTS shortcut if TTS is enabled (independent of grammar)
        has_tts = False
        if self.config.tts.enabled:
            self._tts_processor = TTSProcessor(status_callback=self._tts_status_callback)
            self._key_interceptor.set_speaking_handler(self._tts_processor.stop)
            modifiers, key = parse_shortcut(self.config.tts.speak_shortcut)
            if key:
                self._key_interceptor.register_shortcut(modifiers, key, self._tts_processor.trigger)
                has_tts = True

        # Set enabled guard if any shortcuts are registered
        if has_shortcuts or has_tts:
            self._key_interceptor.set_enabled_guard(
                lambda: (not self.recorder.recording
                         and not self._busy
                         and not (self._shortcut_processor and self._shortcut_processor.is_busy()))
            )

        if self._key_interceptor.start():
            log("Key interceptor started", "OK")
            if has_shortcuts:
                log("Shortcuts: Ctrl+Shift+G (proofread) Ctrl+Shift+R (rewrite) Ctrl+Shift+P (prompt)", "OK")
            if has_tts:
                log(f"TTS: {self.config.tts.speak_shortcut} to speak selected text", "OK")
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
    # Shortcut / TTS status callbacks
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

    def _tts_status_callback(self, phase: str, status_text: str):
        """Forward TTS processor status to Swift via IPC. Also manages Esc interception."""
        if self._key_interceptor:
            self._key_interceptor.set_speaking_active(phase in ("speaking", "processing"))
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

        # Stop TTS processor
        if self._tts_processor:
            try:
                self._tts_processor.close()
                log("TTS processor stopped", "OK")
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

        # Stop command server
        try:
            self._cmd_server.stop()
        except Exception:
            pass

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

    # Check microphone permission with retries to handle the race where
    # setup.sh just granted it and macOS TCC hasn't propagated yet
    mic_ok, mic_msg = check_microphone_permission()
    if not mic_ok:
        for attempt in range(3):
            delay = (attempt + 1) * 3  # 3s, 6s, 9s
            log(f"Microphone not yet granted, retrying in {delay}s... ({attempt + 1}/3)", "WARN")
            time.sleep(delay)
            mic_ok, mic_msg = check_microphone_permission()
            if mic_ok:
                break

    if not mic_ok:
        log(f"Microphone permission denied: {mic_msg}", "ERR")
        log("Grant access: System Settings -> Privacy & Security -> Microphone -> Python", "ERR")
        log("Then run: wh restart", "ERR")
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

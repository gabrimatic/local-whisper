# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""App coordinator. Loads the service mixins and owns `service_main`."""

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

from .app_audio_health import AudioHealthMixin
from .app_commands import CommandsMixin
from .app_ipc import IPCMixin
from .app_pipeline import PipelineMixin
from .app_recording import RecordingMixin
from .app_recovery import RecoveryMixin
from .app_switching import SwitchingMixin
from .audio import Recorder
from .audio_processor import AudioProcessor
from .backends import BACKEND_REGISTRY
from .backup import Backup
from .cli.constants import LOCK_FILE
from .cmd_server import CommandServer
from .config import CONFIG_FILE, get_config
from .grammar import Grammar
from .ipc_server import IPCServer
from .key_interceptor import KEYCODE_FOR_KEY_NAME, KeyInterceptor
from .shortcuts import (
    ShortcutProcessor,
    build_shortcut_map,
    normalize_shortcut,
    parse_shortcut,
    validate_shortcut,
)
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


class App(IPCMixin, RecordingMixin, PipelineMixin, CommandsMixin, SwitchingMixin, AudioHealthMixin, RecoveryMixin):
    """Headless service. No UI. All state changes go over IPC to Swift."""

    def __init__(self):
        self.config = get_config()
        self.backup = Backup()
        self.transcriber = Transcriber()
        try:
            self.grammar = Grammar() if self.config.grammar.enabled else None
        except Exception as e:
            log(f"Grammar backend could not be created: {e}", "ERR")
            self.grammar = None
        self.recorder = Recorder()
        self.audio_processor = AudioProcessor(self.config)

        self._busy = False
        self._settings_operation_active = False
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

        self._shortcut_processor: Optional[ShortcutProcessor] = None
        self._shortcut_processor_grammar = None
        self._rebind_lock = threading.Lock()
        self._key_interceptor: Optional[KeyInterceptor] = None
        self._tts_processor: Optional[TTSProcessor] = None
        self._swift_process = None

        self._stop_event = threading.Event()
        self._cleaned_up = False

        self._last_model_use: float = time.time()
        self._idle_timer: Optional[threading.Timer] = None
        self._models_loaded: bool = True

        self._monitor_heartbeat_timer: Optional[threading.Timer] = None
        self._listener_watchdog_timer: Optional[threading.Timer] = None
        self._download_cancel_lock = threading.Lock()
        self._download_cancel_events: dict[str, threading.Event] = {}

        self.ipc = IPCServer()
        self.ipc.set_on_connect(self._on_swift_connect)
        self.ipc.set_message_handler(self._handle_ipc_message)
        self.ipc.start()

        self._cmd_server = CommandServer(self._handle_command)
        self._cmd_server.start()

        register_notification_sender(
            lambda title, body: self.ipc.send({"type": "notification", "title": title, "body": body})
        )

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

        # Check grammar backend if enabled. When the backend isn't up yet
        # (e.g. Ollama starts after Local Whisper), KEEP the Grammar instance:
        # the lazy reconnect in _check_grammar_connection and the running()
        # probe in ShortcutProcessor recover the moment the backend appears,
        # instead of leaving grammar and transform shortcuts dead all session.
        if self.config.grammar.enabled and self.grammar is not None:
            self._current_status = "Initializing grammar..."
            self._send_state_update("processing", status_text="Initializing grammar...")
            try:
                self._grammar_ready = self.grammar.start()
            except Exception as e:
                log(f"Grammar backend failed to start: {e}", "ERR")
                self._grammar_ready = False
            if not self._grammar_ready:
                log(
                    f"{self.grammar.name} not available yet — will keep checking in the background.",
                    "WARN",
                )
        else:
            log("Grammar correction disabled", "INFO")

        # Always start KeyInterceptor for recording-mode key suppression
        self._key_interceptor = KeyInterceptor()
        self._key_interceptor.set_recording_handler(self._on_recording_key)

        # Create the TTS processor if enabled (its shortcut binds in _rebind_shortcuts)
        if self.config.tts.enabled:
            try:
                self._tts_processor = TTSProcessor(status_callback=self._tts_status_callback)
                self._key_interceptor.set_speaking_handler(self._tts_processor.stop)
            except Exception as e:
                log(f"TTS processor failed to initialize: {e}", "ERR")
                self._tts_processor = None

        # Bind transform + TTS shortcuts and the recording-trigger suppression
        self._rebind_shortcuts()

        if self._key_interceptor.start():
            log("Key interceptor started", "OK")
        else:
            log("Key interceptor failed to start", "WARN")

        # Start the hotkey listener immediately after the interceptor: with a
        # non-modifier trigger (e.g. F6) the interceptor suppresses the key
        # and relies on this listener observing the same events, so the gap
        # between the two must stay minimal. A watchdog restarts the listener
        # if it ever dies.
        self._start_keyboard_listener()
        self._schedule_listener_watchdog()

        self._current_status = "Ready"
        self._send_state_update()
        key_name = self.config.hotkey.key.upper().replace("_", " ")
        log(f"Double-tap {key_name} to copy, hold to paste", "OK")

        # Check Accessibility permission
        if not check_accessibility_trusted():
            request_accessibility_permission()
            log("Accessibility permission required - System Settings opened", "WARN")
            log("Enable this process in Accessibility, then run: wh restart", "WARN")

        # Start idle unload timer
        self._schedule_idle_unload()

        # Start audio monitor heartbeat
        self._schedule_monitor_heartbeat()

        try:
            self._recover_pending_audio()
        except Exception as e:
            log(f"Recovery pass failed to start: {e}", "WARN")

    def _exit_app(self):
        """Exit the application from any thread."""
        threading.Timer(0.5, self._cleanup).start()

    # ------------------------------------------------------------------
    # Shortcut binding (single source of truth)
    # ------------------------------------------------------------------

    def _rebind_shortcuts(self):
        """Rebuild every CGEventTap binding from the current config.

        Called at startup and whenever shortcuts/tts/hotkey/grammar state
        changes, so edits in Settings take effect immediately — no restart.
        """
        interceptor = self._key_interceptor
        if interceptor is None:
            return
        with self._rebind_lock:
            interceptor.clear_shortcuts()
            config = self.config

            with self._grammar_lock:
                grammar = self.grammar

            # A non-modifier recording trigger (e.g. F6) is suppressed by
            # keycode alone, BEFORE binding lookup — any shortcut sharing
            # that key could never fire. Reject such bindings loudly instead
            # of registering dead keys.
            record_key_name = (
                config.hotkey.key if config.hotkey.key in KEYCODE_FOR_KEY_NAME else None
            )

            # Text-transform shortcuts need a grammar backend instance; it
            # does NOT have to be reachable right now — the processor probes
            # running() per trigger and shows "Backend unavailable", so a
            # backend that comes up later starts working without a rebind.
            bindings: dict = {}
            bound_transforms: list[str] = []
            if config.shortcuts.enabled and grammar is not None:
                if self._shortcut_processor is None or self._shortcut_processor_grammar is not grammar:
                    self._shortcut_processor = ShortcutProcessor(
                        grammar, status_callback=self._shortcut_status_callback
                    )
                    self._shortcut_processor_grammar = grammar
                bindings, problems = build_shortcut_map(config)
                for problem in problems:
                    log(f"Shortcut config: {problem}", "WARN")
                for combo in [c for c in bindings if c[0] == record_key_name]:
                    log(
                        f"{bindings[combo]} shortcut uses the recording trigger "
                        f"key '{record_key_name}' — binding skipped",
                        "WARN",
                    )
                    del bindings[combo]
                for (key, modifiers), mode_id in bindings.items():
                    interceptor.register_shortcut(
                        set(modifiers), key,
                        lambda mid=mode_id: self._shortcut_processor.trigger(mid)
                    )
                    bound_transforms.append(
                        f"{normalize_shortcut('+'.join(sorted(modifiers) + [key]))} ({mode_id})"
                    )

            # TTS speak shortcut is independent of grammar.
            if config.tts.enabled and self._tts_processor is not None:
                shortcut = config.tts.speak_shortcut
                error = validate_shortcut(shortcut)
                if error:
                    log(f"TTS shortcut '{shortcut}': {error}", "WARN")
                elif shortcut and shortcut.strip():
                    modifiers, key = parse_shortcut(shortcut)
                    if key == record_key_name:
                        log(
                            f"TTS shortcut '{shortcut}' uses the recording trigger "
                            f"key '{record_key_name}' — TTS shortcut disabled",
                            "WARN",
                        )
                    elif (key, frozenset(modifiers)) in bindings:
                        log(
                            f"TTS shortcut '{shortcut}' conflicts with "
                            f"{bindings[(key, frozenset(modifiers))]} — TTS shortcut disabled",
                            "WARN",
                        )
                    else:
                        interceptor.register_shortcut(modifiers, key, self._tts_processor.trigger)
                        log(f"TTS: {normalize_shortcut(shortcut)} to speak selected text", "OK")

            if bound_transforms:
                log("Shortcuts: " + "  ".join(bound_transforms), "OK")

            # Suppress a non-modifier recording trigger (e.g. F6) so pressing
            # it never leaks a keystroke into the frontmost app. Modifier
            # triggers map to None here and are unaffected.
            interceptor.set_record_keycode(KEYCODE_FOR_KEY_NAME.get(config.hotkey.key))

            # Interception pauses while recording/processing. Capture mode is
            # separate: while the Settings shortcut recorder is armed, bound
            # combos must PASS THROUGH (not be swallowed) so they reach the
            # recorder and it can show its conflict notice.
            interceptor.set_enabled_guard(
                lambda: (not self.recorder.recording
                         and not self._busy
                         and not (self._shortcut_processor and self._shortcut_processor.is_busy()))
            )
            interceptor.set_capture_guard(
                lambda: getattr(self, "_shortcut_capture_paused", False)
            )

    def _set_record_key(self, key_name: str) -> bool:
        """Point the hotkey listener at a new trigger key. Returns False if unknown."""
        new_key = KEY_MAP.get(key_name)
        if new_key is None:
            log(f"Unknown hotkey '{key_name}' — keeping current trigger", "WARN")
            return False
        changed = new_key != self._record_key
        self._record_key = new_key
        self._rebind_shortcuts()
        if changed:
            log(f"Recording trigger is now {key_name.upper().replace('_', ' ')}", "OK")
        return True

    # ------------------------------------------------------------------
    # Idle model management
    # ------------------------------------------------------------------

    def _touch_model_activity(self):
        """Mark models as recently used. Reloads if needed, resets idle timer."""
        self._last_model_use = time.time()
        if not self._models_loaded:
            if not self._reload_models():
                return False
        self._schedule_idle_unload()
        return True

    def _schedule_idle_unload(self):
        """(Re)schedule the idle unload timer."""
        if self._idle_timer:
            self._idle_timer.cancel()
        minutes = self.config.service.idle_unload_minutes
        if minutes <= 0:
            return
        self._idle_timer = threading.Timer(minutes * 60, self._idle_unload)
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _idle_unload(self):
        """Unload models after idle timeout.

        Must hold ``_state_lock`` around the busy check AND the unload so a
        concurrent ``_touch_model_activity`` → ``transcribe()`` path can't
        observe ``_busy=False``, start a transcription, and then have the
        engine nulled out from under it.
        """
        with self._state_lock:
            if self._busy or self.recorder.recording:
                self._schedule_idle_unload()
                return
            log(f"Idle for {int((time.time() - self._last_model_use) / 60)}min — unloading models", "INFO")
            self.transcriber.unload()
            if self._tts_processor:
                self._tts_processor.unload_model()
            self._models_loaded = False

    def _reload_models(self):
        """Reload models that were unloaded due to idle timeout."""
        log("Reloading models...", "INFO")
        self._send_state_update("processing", status_text="Reloading models...")
        if not self.transcriber.ensure_loaded():
            log("Failed to reload transcription engine", "ERR")
            self._send_state_error("Failed to reload engine")
            return False
        self._models_loaded = True
        self._send_state_update()
        log("Models reloaded", "OK")
        return True

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
            # Only swallow Esc system-wide while audio is actually playing.
            # During the (potentially long) processing phase the user's Esc
            # keystrokes belong to their frontmost app.
            self._key_interceptor.set_speaking_active(phase == "speaking")
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
        log("Update requested from Swift UI.")

        if self.recorder.recording or self._busy:
            self._send_state_update("error", status_text="Finish current recording before updating")
            return

        def report(phase: str, status_text: str):
            self._send_state_update(phase, status_text=status_text)

        try:
            from .cli.doctor import cmd_update
            ok = cmd_update(
                status_callback=report,
                restart_callback=self._restart_service,
                wait_after_restart=False,
            )
            if ok:
                self._send_state_done("", status="Update complete")
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

        if self._idle_timer:
            self._idle_timer.cancel()
            self._idle_timer = None

        if self._monitor_heartbeat_timer:
            self._monitor_heartbeat_timer.cancel()
            self._monitor_heartbeat_timer = None

        if self._listener_watchdog_timer:
            self._listener_watchdog_timer.cancel()
            self._listener_watchdog_timer = None

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


def _acquire_service_lock(lock_path: str = LOCK_FILE):
    """Acquire the cross-install service lock, or return None if another service owns it."""
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(str(path), os.O_CREAT | os.O_WRONLY, 0o600)
    lock_file = os.fdopen(lock_fd, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_file.close()
        return None
    return lock_file


def _release_service_lock(lock_file):
    try:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
    finally:
        lock_file.close()


def _service_process_pids() -> list[int]:
    """Return same-user Local Whisper service PIDs, excluding this process."""
    current_pid = os.getpid()
    uid = os.getuid()
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,uid=,command="],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []

    pids: list[int] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        try:
            pid = int(parts[0])
            process_uid = int(parts[1])
        except ValueError:
            continue
        command = parts[2]
        if pid == current_pid or process_uid != uid:
            continue
        if "local-whisper" in command and (" wh _run" in command or "/wh _run" in command):
            pids.append(pid)
    return pids


def _terminate_duplicate_services():
    """Stop legacy duplicate services that used a HOME-scoped lock path."""
    pids = _service_process_pids()
    if not pids:
        return
    log(f"Stopping duplicate Local Whisper services: {', '.join(map(str, pids))}", "WARN")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except PermissionError:
            log(f"Permission denied stopping duplicate service pid {pid}", "WARN")
    deadline = time.time() + 3.0
    remaining = set(pids)
    while remaining and time.time() < deadline:
        for pid in list(remaining):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                remaining.remove(pid)
        time.sleep(0.1)
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
            log(f"Force-killed duplicate Local Whisper service pid {pid}", "WARN")
        except ProcessLookupError:
            pass
        except PermissionError:
            log(f"Permission denied force-killing duplicate service pid {pid}", "WARN")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def service_main():
    """Entry point for the service (launched via LaunchAgent or wh start)."""
    _setup_service_logging()
    log(
        "Runtime identity: "
        f"executable={sys.executable} "
        f"realpath={os.path.realpath(sys.executable)} "
        f"prefix={sys.prefix}",
        "INFO",
    )

    # Older installs shipped a LaunchAgent plist that hard-pinned
    # HF_HUB_OFFLINE=1, which blocked on-demand downloads when users switched
    # engines or enabled TTS mid-session. Clear it in-process so those installs
    # get the fix on next restart without needing to re-run setup.sh.
    os.environ.pop("HF_HUB_OFFLINE", None)

    # Single-instance lock shared by source, pip, and Homebrew installs.
    lock_file = _acquire_service_lock()
    if lock_file is None:
        print("Local Whisper is already running.", file=sys.stderr)
        sys.exit(0)
    atexit.register(_release_service_lock, lock_file)
    _terminate_duplicate_services()

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
        log("Grant access: System Settings -> Privacy & Security -> Microphone -> local-whisper", "ERR")
        log("Then run: wh restart", "ERR")
        # Exit 0 so launchd's KeepAlive doesn't hot-loop on user action.
        sys.exit(0)

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
    print(f"  {C_BOLD}│{C_RESET}  Double-tap {C_YELLOW}{key_name}{C_RESET} to copy        {C_BOLD}│{C_RESET}")
    print(f"  {C_BOLD}│{C_RESET}  Hold {C_YELLOW}{key_name}{C_RESET}, release -> paste      {C_BOLD}│{C_RESET}")
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

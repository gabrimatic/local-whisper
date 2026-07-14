# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""IPC mixin: Swift connect/disconnect handlers, state/history/config push."""

import re
import subprocess
import threading

from .config import (
    add_dictation_command,
    add_replacement,
    add_replacements,
    get_config,
    remove_dictation_command,
    remove_replacement,
)
from .utils import log


def _dictation_defaults() -> dict:
    from .dictation_commands import DEFAULT_COMMANDS
    return dict(DEFAULT_COMMANDS)


# History/audio entry stems look like 20260712_104755_109604 (+ optional _pid).
_ENTRY_ID_RE = re.compile(r"^\d{8}_\d{6}_\d{6}(_\d+)?$")


class IPCMixin:
    """Handles all IPC communication with the Swift client."""

    def _on_swift_connect(self):
        self._send_config_snapshot()
        self._send_engines_status()
        self._send_state_update()
        self._send_history_update()

    def _send_engines_status(self):
        """Broadcast per-engine download/cache state so Swift can render it."""
        from .engines.status import all_engine_statuses
        active = self.config.transcription.engine
        self.ipc.send({
            "type": "engines_status",
            "active": active,
            "engines": all_engine_statuses(active),
        })

    def _send_state_update(self, phase: str = None, status_text: str = None):
        """Send current state to Swift client."""
        if phase is None:
            if self.recorder.recording:
                phase = "recording"
            elif self._busy and not getattr(self, "_settings_operation_active", False):
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

    def _send_state_done(self, text: str, status: str = "Copied!"):
        """Send done state with final text."""
        self._current_status = status
        self.ipc.send({
            "type": "state_update",
            "phase": "done",
            "duration_seconds": 0.0,
            "rms_level": 0.0,
            "text": text,
            "status_text": status,
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

    @staticmethod
    def _stem_time(stem: str):
        """Parse a history stem (YYYYmmdd_HHMMSS_ffffff[_pid]) to a datetime."""
        from datetime import datetime
        parts = stem.split("_")
        if len(parts) < 3:
            return None
        try:
            return datetime.strptime("_".join(parts[:3]), "%Y%m%d_%H%M%S_%f")
        except ValueError:
            return None

    def _send_history_update(self):
        """Send history entries to Swift client."""
        entries = self.backup.get_history(limit=100)
        serialized = []
        audio_history = self.backup.get_audio_history()
        audio_by_stem = {a["path"].stem: str(a["path"]) for a in audio_history}
        # Legacy entries (pre shared-stem) never match exactly: their audio
        # and text stems were minted seconds apart. Fall back to the nearest
        # recording within a small window.
        audio_times = [
            (self._stem_time(a["path"].stem), str(a["path"]))
            for a in audio_history
        ]
        audio_times = [(t, p) for t, p in audio_times if t is not None]

        def nearest_audio(entry_stem: str):
            entry_time = self._stem_time(entry_stem)
            if entry_time is None or not audio_times:
                return None
            best_time, best_path = min(
                audio_times, key=lambda tp: abs((tp[0] - entry_time).total_seconds())
            )
            if abs((best_time - entry_time).total_seconds()) <= 10.0:
                return best_path
            return None

        for e in entries:
            entry_id = e["path"].stem
            audio_path = audio_by_stem.get(entry_id) or nearest_audio(entry_id)
            ts = e["timestamp"]
            ts_float = ts.timestamp() if hasattr(ts, "timestamp") else float(ts)
            fixed = e.get("fixed") or e.get("raw", "")
            raw = e.get("raw", "")
            serialized.append({
                "id": entry_id,
                "text": fixed,
                # What the engine actually heard, pre-dictation/grammar/
                # replacements — lets the UI answer "why did my rule (not)
                # fire". Omitted when identical to the final text.
                "raw": raw if raw and raw != fixed else None,
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
                "hold_threshold": cfg.hotkey.hold_threshold,
            },
            "transcription": {"engine": cfg.transcription.engine},
            "parakeet_v3": {
                "model": cfg.parakeet.model,
                "timeout": cfg.parakeet.timeout,
                "chunk_duration": cfg.parakeet.chunk_duration,
                "overlap_duration": cfg.parakeet.overlap_duration,
                "decoding": cfg.parakeet.decoding,
                "beam_size": cfg.parakeet.beam_size,
                "length_penalty": cfg.parakeet.length_penalty,
                "patience": cfg.parakeet.patience,
                "duration_reward": cfg.parakeet.duration_reward,
                "local_attention": cfg.parakeet.local_attention,
                "local_attention_context_size": cfg.parakeet.local_attention_context_size,
            },
            "qwen3_asr": {
                "model": cfg.qwen3_asr.model,
                "timeout": cfg.qwen3_asr.timeout,
                "temperature": cfg.qwen3_asr.temperature,
                "top_p": cfg.qwen3_asr.top_p,
                "top_k": cfg.qwen3_asr.top_k,
                "repetition_context_size": cfg.qwen3_asr.repetition_context_size,
                "repetition_penalty": cfg.qwen3_asr.repetition_penalty,
                "chunk_duration": cfg.qwen3_asr.chunk_duration,
                "max_tokens": cfg.qwen3_asr.max_tokens,
            },
            "apple_speech": {
                "locale": cfg.apple_speech.locale,
                "timeout": cfg.apple_speech.timeout,
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
                "auto_paste": cfg.ui.auto_paste,
            },
            "backup": {
                "directory": str(cfg.backup.directory),
                "history_limit": cfg.backup.history_limit,
            },
            "service": {
                "idle_unload_minutes": cfg.service.idle_unload_minutes,
            },
            "shortcuts": {
                "enabled": cfg.shortcuts.enabled,
                "proofread": cfg.shortcuts.proofread,
                "rewrite": cfg.shortcuts.rewrite,
                "prompt_engineer": cfg.shortcuts.prompt_engineer,
                "paste_result": cfg.shortcuts.paste_result,
            },
            "tts": {
                "enabled": cfg.tts.enabled,
                "provider": cfg.tts.provider,
                "speak_shortcut": cfg.tts.speak_shortcut,
            },
            "kokoro_tts": {
                "model": cfg.kokoro_tts.model,
                "voice": cfg.kokoro_tts.voice,
            },
            "replacements": {
                "enabled": cfg.replacements.enabled,
                "rules": cfg.replacements.rules,
            },
            "dictation": {
                "enabled": cfg.dictation.enabled,
                "strip_fillers": cfg.dictation.strip_fillers,
                "commands": cfg.dictation.commands,
                # The built-in command set, so the UI can render the real
                # effective list (defaults + overrides) instead of
                # hardcoding its own drifting copy.
                "defaults": _dictation_defaults(),
            },
        }})

    _SHORTCUT_FIELDS = {
        ("shortcuts", "proofread"),
        ("shortcuts", "rewrite"),
        ("shortcuts", "prompt_engineer"),
        ("tts", "speak_shortcut"),
    }

    def _validate_config_update(self, section: str, key: str, value):
        """Validate + canonicalize a config_update value.

        Returns (value, error). On error the update must be rejected and the
        current snapshot re-sent so the UI reverts.
        """
        if (section, key) in self._SHORTCUT_FIELDS:
            from .shortcuts import normalize_shortcut, validate_shortcut
            if not isinstance(value, str):
                return value, "Shortcut must be text"
            error = validate_shortcut(value)
            if error:
                return value, f"Invalid shortcut: {error}"
            return (normalize_shortcut(value) if value.strip() else ""), None
        if section == "hotkey" and key == "key":
            from .config.schema import VALID_HOTKEY_KEYS
            if value not in VALID_HOTKEY_KEYS:
                return value, f"Unknown trigger key: {value}"
        if section == "apple_speech" and key == "locale":
            if not isinstance(value, str) or not value.strip():
                return value, "Choose an Apple SpeechTranscriber locale"
            return value.strip().replace("_", "-"), None
        return value, None

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
                file_id = str(msg.get("id", ""))
                # Validate the stem shape so a hostile id can't traverse
                # outside the audio history directory.
                if _ENTRY_ID_RE.match(file_id):
                    audio_path = self.backup.audio_history_dir / f"{file_id}.wav"
                    if audio_path.exists():
                        subprocess.Popen(["open", "-R", str(audio_path)])
            elif action == "restart":
                threading.Thread(target=self._restart_service, daemon=True).start()
            elif action == "update":
                threading.Thread(target=self._update_service, daemon=True).start()
            elif action == "resync_audio":
                threading.Thread(target=self._resync_audio, daemon=True).start()
            elif action == "cancel_download":
                target = msg.get("id", "")
                threading.Thread(target=self._cancel_download, args=(target,), daemon=True).start()
            elif action == "request_microphone_permission":
                threading.Thread(target=self._request_microphone_permission, daemon=True).start()
            elif action == "request_accessibility_permission":
                threading.Thread(target=self._request_accessibility_permission, daemon=True).start()
        elif msg_type == "engine_switch":
            engine = msg.get("engine", "")
            threading.Thread(target=self._switch_engine, args=(engine,), daemon=True).start()
        elif msg_type == "engine_remove_cache":
            engine = msg.get("engine", "")
            threading.Thread(target=self._remove_engine_cache, args=(engine,), daemon=True).start()
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
                from .config.mutations import config_section_attr
                value, error = self._validate_config_update(section, key, value)
                if error:
                    log(f"Rejected config update {section}.{key}: {error}", "WARN")
                    self._send_state_error(error)
                    # Re-send the snapshot so the UI snaps back to the real value.
                    self._send_config_snapshot()
                    return
                old_value = None
                section_config = getattr(self.config, config_section_attr(section), None)
                if section_config is not None:
                    old_value = getattr(section_config, key, None)
                if not update_config_field(section, key, value):
                    # Write refused (broken config.toml / disk error). The
                    # in-memory value was rolled back — tell the user and
                    # snap the UI back instead of confirming a phantom edit.
                    log(f"Config update failed for {section}.{key}", "ERR")
                    self._send_state_error("Not saved — fix ~/.whisper/config.toml")
                    self._send_config_snapshot()
                    return
                self.config = get_config()
                self._send_config_snapshot()
                # Side effects for settings that drive runtime state. Toggling
                # grammar.enabled must actually initialize or tear down the
                # in-process backend, not just flip a bool in the config file.
                if section == "grammar" and key == "enabled":
                    if value:
                        threading.Thread(
                            target=self._switch_backend,
                            args=(self.config.grammar.backend,),
                            daemon=True,
                        ).start()
                    else:
                        threading.Thread(target=self._disable_grammar, daemon=True).start()
                # Same for tts.enabled: without this, toggling the menu item
                # only rewrote the config file while the TTS processor kept
                # running and ⌥T kept speaking.
                elif section == "tts" and key == "enabled":
                    if value:
                        threading.Thread(target=self._enable_tts, daemon=True).start()
                    else:
                        threading.Thread(target=self._disable_tts, daemon=True).start()
                elif section == "service" and key == "idle_unload_minutes":
                    self._schedule_idle_unload()
                # Shortcut edits take effect immediately: rebuild the event-tap
                # bindings instead of waiting for a service restart.
                elif section == "shortcuts":
                    self._rebind_shortcuts()
                elif section == "tts" and key == "speak_shortcut":
                    self._rebind_shortcuts()
                elif section == "hotkey" and key == "key":
                    self._set_record_key(value)
                elif section in ("parakeet_v3", "qwen3_asr") and key == "model":
                    self._send_engines_status()
                    if section == self.config.transcription.engine:
                        threading.Thread(
                            target=self._switch_engine,
                            args=(section, (section, key, old_value)),
                            daemon=True,
                        ).start()
                elif section == "whisper" and key == "model":
                    if self.config.transcription.engine == "whisperkit":
                        threading.Thread(
                            target=self._switch_engine,
                            args=("whisperkit", (section, key, old_value)),
                            daemon=True,
                        ).start()
                elif section == "apple_speech" and key == "locale":
                    self._send_engines_status()
                    if self.config.transcription.engine == "apple_speech":
                        threading.Thread(
                            target=self._switch_engine,
                            args=("apple_speech", (section, key, old_value)),
                            daemon=True,
                        ).start()
        elif msg_type == "replacement_add":
            spoken = str(msg.get("spoken", "")).strip()
            replacement = str(msg.get("replacement", ""))
            # Empty replacement is legitimate ("delete this word"), and
            # leading/trailing whitespace in the replacement is preserved
            # verbatim (e.g. a " :)" suffix rule). Only the spoken form
            # must be non-blank.
            if spoken:
                if not add_replacement(spoken, replacement):
                    self._send_state_error("Not saved — fix ~/.whisper/config.toml")
                self.config = get_config()
                self._send_config_snapshot()
        elif msg_type == "replacement_remove":
            spoken = msg.get("spoken", "").strip()
            if spoken:
                remove_replacement(spoken)
                self.config = get_config()
                self._send_config_snapshot()
        elif msg_type == "replacement_import":
            raw_rules = msg.get("rules")
            if isinstance(raw_rules, dict):
                # Same contract as replacement_add: only the spoken form must
                # be non-blank. Empty replacements ("delete this word") and
                # padded values are preserved verbatim.
                rules = {
                    str(k).strip(): str(v)
                    for k, v in raw_rules.items()
                    if str(k).strip()
                }
                if rules:
                    if not add_replacements(rules):
                        self._send_state_error("Import not saved — fix ~/.whisper/config.toml")
                    self.config = get_config()
                    self._send_config_snapshot()
        elif msg_type == "replacement_test":
            # Live tester for the Vocabulary panel: run the input through the
            # real replacement engine (same code path dictation uses) so the
            # user can verify a rule actually fires before trusting it.
            from .replacements import apply_replacements
            text = msg.get("text", "")
            output = text
            if isinstance(text, str) and text:
                try:
                    output = apply_replacements(text, self.config.replacements.rules)
                except Exception as e:
                    log(f"Replacement test failed: {e}", "WARN")
            self.ipc.send({
                "type": "replacement_test_result",
                "input": text,
                "output": output,
                "enabled": bool(self.config.replacements.enabled),
            })
        elif msg_type == "dictation_command_add":
            spoken = str(msg.get("spoken", "")).strip()
            replacement = str(msg.get("replacement", ""))
            if spoken:
                if not add_dictation_command(spoken, replacement):
                    self._send_state_error("Not saved — fix ~/.whisper/config.toml")
                self.config = get_config()
                self._send_config_snapshot()
        elif msg_type == "dictation_command_remove":
            spoken = str(msg.get("spoken", "")).strip()
            if spoken:
                remove_dictation_command(spoken)
                self.config = get_config()
                self._send_config_snapshot()
        elif msg_type == "dictation_test":
            # Live tester for the Voice panel: run the input through the real
            # dictation pass (commands + filler stripping, per current config).
            from .dictation_commands import apply_dictation_commands
            text = msg.get("text", "")
            output = text
            if isinstance(text, str) and text:
                try:
                    output = apply_dictation_commands(text)
                except Exception as e:
                    log(f"Dictation test failed: {e}", "WARN")
            self.ipc.send({
                "type": "dictation_test_result",
                "input": text,
                "output": output,
                "enabled": bool(self.config.dictation.enabled),
            })

    def _request_microphone_permission(self):
        from .utils import request_microphone_permission

        ok, msg = request_microphone_permission()
        status = "Microphone access granted" if ok else msg
        self._current_status = status
        self._send_state_update("idle", status_text=status)

    def _request_accessibility_permission(self):
        from .utils import check_accessibility_trusted, request_accessibility_permission

        trusted = check_accessibility_trusted()
        if not trusted:
            trusted = request_accessibility_permission(force=True)
        status = (
            "Accessibility access granted"
            if trusted
            else "Accessibility permission requested"
        )
        self._current_status = status
        self._send_state_update("idle", status_text=status)

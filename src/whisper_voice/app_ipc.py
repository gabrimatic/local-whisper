# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""IPC mixin: Swift connect/disconnect handlers, state/history/config push."""

import subprocess
import threading

from .config import add_replacement, get_config, remove_replacement


class IPCMixin:
    """Handles all IPC communication with the Swift client."""

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
                "auto_paste": cfg.ui.auto_paste,
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
        elif msg_type == "replacement_add":
            spoken = msg.get("spoken", "").strip()
            replacement = msg.get("replacement", "").strip()
            if spoken and replacement:
                add_replacement(spoken, replacement)
                self.config = get_config()
                self._send_config_snapshot()
        elif msg_type == "replacement_remove":
            spoken = msg.get("spoken", "").strip()
            if spoken:
                remove_replacement(spoken)
                self.config = get_config()
                self._send_config_snapshot()

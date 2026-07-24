# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Commands mixin: CLI command socket handlers (whisper, listen, transcribe)."""

import threading
from pathlib import Path

import numpy as np

from .utils import is_hallucination, strip_hallucination_lines


class CommandsMixin:
    """Handles commands arriving over the command socket (wh whisper/listen/transcribe)."""

    # ------------------------------------------------------------------
    # Command socket handler
    # ------------------------------------------------------------------

    def _handle_command(self, request: dict, send: callable):
        """Handle a CLI command from the command socket.

        Requests use the ``action`` key (same vocabulary as responses).
        """
        action = request.get("action")
        stop_event = request.get("_stop_event", threading.Event())

        if action == "whisper":
            self._cmd_whisper(request, send, stop_event)
        elif action == "listen":
            self._cmd_listen(request, send, stop_event)
        elif action == "transcribe":
            self._cmd_transcribe(request, send, stop_event)
        elif action == "status":
            self._cmd_status(send)
        elif action == "reload_config":
            self._cmd_reload_config(send)
        elif action == "stop":
            # Stop is handled by the disconnect watcher in cmd_server
            pass
        else:
            send({"type": "error", "message": f"Unknown command: {action}"})

    def _cmd_reload_config(self, send: callable):
        """Re-read config.toml after an external writer changed it.

        Everything live-reloadable applies immediately (hotkey, shortcuts,
        TTS binding, replacements, dictation commands). Engine and grammar
        backend changes go through their normal switch paths in the
        background — the same code the Settings UI uses.
        """
        import threading as _threading
        import time

        from .config import reload_config
        from .utils import log

        old = self.config
        old_engine = old.transcription.engine
        old_backend = old.grammar.backend if old.grammar.enabled else "none"
        old_tts_enabled = old.tts.enabled

        def _engine_runtime_config(config, engine_id):
            if engine_id == "parakeet_v3":
                return config.parakeet.model
            if engine_id == "qwen3_asr":
                return config.qwen3_asr.model
            if engine_id == "whisperkit":
                return config.whisper.model
            if engine_id == "apple_speech":
                return config.apple_speech.locale
            return None

        old_engine_runtime = _engine_runtime_config(old, old_engine)

        try:
            self.config = reload_config()
        except Exception as e:
            send({"type": "error", "message": f"Reload failed: {e}"})
            return

        new = self.config
        self._set_record_key(new.hotkey.key)  # also rebinds shortcuts
        self._schedule_idle_unload()

        new_backend = new.grammar.backend if new.grammar.enabled else "none"
        backend_changed = new_backend != old_backend
        tts_changed = new.tts.enabled != old_tts_enabled
        engine_changed = new.transcription.engine != old_engine
        active_engine_config_changed = (
            not engine_changed
            and _engine_runtime_config(new, new.transcription.engine) != old_engine_runtime
        )
        engine_needs_switch = engine_changed or active_engine_config_changed

        def _apply_switches():
            # Sequential, and waits out a busy pipeline first: the switch
            # helpers silently refuse while _busy, which would leave the
            # config claiming an engine/backend that never actually loaded.
            deadline = time.time() + 120.0
            while (self._busy or self.recorder.recording) and time.time() < deadline:
                time.sleep(0.5)
            if self._busy or self.recorder.recording:
                log("Reload: service stayed busy — engine/backend switch skipped", "ERR")
                self._send_state_error("Reload switch skipped (busy) — restart to apply")
                return
            if backend_changed:
                if new_backend == "none":
                    self._disable_grammar()
                else:
                    self._switch_backend(new_backend)
            if tts_changed:
                (self._enable_tts if new.tts.enabled else self._disable_tts)()
            if engine_needs_switch:
                self._switch_engine(new.transcription.engine)

        if backend_changed or tts_changed or engine_needs_switch:
            _threading.Thread(target=_apply_switches, daemon=True).start()

        self._send_config_snapshot()
        send({
            "type": "done",
            "success": True,
            "engine_switching": engine_needs_switch,
        })

    def _cmd_status(self, send: callable):
        """Return a lightweight readiness snapshot for update/restart verification."""
        model_running = bool(self.transcriber.running())
        send({
            "type": "done",
            "success": True,
            "ready": bool(self._ready),
            "models_loaded": bool(getattr(self, "_models_loaded", model_running) and model_running),
            "busy": bool(self._busy),
            "recording": bool(self.recorder.recording),
            "engine": self.config.transcription.engine,
        })

    def _cmd_whisper(self, request: dict, send: callable, stop_event: threading.Event):
        """Speak text aloud via TTS."""
        if self._touch_model_activity() is False:
            send({"type": "error", "message": "Model reload failed"})
            return
        text = request.get("text", "").strip()
        if not text:
            send({"type": "error", "message": "No text provided"})
            return

        if not self.config.tts.enabled:
            send({"type": "error", "message": "TTS is disabled in config"})
            return

        send({"type": "started", "action": "whisper"})

        try:
            # Get or create TTS provider (reuse from TTS processor if available)
            if self._tts_processor:
                provider = self._tts_processor.get_provider()
            else:
                from .tts import create_tts_provider
                provider = create_tts_provider(self.config.tts.provider)
                provider.start()

            if provider is None:
                send({"type": "error", "message": "TTS provider unavailable"})
                return

            voice = request.get("voice") or self.config.kokoro_tts.voice
            provider.refresh(self.config.kokoro_tts.model)
            provider.speak(text, stop_event, speaker=voice)

            send({"type": "done", "success": True})
        except Exception as e:
            send({"type": "error", "message": str(e)})

    def _cmd_listen(self, request: dict, send: callable, stop_event: threading.Event):
        """Record from microphone, transcribe, and return text."""
        if self._touch_model_activity() is False:
            send({"type": "error", "message": "Model reload failed"})
            return
        with self._state_lock:
            if self._busy or self.recorder.recording:
                send({"type": "error", "message": "Service is busy"})
                return
            if not self._ready:
                send({"type": "error", "message": "Service not ready"})
                return
            self._busy = True

        max_duration = request.get("max_duration", 0)
        skip_grammar = request.get("raw", False)

        send({"type": "started", "action": "listen"})

        try:
            # Start recording
            if not self.recorder.start():
                message = getattr(self.recorder, "last_error_message", None) or "Microphone error"
                send({"type": "error", "message": message})
                return

            # Wait for stop_event (Ctrl+C on CLI side) or max_duration
            timeout = max_duration if max_duration > 0 else 600
            stop_event.wait(timeout=timeout)

            if not self.recorder.recording:
                send({"type": "error", "message": "Recording ended unexpectedly"})
                return

            audio = self.recorder.stop()

            if len(audio) == 0 or np.max(np.abs(audio)) == 0:
                if len(audio) > 0:
                    self.recorder.reset_audio_host(close_stream=False)
                formatter = getattr(self.recorder, "no_signal_error_message", None)
                message = formatter() if callable(formatter) and len(audio) > 0 else "No audio captured"
                send({"type": "error", "message": message})
                return

            # Process audio
            processed = self.audio_processor.process(audio, self.config.audio.sample_rate)
            if not processed.has_speech:
                send({"type": "error", "message": "No speech detected"})
                return

            # Segment if needed
            if self.transcriber.supports_long_audio:
                segments = [processed.audio]
            else:
                segments = self.audio_processor.segment_long_audio(
                    processed.audio, self.config.audio.sample_rate,
                    segments=processed.segments,
                )

            # Transcribe
            all_text = []
            for seg in segments:
                path = self.backup.save_processed_audio(seg)
                if not path:
                    continue
                text, err = self.transcriber.transcribe(path)
                if err or not text:
                    continue
                cleaned, _ = strip_hallucination_lines(text)
                if cleaned and not is_hallucination(cleaned):
                    all_text.append(cleaned)

            raw_text = " ".join(all_text) if all_text else None
            if not raw_text:
                send({"type": "error", "message": "No speech detected"})
                return

            # Preserve the untouched transcription for the response payload so
            # `raw_text` is actually raw (pre-dictation, pre-grammar, pre-
            # replacements). The user is dictating into a shell, so dictation
            # commands do apply on the processed text — --raw only suppresses
            # grammar correction, matching historical CLI semantics.
            original_raw = raw_text
            processed = self._apply_dictation_commands(raw_text)

            final_text = processed
            if not skip_grammar:
                self._check_grammar_connection()
                final_text = self._apply_grammar(processed)

            final_text = self._apply_replacements(final_text)

            send({"type": "done", "text": final_text, "raw_text": original_raw, "success": True})

        except Exception as e:
            send({"type": "error", "message": str(e)})
        finally:
            if self.recorder.recording:
                self.recorder.stop()
            # Re-arm the pre-recording monitor. self.recorder.start() stops it when the
            # CLI 'listen' begins; without this call it stays off until the next restart.
            try:
                self.recorder.start_monitoring()
            except Exception:
                pass
            with self._state_lock:
                self._busy = False

    def _cmd_transcribe(self, request: dict, send: callable, stop_event: threading.Event):
        """Transcribe an audio file."""
        if self._touch_model_activity() is False:
            send({"type": "error", "message": "Model reload failed"})
            return
        file_path = request.get("path", "").strip()
        if not file_path:
            send({"type": "error", "message": "No file path provided"})
            return

        path = Path(file_path)
        if not path.exists():
            send({"type": "error", "message": f"File not found: {file_path}"})
            return

        skip_grammar = request.get("raw", False)

        with self._state_lock:
            if self._busy:
                send({"type": "error", "message": "Service is busy"})
                return
            if not self._ready:
                send({"type": "error", "message": "Service not ready"})
                return
            self._busy = True

        send({"type": "started", "action": "transcribe"})

        try:
            raw_text, err = self.transcriber.transcribe(str(path))
            if err or not raw_text:
                send({"type": "error", "message": err or "No speech detected"})
                return

            cleaned, _ = strip_hallucination_lines(raw_text)
            if not cleaned or is_hallucination(cleaned):
                send({"type": "error", "message": "No speech detected"})
                return

            # `wh transcribe` points at an arbitrary audio file, so the speaker
            # is almost certainly not dictating with voice commands in mind.
            # Running dictation would turn a literal "period" into a ".". Skip
            # the dictation pass entirely and only run grammar + replacements.
            original_raw = cleaned
            final_text = original_raw
            if not skip_grammar:
                self._check_grammar_connection()
                final_text = self._apply_grammar(original_raw)

            final_text = self._apply_replacements(final_text)

            send({"type": "done", "text": final_text, "raw_text": original_raw, "success": True})

        except Exception as e:
            send({"type": "error", "message": str(e)})
        finally:
            with self._state_lock:
                self._busy = False

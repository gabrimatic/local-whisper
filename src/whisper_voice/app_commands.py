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
        """Handle a CLI command from the command socket."""
        cmd_type = request.get("type")
        stop_event = request.get("_stop_event", threading.Event())

        if cmd_type == "whisper":
            self._cmd_whisper(request, send, stop_event)
        elif cmd_type == "listen":
            self._cmd_listen(request, send, stop_event)
        elif cmd_type == "transcribe":
            self._cmd_transcribe(request, send, stop_event)
        elif cmd_type == "stop":
            # Stop is handled by the disconnect watcher in cmd_server
            pass
        else:
            send({"type": "error", "message": f"Unknown command: {cmd_type}"})

    def _cmd_whisper(self, request: dict, send: callable, stop_event: threading.Event):
        """Speak text aloud via TTS."""
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
                send({"type": "error", "message": "Microphone error"})
                return

            # Wait for stop_event (Ctrl+C on CLI side) or max_duration
            timeout = max_duration if max_duration > 0 else 600
            stop_event.wait(timeout=timeout)

            if not self.recorder.recording:
                send({"type": "error", "message": "Recording ended unexpectedly"})
                return

            audio = self.recorder.stop()

            if len(audio) == 0 or np.max(np.abs(audio)) == 0:
                send({"type": "error", "message": "No audio captured"})
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

            # Grammar
            final_text = raw_text
            if not skip_grammar:
                self._check_grammar_connection()
                final_text = self._apply_grammar(raw_text)

            # Replacements
            final_text = self._apply_replacements(final_text)

            send({"type": "done", "text": final_text, "raw_text": raw_text, "success": True})

        except Exception as e:
            send({"type": "error", "message": str(e)})
        finally:
            if self.recorder.recording:
                self.recorder.stop()
            with self._state_lock:
                self._busy = False

    def _cmd_transcribe(self, request: dict, send: callable, stop_event: threading.Event):
        """Transcribe an audio file."""
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

            raw_text = cleaned
            final_text = raw_text
            if not skip_grammar:
                self._check_grammar_connection()
                final_text = self._apply_grammar(raw_text)

            final_text = self._apply_replacements(final_text)

            send({"type": "done", "text": final_text, "raw_text": raw_text, "success": True})

        except Exception as e:
            send({"type": "error", "message": str(e)})
        finally:
            with self._state_lock:
                self._busy = False

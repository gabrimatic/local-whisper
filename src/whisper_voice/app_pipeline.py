# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Pipeline mixin: audio processing, transcription, grammar, clipboard, retry/copy."""

import re
import subprocess
import threading
import time

import numpy as np

from .utils import (
    CLIPBOARD_TIMEOUT,
    LOG_TRUNCATE,
    PREVIEW_TRUNCATE,
    is_hallucination,
    log,
    play_sound,
    send_notification,
    strip_hallucination_lines,
    truncate,
)


class PipelineMixin:
    """Handles the full transcription pipeline and clipboard output."""

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
            _raw_save_result: list = [None]

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

            # 4. Vocabulary replacements (last text transformation)
            final_text = self._apply_replacements(final_text)

            # 5. Copy to clipboard / auto-paste
            if config.ui.auto_paste:
                clipboard_ok = self._paste_text_at_cursor(final_text)
            else:
                clipboard_ok = self._copy_to_clipboard(final_text, show_error=False)

            # 6. Save backup
            self.backup.save_text(final_text)
            self.backup.save_history(raw_text, final_text)

            # 7. Send result
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
        if self.config.ui.auto_paste:
            log(f"Pasted: {truncate(text, PREVIEW_TRUNCATE)}", "OK")
            self._send_state_done(text, status="Pasted!")
        else:
            log(f"Copied: {truncate(text, PREVIEW_TRUNCATE)}", "OK")
            self._send_state_done(text, status="Copied!")
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

    def _apply_replacements(self, text: str) -> str:
        """Apply vocabulary replacement rules. Case-insensitive, word-boundary-aware."""
        rules = self.config.replacements.rules
        if not self.config.replacements.enabled or not rules:
            return text
        for spoken, replacement in rules.items():
            text = re.sub(r'\b' + re.escape(spoken) + r'\b', replacement, text, flags=re.IGNORECASE)
        return text

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

    def _paste_text_at_cursor(self, text: str) -> bool:
        """Paste text at the current cursor position without permanently modifying the clipboard.

        Saves the current clipboard, temporarily puts the text in it, simulates Cmd+V,
        then restores the original clipboard content.
        """
        try:
            saved = subprocess.run(['pbpaste'], capture_output=True, timeout=CLIPBOARD_TIMEOUT)
            saved_content = saved.stdout if saved.returncode == 0 else None

            subprocess.run(['pbcopy'], input=text.encode(), check=True, timeout=CLIPBOARD_TIMEOUT)
            time.sleep(0.05)

            result = subprocess.run(
                ['osascript', '-e', 'tell application "System Events" to keystroke "v" using command down'],
                capture_output=True, timeout=CLIPBOARD_TIMEOUT
            )
            if result.returncode != 0:
                log(f"Auto-paste keystroke failed (code={result.returncode})", "ERR")
                if saved_content is not None:
                    subprocess.run(['pbcopy'], input=saved_content, timeout=CLIPBOARD_TIMEOUT)
                return False

            time.sleep(0.4)

            if saved_content is not None:
                restore = subprocess.run(['pbcopy'], input=saved_content, timeout=CLIPBOARD_TIMEOUT)
                if restore.returncode != 0:
                    log("Auto-paste: clipboard restore failed", "WARN")

            log("Auto-pasted at cursor", "OK")
            return True
        except Exception as e:
            log(f"Auto-paste failed: {e}", "ERR")
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

                final_text = self._apply_replacements(final_text)

                if self.config.ui.auto_paste:
                    ok = self._paste_text_at_cursor(final_text)
                else:
                    ok = self._copy_to_clipboard(final_text)
                if not ok:
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

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Pipeline mixin: audio processing, transcription, grammar, clipboard, retry/copy."""

import re
import subprocess
import threading
import time

import numpy as np

from . import recovery
from .dictation_commands import apply_dictation_commands
from .long_session import LONG_SESSION_THRESHOLD_SECONDS, SessionChunk, SessionLog
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
from .watchdog import TimedOut, run_with_timeout

_TRANSCRIBE_WATCHDOG_SECONDS = 20 * 60
_GRAMMAR_WATCHDOG_SECONDS = 90
_PASTE_WATCHDOG_SECONDS = 8
_MIN_CLIP_SECONDS = 0.5


class PipelineMixin:
    """Handles the full transcription pipeline and clipboard output."""

    # ------------------------------------------------------------------
    # Processing pipeline
    # ------------------------------------------------------------------

    def _process(self, audio):
        """Process recorded audio: transcribe, fix grammar, copy to clipboard."""
        self._touch_model_activity()
        self._current_status = "Processing..."
        self._send_state_update()
        marker_written = False
        try:
            config = self.config

            # 0a. Reject accidental short taps before running VAD/STFT/engine.
            clip_seconds = len(audio) / config.audio.sample_rate if len(audio) else 0.0
            if clip_seconds < _MIN_CLIP_SECONDS:
                log(f"Clip too short ({clip_seconds:.2f}s) — ignoring", "WARN")
                self._show_error("Too short", f"Clip too short ({clip_seconds:.2f}s)")
                return

            # 0. Save raw audio in background (independent of processing)
            _raw_save_result: list = [None]

            def _save_raw():
                _raw_save_result[0] = self.backup.save_audio(audio)

            _raw_save_thread = threading.Thread(target=_save_raw, daemon=True)
            _raw_save_thread.start()

            recovery.mark_processing(self.backup.audio_path)
            marker_written = True

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
            duration_seconds = len(audio) / config.audio.sample_rate

            # 2. Route short vs long sessions differently. Long sessions
            # persist each chunk's transcription before moving on to the
            # next so a mid-session crash loses at most one chunk of work.
            is_long = duration_seconds >= LONG_SESSION_THRESHOLD_SECONDS
            if is_long:
                original_raw, final_text, err = self._process_long_session(
                    audio, processed, config,
                )
                if err:
                    self._show_error(err, f"Long session failed: {err}")
                    self._notify("Transcription Failed", err)
                    return
                self.backup.save_raw(original_raw)
                log(f"Raw: {truncate(original_raw, LOG_TRUNCATE)}", "OK")
            else:
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
                        self._notify("Transcription Failed", err)
                        return
                else:
                    raw_text, err = self._transcribe_segments(segments)
                    if err:
                        self._show_error(err, f"Transcription failed: {err} (raw audio saved for retry)")
                        self._notify("Transcription Failed", f"{err} (raw audio saved)")
                        return

                self.backup.save_raw(raw_text)
                log(f"Raw: {truncate(raw_text, LOG_TRUNCATE)}", "OK")

                # Snapshot before dictation mutates raw_text.
                original_raw = raw_text

                # 3. Dictation commands (before grammar so grammar sees punctuation we inserted)
                raw_text = self._apply_dictation_commands(raw_text)

                # 4. Grammar correction
                self._check_grammar_connection()
                final_text = self._apply_grammar(raw_text)

                # 5. Vocabulary replacements (last text transformation)
                final_text = self._apply_replacements(final_text)

            # 6. Copy to clipboard / auto-paste
            if config.ui.auto_paste:
                clipboard_ok = self._paste_text_at_cursor(final_text)
            else:
                clipboard_ok = self._copy_to_clipboard(final_text, show_error=False)

            # 7. Save backup
            self.backup.save_text(final_text)
            self.backup.save_history(original_raw, final_text)

            # 7. Send result
            if clipboard_ok:
                self._show_success(final_text)
                self._notify("Transcription Complete", truncate(final_text, PREVIEW_TRUNCATE))
            else:
                log("Text saved but clipboard failed. Use 'Copy Last' to copy.", "WARN")
                self._notify("Clipboard Failed", "Text saved. Use 'Copy Last' to copy.")

        except Exception as e:
            log(f"Processing error: {e}", "ERR")
            try:
                self._show_error("Error", f"Error: {e}")
                self._notify("Transcription Error", str(e))
            except Exception:
                pass
        finally:
            # Restart the pre-buffer monitor BEFORE releasing _busy so a
            # hotkey press between release and monitor-restart can't race
            # the rebuild against Recorder.start()'s own stop_monitoring.
            with self._state_lock:
                try:
                    self.recorder.start_monitoring()
                except Exception:
                    pass
                self._busy = False
            if marker_written:
                recovery.clear_marker()

    # ------------------------------------------------------------------
    # Result display helpers
    # ------------------------------------------------------------------

    def _notify(self, title: str, body: str):
        if self.config.ui.notifications_enabled:
            send_notification(title, body)

    def _show_error(self, status: str, log_msg: str = None):
        if log_msg:
            log(log_msg, "ERR")
        if self.config.ui.sounds_enabled:
            play_sound("Basso")
        self._notify("Error", status)
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
        """Apply grammar under the watchdog. On any failure deliver raw_text."""
        with self._grammar_lock:
            grammar = self.grammar
            grammar_ready = self._grammar_ready
        if not self.config.grammar.enabled or not grammar_ready or grammar is None:
            return raw_text
        self._current_status = "Polishing..."
        self._send_state_update()
        log("Polishing text...", "AI")
        try:
            result = run_with_timeout(
                grammar.fix,
                raw_text,
                timeout_seconds=_GRAMMAR_WATCHDOG_SECONDS,
                stage="grammar",
            )
        except Exception as e:
            log(f"Grammar fix crashed: {e}", "WARN")
            self._notify("Grammar unavailable", "Delivered raw transcription.")
            return raw_text
        if isinstance(result, TimedOut):
            with self._grammar_lock:
                self._grammar_ready = False
            self._notify("Grammar timed out", "Delivered raw transcription.")
            return raw_text
        final_text, g_err = result
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

    def _apply_dictation_commands(self, text: str) -> str:
        """Apply voice dictation commands (new line, period, scratch that, etc.)."""
        try:
            return apply_dictation_commands(text)
        except Exception as e:
            log(f"Dictation command pass failed: {e}", "WARN")
            return text

    def _transcribe_and_validate(self, path) -> tuple:
        """Transcribe under the watchdog. Returns (raw_text, error)."""
        self._current_status = "Transcribing..."
        self._send_state_update()
        log("Transcribing (this may take a moment)...")
        try:
            result = run_with_timeout(
                self.transcriber.transcribe,
                path,
                timeout_seconds=_TRANSCRIBE_WATCHDOG_SECONDS,
                stage="transcribe",
            )
        except Exception as e:
            return None, f"Transcription crashed: {e}"
        if isinstance(result, TimedOut):
            # Force reload: abandoned worker left MLX state mid-mutation.
            try:
                self.transcriber.reload()
            except Exception as e:
                log(f"Transcriber reload after timeout failed: {e}", "ERR")
            return None, f"Transcription timed out after {result.seconds:.0f}s"
        raw_text, err = result

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
        """Paste via save/Cmd+V/restore, under the watchdog."""
        try:
            ok = run_with_timeout(
                self._paste_text_at_cursor_inner,
                text,
                timeout_seconds=_PASTE_WATCHDOG_SECONDS,
                stage="paste",
            )
        except Exception as e:
            log(f"Auto-paste failed: {e}", "ERR")
            return False
        if isinstance(ok, TimedOut):
            log("Auto-paste timed out", "WARN")
            return False
        return bool(ok)

    def _paste_text_at_cursor_inner(self, text: str) -> bool:
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

    # ------------------------------------------------------------------
    # Long session (chunked transcription + partial persistence)
    # ------------------------------------------------------------------

    def _process_long_session(self, audio, processed, config):
        """Chunked pipeline. Returns (original_raw, final_text, err)."""
        segments = self.audio_processor.segment_long_audio(
            audio, config.audio.sample_rate, segments=processed.segments
        )
        total = len(segments)
        log(f"Long session: {total} chunks, {len(audio) / config.audio.sample_rate:.1f}s total", "INFO")
        self._check_grammar_connection()

        session = SessionLog(total_chunks=total)
        partial_final_parts: list[str] = []
        partial_raw_parts: list[str] = []
        failed: list[int] = []

        for i, seg in enumerate(segments):
            status = f"Long session: chunk {i + 1}/{total}..."
            self._current_status = status
            self._send_state_update("processing", status_text=status)

            path = self.backup.save_audio_segment(seg, i)
            if not path:
                log(f"Chunk {i} save failed, skipping", "WARN")
                failed.append(i)
                continue

            raw_text, err = self._transcribe_and_validate(path)
            if err or not raw_text:
                log(f"Chunk {i} transcription failed: {err or 'empty'}", "WARN")
                failed.append(i)
                continue

            raw_for_history = raw_text
            dictated = self._apply_dictation_commands(raw_text)
            fixed = self._apply_grammar(dictated)
            fixed = self._apply_replacements(fixed)

            chunk = SessionChunk(index=i, text=fixed, raw=raw_for_history, ts=time.time())
            session.append(chunk)
            partial_raw_parts.append(raw_for_history)
            partial_final_parts.append(fixed)
            log(f"Long session chunk {i + 1}/{total}: {truncate(fixed, LOG_TRUNCATE)}", "OK")

        if not partial_final_parts:
            session.close()
            return "", "", "All chunks failed"

        if failed:
            log(f"Long session: {len(failed)}/{total} chunks failed: {failed}", "WARN")

        original_raw = " ".join(partial_raw_parts).strip()
        final_text = " ".join(partial_final_parts).strip()
        session.close()
        return original_raw, final_text, None

    def _transcribe_segments(self, segments):
        """Multi-segment transcription for WhisperKit under the long-session threshold."""
        log(f"Multi-segment transcription: {len(segments)} segments", "INFO")
        all_text: list[str] = []
        failed: list[int] = []
        for i, seg in enumerate(segments):
            self._current_status = f"Transcribing {i + 1}/{len(segments)}..."
            self._send_state_update()
            path = self.backup.save_audio_segment(seg, i)
            if not path:
                log(f"Segment {i} save failed, skipping", "WARN")
                failed.append(i)
                continue
            try:
                result = run_with_timeout(
                    self.transcriber.transcribe,
                    path,
                    timeout_seconds=_TRANSCRIBE_WATCHDOG_SECONDS,
                    stage="transcribe",
                )
            except Exception as e:
                log(f"Segment {i} transcription error: {e}", "ERR")
                failed.append(i)
                continue
            if isinstance(result, TimedOut):
                log(
                    f"Segment {i} transcription timed out after {result.seconds:.0f}s",
                    "ERR",
                )
                try:
                    self.transcriber.reload()
                except Exception as e:
                    log(f"Transcriber reload after segment timeout failed: {e}", "ERR")
                failed.append(i)
                continue
            text, seg_err = result
            if seg_err:
                log(f"Segment {i} transcription failed: {seg_err}", "WARN")
                failed.append(i)
                continue
            if text:
                cleaned, stripped = strip_hallucination_lines(text)
                if stripped:
                    log(f"Segment {i}: stripped hallucination", "WARN")
                if cleaned and not is_hallucination(cleaned):
                    all_text.append(cleaned)
        if failed:
            log(f"Warning: {len(failed)}/{len(segments)} segments failed: {failed}", "WARN")
        raw_text = " ".join(all_text).strip() if all_text else ""
        return (raw_text or None), (None if raw_text else "No speech")

# Crash-recovery entry points live in :mod:`whisper_voice.app_recovery`.

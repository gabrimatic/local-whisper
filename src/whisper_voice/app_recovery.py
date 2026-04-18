# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""RecoveryMixin: replay interrupted transcriptions on startup."""

from __future__ import annotations

import threading

from . import long_session, recovery
from .utils import LOG_TRUNCATE, PREVIEW_TRUNCATE, log, truncate


class RecoveryMixin:
    def _recover_pending_audio(self):
        """Replay anything the last run didn't finish. Long session wins over marker."""
        if self._recover_partial_long_session():
            recovery.clear_marker()
            return

        pending = recovery.pending_recoveries()
        if not pending:
            return

        age = recovery.marker_age_seconds()
        audio_path = pending[0]
        age_note = f" ({age / 60:.1f} min ago)" if age is not None else ""
        log(f"Recovery: resuming interrupted transcription{age_note}: {audio_path.name}", "INFO")
        self._notify("Recovering last recording", "Service restarted mid-transcription.")

        def _go():
            # Hold the busy flag so a user hotkey doesn't fire a concurrent
            # generate() on the same engine (MLX is not thread-safe).
            with self._state_lock:
                if self._busy:
                    log("Recovery skipped — pipeline already busy", "WARN")
                    return
                self._busy = True
            try:
                raw_text, err = self._transcribe_and_validate(audio_path)
                if err or not raw_text:
                    log(f"Recovery: transcription failed ({err or 'empty'})", "WARN")
                    self._notify("Recovery failed", err or "No speech detected")
                    return

                original_raw = raw_text
                raw_text = self._apply_dictation_commands(raw_text)
                self._check_grammar_connection()
                final_text = self._apply_grammar(raw_text)
                final_text = self._apply_replacements(final_text)
                self._copy_to_clipboard(final_text, show_error=False)
                self.backup.save_raw(original_raw)
                self.backup.save_text(final_text)
                self.backup.save_history(original_raw, final_text)
                self._send_history_update()
                self._notify(
                    "Recovered transcription",
                    truncate(final_text, PREVIEW_TRUNCATE),
                )
                log(f"Recovery: restored {truncate(final_text, LOG_TRUNCATE)}", "OK")
            except Exception as e:
                log(f"Recovery: crashed ({e})", "ERR")
                self._notify("Recovery failed", str(e))
            finally:
                recovery.clear_marker()
                with self._state_lock:
                    self._busy = False

        threading.Thread(target=_go, daemon=True).start()

    def _recover_partial_long_session(self) -> bool:
        """Commit any chunks captured by a crashed long session. Returns True if a session file existed."""
        pending = long_session.read_pending_session()
        if pending is None:
            return False

        chunks = pending.get("chunks") or []
        if not chunks:
            long_session.discard_pending_session()
            return True

        total = pending["total_chunks"] or len(chunks)
        raw, final = long_session.format_interrupted_session(chunks, total)
        try:
            self.backup.save_raw(raw)
            self.backup.save_text(final)
            self.backup.save_history(raw, final)
            self._send_history_update()
            self._notify(
                "Recovered long session",
                f"Saved {len(chunks)} of {total} chunks from an interrupted session.",
            )
            log(f"Recovered partial long session: {len(chunks)}/{total} chunks", "OK")
        except Exception as e:
            log(f"Long session recovery failed: {e}", "ERR")
        finally:
            long_session.discard_pending_session()
        return True

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Switching mixin: engine and backend switching with rollback."""

import threading
import time

from .backends import BACKEND_REGISTRY
from .config import get_config
from .grammar import Grammar
from .shortcuts import ShortcutProcessor
from .transcriber import Transcriber
from .utils import log


class SwitchingMixin:
    """Handles in-process engine and grammar backend switching."""

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

        self._current_status = f"Loading {engine_name}..."
        self._send_state_update("processing", status_text=f"Loading {engine_name}...")

        try:
            new_transcriber = Transcriber(engine_id=engine_name)
            ok = new_transcriber.start()
            if not ok:
                raise RuntimeError(f"{engine_name} failed to start")

            # Engine works — now persist and swap
            update_config_field("transcription", "engine", engine_name)
            self.config = get_config()
            old_transcriber.close()
            self.transcriber = new_transcriber
            self._send_config_snapshot()
            self._current_status = "Ready"
            self._send_state_update("idle", status_text="Ready")
            log(f"Switched engine to {engine_name}", "OK")

        except Exception as e:
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

        # Disabled case -- no need to try a new backend
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
                # Rollback: restore old grammar and config -- don't leave grammar as None
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

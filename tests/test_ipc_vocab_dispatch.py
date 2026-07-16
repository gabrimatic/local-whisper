# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Dispatch-level tests for the vocabulary/dictation/shortcut IPC handlers:
messages go through IPCMixin._handle_ipc_message and must hit the real
mutation entry points, resend snapshots, validate inputs, and trigger live
rebinding side effects."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import whisper_voice.app_ipc as app_ipc
from whisper_voice.app_ipc import IPCMixin


class ImmediateThread:
    def __init__(self, target, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


class FakeApp(IPCMixin):
    pass


@pytest.fixture
def app(monkeypatch):
    app = FakeApp()
    app.config = SimpleNamespace(
        replacements=SimpleNamespace(enabled=True, rules={"open ai": "OpenAI"}),
        dictation=SimpleNamespace(enabled=True, strip_fillers=True, commands={}),
        shortcuts=SimpleNamespace(
            enabled=True, proofread="ctrl+shift+g", rewrite="ctrl+shift+r",
            prompt_engineer="ctrl+shift+p", paste_result=True,
        ),
        hotkey=SimpleNamespace(key="alt_r", double_tap_threshold=0.4, hold_threshold=0.0),
    )
    app.ipc = SimpleNamespace(send=Mock())
    app._send_config_snapshot = Mock()
    app._send_state_error = Mock()
    app._rebind_shortcuts = Mock()
    app._set_record_key = Mock()
    monkeypatch.setattr(app_ipc.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(app_ipc, "get_config", lambda: app.config)
    return app


class TestReplacementDispatch:
    def test_replacement_add_calls_mutation_and_resends_snapshot(self, app, monkeypatch):
        added = Mock(return_value=True)
        monkeypatch.setattr(app_ipc, "add_replacement", added)
        app._handle_ipc_message(
            {"type": "replacement_add", "spoken": "chat gpt", "replacement": "ChatGPT"}
        )
        added.assert_called_once_with("chat gpt", "ChatGPT")
        app._send_config_snapshot.assert_called_once()

    def test_replacement_add_allows_empty_replacement(self, app, monkeypatch):
        # Empty replacement = "delete this word" — a legitimate rule.
        added = Mock(return_value=True)
        monkeypatch.setattr(app_ipc, "add_replacement", added)
        app._handle_ipc_message(
            {"type": "replacement_add", "spoken": "um", "replacement": ""}
        )
        added.assert_called_once_with("um", "")

    def test_replacement_add_preserves_replacement_whitespace(self, app, monkeypatch):
        added = Mock(return_value=True)
        monkeypatch.setattr(app_ipc, "add_replacement", added)
        app._handle_ipc_message(
            {"type": "replacement_add", "spoken": "smiley", "replacement": " :)"}
        )
        added.assert_called_once_with("smiley", " :)")

    def test_replacement_add_blank_spoken_ignored(self, app, monkeypatch):
        added = Mock(return_value=True)
        monkeypatch.setattr(app_ipc, "add_replacement", added)
        app._handle_ipc_message(
            {"type": "replacement_add", "spoken": "   ", "replacement": "x"}
        )
        added.assert_not_called()

    def test_replacement_import_bulk(self, app, monkeypatch):
        # Same contract as replacement_add: only keys are trimmed/required;
        # values pass through verbatim (empty = delete-word, padding kept).
        bulk = Mock(return_value=True)
        monkeypatch.setattr(app_ipc, "add_replacements", bulk)
        app._handle_ipc_message({
            "type": "replacement_import",
            "rules": {"a": "1", " b ": " 2 ", "": "dropped", "um": ""},
        })
        bulk.assert_called_once_with({"a": "1", "b": " 2 ", "um": ""})
        app._send_config_snapshot.assert_called_once()

    def test_replacement_test_roundtrip(self, app):
        app._handle_ipc_message({"type": "replacement_test", "text": "i use open ai"})
        sent = app.ipc.send.call_args[0][0]
        assert sent["type"] == "replacement_test_result"
        assert sent["input"] == "i use open ai"
        assert sent["output"] == "i use OpenAI"
        assert sent["enabled"] is True


class TestDictationDispatch:
    def test_dictation_command_add(self, app, monkeypatch):
        added = Mock(return_value=True)
        monkeypatch.setattr(app_ipc, "add_dictation_command", added)
        app._handle_ipc_message(
            {"type": "dictation_command_add", "spoken": "next bullet", "replacement": "\n- "}
        )
        added.assert_called_once_with("next bullet", "\n- ")
        app._send_config_snapshot.assert_called_once()

    def test_dictation_command_remove(self, app, monkeypatch):
        removed = Mock(return_value=True)
        monkeypatch.setattr(app_ipc, "remove_dictation_command", removed)
        app._handle_ipc_message({"type": "dictation_command_remove", "spoken": "smiley"})
        removed.assert_called_once_with("smiley")

    def test_dictation_test_roundtrip(self, app, monkeypatch):
        monkeypatch.setattr(
            "whisper_voice.dictation_commands.apply_dictation_commands",
            lambda text: "hello, world.",
        )
        app._handle_ipc_message({"type": "dictation_test", "text": "hello comma world period"})
        sent = app.ipc.send.call_args[0][0]
        assert sent["type"] == "dictation_test_result"
        assert sent["output"] == "hello, world."


class TestConfigUpdateValidationAndRebind:
    def test_invalid_shortcut_rejected_and_snapshot_resent(self, app, monkeypatch):
        updated = Mock()
        monkeypatch.setattr("whisper_voice.config.update_config_field", updated)
        app._handle_ipc_message({
            "type": "config_update", "section": "shortcuts",
            "key": "proofread", "value": "banana+g",
        })
        updated.assert_not_called()
        app._send_state_error.assert_called_once()
        app._send_config_snapshot.assert_called_once()

    def test_valid_shortcut_normalized_persisted_and_rebound(self, app, monkeypatch):
        updated = Mock(return_value=True)
        monkeypatch.setattr("whisper_voice.config.update_config_field", updated)
        app._handle_ipc_message({
            "type": "config_update", "section": "shortcuts",
            "key": "proofread", "value": "Shift+Control+K",
        })
        updated.assert_called_once_with("shortcuts", "proofread", "ctrl+shift+k")
        app._rebind_shortcuts.assert_called_once()

    def test_unchanged_value_skips_write_and_side_effects(self, app, monkeypatch):
        # "Shift+Control+G" canonicalizes to the stored "ctrl+shift+g": a
        # no-op must not rewrite config.toml or rebind (and, for engine model
        # fields, must not trigger an engine reload).
        updated = Mock(return_value=True)
        monkeypatch.setattr("whisper_voice.config.update_config_field", updated)
        app._handle_ipc_message({
            "type": "config_update", "section": "shortcuts",
            "key": "proofread", "value": "Shift+Control+G",
        })
        updated.assert_not_called()
        app._rebind_shortcuts.assert_not_called()
        # The raw input differed from the canonical form, so the UI is
        # re-synced to show "ctrl+shift+g" instead of what was typed.
        app._send_config_snapshot.assert_called_once()

    def test_unchanged_canonical_value_skips_snapshot_too(self, app, monkeypatch):
        # A byte-identical no-op (focus-in/focus-out) stays fully silent.
        updated = Mock(return_value=True)
        monkeypatch.setattr("whisper_voice.config.update_config_field", updated)
        app._handle_ipc_message({
            "type": "config_update", "section": "shortcuts",
            "key": "proofread", "value": "ctrl+shift+g",
        })
        updated.assert_not_called()
        app._send_config_snapshot.assert_not_called()


class TestCaptureMode:
    def test_capture_mode_toggles_pause_flag(self, app, monkeypatch):
        # The 30s watchdog timer must not fire inline under the patched
        # threading module.
        class FakeTimer:
            def __init__(self, interval, function):
                self.daemon = False

            def start(self):
                pass

        monkeypatch.setattr(app_ipc.threading, "Timer", FakeTimer)
        app._handle_ipc_message({"type": "capture_mode", "active": True})
        assert app._shortcut_capture_paused is True
        app._handle_ipc_message({"type": "capture_mode", "active": False})
        assert app._shortcut_capture_paused is False

    def test_shortcuts_enabled_toggle_rebinds(self, app, monkeypatch):
        monkeypatch.setattr("whisper_voice.config.update_config_field", Mock(return_value=True))
        app._handle_ipc_message({
            "type": "config_update", "section": "shortcuts",
            "key": "enabled", "value": False,
        })
        app._rebind_shortcuts.assert_called_once()

    def test_tts_speak_shortcut_rebinds(self, app, monkeypatch):
        monkeypatch.setattr("whisper_voice.config.update_config_field", Mock(return_value=True))
        app._handle_ipc_message({
            "type": "config_update", "section": "tts",
            "key": "speak_shortcut", "value": "alt+t",
        })
        app._rebind_shortcuts.assert_called_once()

    def test_hotkey_change_applies_live(self, app, monkeypatch):
        monkeypatch.setattr("whisper_voice.config.update_config_field", Mock(return_value=True))
        app._handle_ipc_message({
            "type": "config_update", "section": "hotkey", "key": "key", "value": "f6",
        })
        app._set_record_key.assert_called_once_with("f6")

    def test_unknown_hotkey_rejected(self, app, monkeypatch):
        updated = Mock()
        monkeypatch.setattr("whisper_voice.config.update_config_field", updated)
        app._handle_ipc_message({
            "type": "config_update", "section": "hotkey", "key": "key", "value": "hyperkey",
        })
        updated.assert_not_called()
        app._send_state_error.assert_called_once()

    def test_empty_shortcut_disables_mode(self, app, monkeypatch):
        updated = Mock(return_value=True)
        monkeypatch.setattr("whisper_voice.config.update_config_field", updated)
        app._handle_ipc_message({
            "type": "config_update", "section": "shortcuts",
            "key": "rewrite", "value": "",
        })
        updated.assert_called_once_with("shortcuts", "rewrite", "")
        app._rebind_shortcuts.assert_called_once()


class TestRevealSanitization:
    def test_traversal_id_rejected(self, app, monkeypatch):
        opened = Mock()
        monkeypatch.setattr(app_ipc.subprocess, "Popen", opened)
        app.backup = SimpleNamespace(audio_history_dir=SimpleNamespace())
        app._handle_ipc_message(
            {"type": "action", "action": "reveal", "id": "../../etc/passwd"}
        )
        opened.assert_not_called()

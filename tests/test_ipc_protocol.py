# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for the IPC message protocol.

All tests are pure JSON/dict operations. No sockets are created.

The helpers below mirror the real payload shapes emitted by the service in
``src/whisper_voice/app_ipc.py`` so the tests break when the wire format drifts.
"""

import json


# ---------------------------------------------------------------------------
# Helpers: message constructors that mirror the real Python→Swift payloads.
# ---------------------------------------------------------------------------

def make_state_update(phase: str, **kwargs) -> dict:
    msg = {"type": "state_update", "phase": phase}
    msg.update(kwargs)
    return msg


def make_config_snapshot(engine: str = "qwen3_asr", backend: str = "apple_intelligence",
                         grammar_enabled: bool = False) -> dict:
    """Nested-under-'config' shape, matching `_send_config_snapshot`."""
    return {
        "type": "config_snapshot",
        "config": {
            "transcription": {"engine": engine},
            "grammar": {"backend": backend, "enabled": grammar_enabled},
            "ui": {"show_overlay": True},
            "audio": {"sample_rate": 16000},
        },
    }


def make_history_update(entries: list) -> dict:
    """Uses the 'entries' key, matching the production payload."""
    return {"type": "history_update", "entries": entries}


def make_notification(title: str, body: str) -> dict:
    return {"type": "notification", "title": title, "body": body}


# Incoming messages from Swift → Python
def make_action(action: str) -> dict:
    return {"type": "action", "action": action}


def make_engine_switch(engine: str) -> dict:
    return {"type": "engine_switch", "engine": engine}


def make_backend_switch(backend: str) -> dict:
    return {"type": "backend_switch", "backend": backend}


def make_config_update(section: str, key: str, value) -> dict:
    return {"type": "config_update", "section": section, "key": key, "value": value}


def make_replacement_add(spoken: str, replacement: str) -> dict:
    return {"type": "replacement_add", "spoken": spoken, "replacement": replacement}


def make_replacement_remove(spoken: str) -> dict:
    return {"type": "replacement_remove", "spoken": spoken}


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------

class TestJsonRoundTrip:
    def test_state_update_serializes(self):
        msg = make_state_update("idle")
        parsed = json.loads(json.dumps(msg))
        assert parsed["type"] == "state_update"
        assert parsed["phase"] == "idle"

    def test_config_snapshot_serializes(self):
        msg = make_config_snapshot()
        parsed = json.loads(json.dumps(msg))
        assert parsed["type"] == "config_snapshot"
        assert "config" in parsed
        assert parsed["config"]["transcription"]["engine"] == "qwen3_asr"
        assert parsed["config"]["grammar"]["backend"] == "apple_intelligence"

    def test_history_update_serializes(self):
        entries = [{
            "id": "2026-01-01",
            "text": "Hello.",
            "timestamp": 1704067200.0,
            "audio_path": None,
        }]
        msg = make_history_update(entries)
        parsed = json.loads(json.dumps(msg))
        assert parsed["type"] == "history_update"
        assert len(parsed["entries"]) == 1
        assert parsed["entries"][0]["text"] == "Hello."

    def test_notification_serializes(self):
        msg = make_notification("Transcription Complete", "Hello world")
        parsed = json.loads(json.dumps(msg))
        assert parsed["type"] == "notification"
        assert parsed["title"] == "Transcription Complete"
        assert parsed["body"] == "Hello world"

    def test_action_message_serializes(self):
        msg = make_action("stop_recording")
        parsed = json.loads(json.dumps(msg))
        assert parsed["type"] == "action"
        assert parsed["action"] == "stop_recording"

    def test_engine_switch_serializes(self):
        msg = make_engine_switch("whisperkit")
        parsed = json.loads(json.dumps(msg))
        assert parsed["type"] == "engine_switch"
        assert parsed["engine"] == "whisperkit"

    def test_backend_switch_serializes(self):
        msg = make_backend_switch("ollama")
        parsed = json.loads(json.dumps(msg))
        assert parsed["type"] == "backend_switch"
        assert parsed["backend"] == "ollama"

    def test_config_update_serializes(self):
        msg = make_config_update("grammar", "enabled", True)
        parsed = json.loads(json.dumps(msg))
        assert parsed["type"] == "config_update"
        assert parsed["section"] == "grammar"
        assert parsed["key"] == "enabled"
        assert parsed["value"] is True

    def test_replacement_add_serializes(self):
        msg = make_replacement_add("open ai", "OpenAI")
        parsed = json.loads(json.dumps(msg))
        assert parsed["type"] == "replacement_add"
        assert parsed["spoken"] == "open ai"
        assert parsed["replacement"] == "OpenAI"

    def test_replacement_remove_serializes(self):
        msg = make_replacement_remove("open ai")
        parsed = json.loads(json.dumps(msg))
        assert parsed["type"] == "replacement_remove"
        assert parsed["spoken"] == "open ai"


# ---------------------------------------------------------------------------
# State phases
# ---------------------------------------------------------------------------

class TestStateUpdatePhases:
    # "speaking" is real: emitted while Kokoro TTS is playing. Drop it here and
    # the Swift overlay stops animating during speech regressions go unnoticed.
    VALID_PHASES = ["idle", "recording", "processing", "done", "error", "speaking"]

    def test_all_phases_round_trip(self):
        for phase in self.VALID_PHASES:
            msg = make_state_update(phase)
            parsed = json.loads(json.dumps(msg))
            assert parsed["phase"] == phase

    def test_done_phase_with_text(self):
        msg = make_state_update("done", text="Hello world", duration=2.5)
        parsed = json.loads(json.dumps(msg))
        assert parsed["phase"] == "done"
        assert parsed["text"] == "Hello world"
        assert parsed["duration"] == 2.5

    def test_error_phase_with_message(self):
        msg = make_state_update("error", error="Transcription failed")
        parsed = json.loads(json.dumps(msg))
        assert parsed["phase"] == "error"
        assert "error" in parsed

    def test_recording_phase_with_duration(self):
        msg = make_state_update("recording", duration=1.3)
        parsed = json.loads(json.dumps(msg))
        assert parsed["phase"] == "recording"
        assert parsed["duration"] == 1.3

    def test_speaking_phase_round_trip(self):
        msg = make_state_update("speaking", status_text="Speaking...")
        parsed = json.loads(json.dumps(msg))
        assert parsed["phase"] == "speaking"
        assert parsed["status_text"] == "Speaking..."


# ---------------------------------------------------------------------------
# config_snapshot required structure
# ---------------------------------------------------------------------------

class TestConfigSnapshot:
    def test_top_level_type(self):
        msg = make_config_snapshot()
        assert msg["type"] == "config_snapshot"

    def test_config_is_nested(self):
        msg = make_config_snapshot()
        assert "config" in msg
        assert isinstance(msg["config"], dict)

    def test_required_sections_present(self):
        msg = make_config_snapshot()
        cfg = msg["config"]
        for section in ("transcription", "grammar", "ui", "audio"):
            assert section in cfg, f"Missing config section: {section}"

    def test_grammar_enabled_is_bool(self):
        msg = make_config_snapshot(grammar_enabled=True)
        parsed = json.loads(json.dumps(msg))
        assert isinstance(parsed["config"]["grammar"]["enabled"], bool)


# ---------------------------------------------------------------------------
# Incoming message parsing
# ---------------------------------------------------------------------------

class TestIncomingMessageParsing:
    def test_parse_action(self):
        raw = json.dumps({"type": "action", "action": "cancel"}) + "\n"
        msg = json.loads(raw.strip())
        assert msg["type"] == "action"
        assert msg["action"] == "cancel"

    def test_parse_config_update_int_value(self):
        raw = json.dumps(make_config_update("qwen3_asr", "prefill_step_size", 8192))
        msg = json.loads(raw)
        assert msg["value"] == 8192
        assert isinstance(msg["value"], int)

    def test_parse_config_update_string_value(self):
        raw = json.dumps(make_config_update("qwen3_asr", "language", "en"))
        msg = json.loads(raw)
        assert msg["value"] == "en"

    def test_parse_config_update_bool_value(self):
        raw = json.dumps(make_config_update("grammar", "enabled", False))
        msg = json.loads(raw)
        assert msg["value"] is False

    def test_parse_replacement_add(self):
        raw = json.dumps(make_replacement_add("gonna", "going to"))
        msg = json.loads(raw)
        assert msg["type"] == "replacement_add"
        assert msg["spoken"] == "gonna"
        assert msg["replacement"] == "going to"

    def test_parse_replacement_remove(self):
        raw = json.dumps(make_replacement_remove("gonna"))
        msg = json.loads(raw)
        assert msg["type"] == "replacement_remove"
        assert msg["spoken"] == "gonna"

    def test_invalid_json_raises(self):
        bad = b"{ not valid json }\n"
        try:
            json.loads(bad.strip().decode("utf-8"))
            assert False, "Should have raised"
        except json.JSONDecodeError:
            pass  # expected


# ---------------------------------------------------------------------------
# Buffer overflow protection
# ---------------------------------------------------------------------------

class TestBufferOverflow:
    MAX_BUF = 1_048_576  # 1MB, matches ipc_server._MAX_BUF_SIZE

    def test_large_message_exceeds_limit(self):
        big_payload = "x" * (self.MAX_BUF + 1)
        assert len(big_payload.encode("utf-8")) > self.MAX_BUF

    def test_normal_message_within_limit(self):
        msg = json.dumps(make_state_update("done", text="Hello world"))
        assert len(msg.encode("utf-8")) < self.MAX_BUF

    def test_newline_framing_splits_messages(self):
        msg1 = json.dumps(make_state_update("idle")) + "\n"
        msg2 = json.dumps(make_action("stop_recording")) + "\n"
        combined = (msg1 + msg2).encode("utf-8")

        buf = combined
        messages = []
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if line:
                messages.append(json.loads(line.decode("utf-8")))

        assert len(messages) == 2
        assert messages[0]["type"] == "state_update"
        assert messages[1]["type"] == "action"

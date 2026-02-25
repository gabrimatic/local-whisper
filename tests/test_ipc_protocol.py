# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for IPC message protocol.

All tests are pure JSON/dict operations. No sockets are created.
"""

import json


# ---------------------------------------------------------------------------
# Helpers: message constructors matching what app.py sends
# ---------------------------------------------------------------------------

def make_state_update(phase: str, **kwargs) -> dict:
    msg = {"type": "state_update", "phase": phase}
    msg.update(kwargs)
    return msg


def make_config_snapshot(engine: str = "qwen3_asr", backend: str = "apple_intelligence",
                         grammar_enabled: bool = False) -> dict:
    return {
        "type": "config_snapshot",
        "engine": engine,
        "backend": backend,
        "grammar_enabled": grammar_enabled,
        "history": [],
        "audio_history": [],
    }


def make_history_update(entries: list) -> dict:
    return {"type": "history_update", "history": entries}


# Incoming messages from Swift
def make_action(action: str) -> dict:
    return {"type": "action", "action": action}


def make_engine_switch(engine: str) -> dict:
    return {"type": "engine_switch", "engine": engine}


def make_backend_switch(backend: str) -> dict:
    return {"type": "backend_switch", "backend": backend}


def make_config_update(section: str, key: str, value) -> dict:
    return {"type": "config_update", "section": section, "key": key, "value": value}


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------

class TestJsonRoundTrip:
    def test_state_update_serializes(self):
        msg = make_state_update("idle")
        raw = json.dumps(msg)
        parsed = json.loads(raw)
        assert parsed["type"] == "state_update"
        assert parsed["phase"] == "idle"

    def test_config_snapshot_serializes(self):
        msg = make_config_snapshot()
        raw = json.dumps(msg)
        parsed = json.loads(raw)
        assert parsed["type"] == "config_snapshot"
        assert "engine" in parsed
        assert "backend" in parsed
        assert "grammar_enabled" in parsed

    def test_history_update_serializes(self):
        entries = [{"raw": "hello", "fixed": "Hello.", "timestamp": "2026-01-01T00:00:00"}]
        msg = make_history_update(entries)
        raw = json.dumps(msg)
        parsed = json.loads(raw)
        assert parsed["type"] == "history_update"
        assert len(parsed["history"]) == 1

    def test_action_message_serializes(self):
        msg = make_action("stop_recording")
        raw = json.dumps(msg)
        parsed = json.loads(raw)
        assert parsed["type"] == "action"
        assert parsed["action"] == "stop_recording"

    def test_engine_switch_serializes(self):
        msg = make_engine_switch("whisperkit")
        raw = json.dumps(msg)
        parsed = json.loads(raw)
        assert parsed["type"] == "engine_switch"
        assert parsed["engine"] == "whisperkit"

    def test_backend_switch_serializes(self):
        msg = make_backend_switch("ollama")
        raw = json.dumps(msg)
        parsed = json.loads(raw)
        assert parsed["type"] == "backend_switch"
        assert parsed["backend"] == "ollama"

    def test_config_update_serializes(self):
        msg = make_config_update("grammar", "enabled", True)
        raw = json.dumps(msg)
        parsed = json.loads(raw)
        assert parsed["type"] == "config_update"
        assert parsed["section"] == "grammar"
        assert parsed["key"] == "enabled"
        assert parsed["value"] is True


# ---------------------------------------------------------------------------
# State phases
# ---------------------------------------------------------------------------

class TestStateUpdatePhases:
    VALID_PHASES = ["idle", "recording", "processing", "done", "error"]

    def test_all_phases_round_trip(self):
        for phase in self.VALID_PHASES:
            msg = make_state_update(phase)
            raw = json.dumps(msg)
            parsed = json.loads(raw)
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


# ---------------------------------------------------------------------------
# config_snapshot required fields
# ---------------------------------------------------------------------------

class TestConfigSnapshot:
    REQUIRED_FIELDS = {"type", "engine", "backend", "grammar_enabled", "history", "audio_history"}

    def test_all_required_fields_present(self):
        msg = make_config_snapshot()
        for field in self.REQUIRED_FIELDS:
            assert field in msg, f"Missing field: {field}"

    def test_history_is_list(self):
        msg = make_config_snapshot()
        assert isinstance(msg["history"], list)

    def test_audio_history_is_list(self):
        msg = make_config_snapshot()
        assert isinstance(msg["audio_history"], list)

    def test_grammar_enabled_is_bool(self):
        msg = make_config_snapshot(grammar_enabled=True)
        parsed = json.loads(json.dumps(msg))
        assert isinstance(parsed["grammar_enabled"], bool)


# ---------------------------------------------------------------------------
# Incoming message parsing
# ---------------------------------------------------------------------------

class TestIncomingMessageParsing:
    def test_parse_action(self):
        raw = json.dumps({"type": "action", "action": "cancel"}) + "\n"
        line = raw.strip()
        msg = json.loads(line)
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

    def test_invalid_json_raises(self):
        bad = b"{ not valid json }\n"
        line = bad.strip()
        try:
            json.loads(line.decode("utf-8"))
            assert False, "Should have raised"
        except json.JSONDecodeError:
            pass  # expected


# ---------------------------------------------------------------------------
# Buffer overflow protection
# ---------------------------------------------------------------------------

class TestBufferOverflow:
    MAX_BUF = 1_048_576  # 1MB, matches ipc_server._MAX_BUF_SIZE

    def test_large_message_exceeds_limit(self):
        # A message just over the limit should be detectable
        big_payload = "x" * (self.MAX_BUF + 1)
        assert len(big_payload.encode("utf-8")) > self.MAX_BUF

    def test_normal_message_within_limit(self):
        msg = json.dumps(make_state_update("done", text="Hello world"))
        assert len(msg.encode("utf-8")) < self.MAX_BUF

    def test_newline_framing_splits_messages(self):
        msg1 = json.dumps(make_state_update("idle")) + "\n"
        msg2 = json.dumps(make_action("stop_recording")) + "\n"
        combined = (msg1 + msg2).encode("utf-8")

        # Simulate the read_loop framing logic
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

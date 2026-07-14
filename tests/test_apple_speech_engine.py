# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from whisper_voice.engines.apple_speech import AppleSpeechEngine


@pytest.fixture
def helper(tmp_path: Path) -> Path:
    path = tmp_path / "LocalWhisperSpeech"
    path.write_text("helper", encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def config(monkeypatch):
    value = SimpleNamespace(apple_speech=SimpleNamespace(locale="en-US", timeout=0))
    # Patch the globals dictionary used by the class imported above. Other
    # registry tests deliberately re-import engine modules, so a module-path
    # patch can otherwise target a newer module object during a full run.
    monkeypatch.setitem(AppleSpeechEngine._run_helper.__globals__, "get_config", lambda: value)
    return value


def completed(payload: dict, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, json.dumps(payload), "")


def test_start_installs_selected_locale(helper, config, monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return completed({
            "ok": True,
            "availability": "installed",
            "installed": True,
            "locale": "en-US",
            "message": "ready",
        })

    monkeypatch.setattr(subprocess, "run", run)
    engine = AppleSpeechEngine(helper_path=helper)

    assert engine.start() is True
    assert engine.running() is True
    assert calls[0][0] == [str(helper), "install", "--locale", "en-US"]
    assert calls[0][1]["timeout"] is None


def test_start_preserves_native_unavailable_message(helper, config, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: completed({
            "ok": False,
            "availability": "unavailable",
            "message": "Apple SpeechTranscriber is unavailable on this device.",
            "code": "device_unsupported",
        }, returncode=1),
    )
    engine = AppleSpeechEngine(helper_path=helper)

    assert engine.start() is False
    assert engine.last_error == "Apple SpeechTranscriber is unavailable on this device."


def test_transcribe_returns_native_final_text(helper, config, monkeypatch, tmp_path):
    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"RIFF")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: completed({
            "ok": True,
            "availability": "installed",
            "installed": True,
            "locale": "en-US",
            "message": "complete",
            "transcript": "  Highest quality text.  ",
        }),
    )
    engine = AppleSpeechEngine(helper_path=helper)

    text, error = engine.transcribe(audio)

    assert text == "Highest quality text."
    assert error is None


def test_transcribe_reports_malformed_helper_json(helper, config, monkeypatch, tmp_path):
    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"RIFF")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "not-json", ""),
    )
    engine = AppleSpeechEngine(helper_path=helper)

    assert engine.transcribe(audio) == (None, "Apple SpeechTranscriber returned an invalid response.")


def test_transcribe_uses_configured_timeout(helper, config, monkeypatch, tmp_path):
    config.apple_speech.timeout = 17
    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"RIFF")
    seen = {}

    def run(*args, **kwargs):
        seen.update(kwargs)
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", run)
    engine = AppleSpeechEngine(helper_path=helper)

    assert engine.transcribe(audio) == (None, "Apple SpeechTranscriber timed out after 17 seconds.")
    assert seen["timeout"] == 17


def test_missing_helper_is_actionable(tmp_path, config):
    engine = AppleSpeechEngine(helper_path=tmp_path / "missing")

    assert engine.start() is False
    assert "wh build" in engine.last_error


def test_engine_supports_long_audio(helper, config):
    assert AppleSpeechEngine(helper_path=helper).supports_long_audio is True

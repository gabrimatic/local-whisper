# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Regression tests for CLI lifecycle config reporting.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest


def _write_config(tmp_path: Path, grammar_enabled: bool, backend: str = "apple_intelligence") -> None:
    config_dir = tmp_path / ".whisper"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(
        "\n".join(
            [
                "[transcription]",
                'engine = "qwen3_asr"',
                "",
                "[grammar]",
                f'backend = "{backend}"',
                f"enabled = {'true' if grammar_enabled else 'false'}",
                "",
            ]
        ),
        encoding="utf-8",
    )


class TestLifecycleBackendStatus:
    def test_returns_disabled_when_grammar_flag_is_false(self, monkeypatch, tmp_path):
        from whisper_voice.cli import lifecycle

        monkeypatch.setenv("HOME", str(tmp_path))
        _write_config(tmp_path, grammar_enabled=False)

        assert lifecycle._read_config_backend_status() == "disabled"

    def test_returns_disabled_when_backend_is_none(self, monkeypatch, tmp_path):
        from whisper_voice.cli import lifecycle

        monkeypatch.setenv("HOME", str(tmp_path))
        _write_config(tmp_path, grammar_enabled=True, backend="none")

        assert lifecycle._read_config_backend_status() == "disabled"

    def test_returns_backend_when_grammar_is_enabled(self, monkeypatch, tmp_path):
        from whisper_voice.cli import lifecycle

        monkeypatch.setenv("HOME", str(tmp_path))
        _write_config(tmp_path, grammar_enabled=True, backend="ollama")

        assert lifecycle._read_config_backend_status() == "ollama"


class TestConfigSummary:
    def test_static_summary_uses_current_defaults(self, monkeypatch, tmp_path, capsys):
        from whisper_voice.cli.editor import cmd_config

        config_dir = tmp_path / ".whisper"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text("[service]\nidle_unload_minutes = 0\n", encoding="utf-8")
        monkeypatch.setenv("HOME", str(tmp_path))

        cmd_config(["show"])

        out = capsys.readouterr().out
        assert "parakeet_v3" in out
        assert "Idle unload" in out
        assert "never" in out
        assert "off" in out

    def test_qwen_summary_shows_selected_model_variant(self, monkeypatch, tmp_path, capsys):
        from whisper_voice.cli.editor import cmd_config

        config_dir = tmp_path / ".whisper"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            '[transcription]\nengine = "qwen3_asr"\n'
            '[qwen3_asr]\nmodel = "mlx-community/Qwen3-ASR-0.6B-bf16"\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("HOME", str(tmp_path))

        cmd_config(["show"])

        assert "Qwen3-ASR-0.6B-bf16" in capsys.readouterr().out


class TestUptimeParsing:
    def test_parse_etime_mm_ss(self):
        from whisper_voice.cli.lifecycle import _parse_etime

        assert _parse_etime("02:30") == 150

    def test_parse_etime_hh_mm_ss(self):
        from whisper_voice.cli.lifecycle import _parse_etime

        assert _parse_etime("01:02:03") == 3723

    def test_parse_etime_with_days(self):
        from whisper_voice.cli.lifecycle import _parse_etime

        assert _parse_etime("2-03:04:05") == 2 * 86400 + 3 * 3600 + 4 * 60 + 5

    def test_parse_etime_rejects_garbage(self):
        from whisper_voice.cli.lifecycle import _parse_etime

        assert _parse_etime("abc") is None
        assert _parse_etime("") is None

    def test_format_uptime_spans(self):
        from whisper_voice.cli.lifecycle import _format_uptime

        assert _format_uptime(45) == "45s"
        assert _format_uptime(90) == "1m"
        assert _format_uptime(7200) == "2.0h"
        assert _format_uptime(90000) == "1.0d"


class TestPendingWorkSummary:
    def test_reports_processing_marker(self, monkeypatch, tmp_path):
        from whisper_voice.cli import lifecycle

        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / ".whisper").mkdir()
        (tmp_path / ".whisper" / "processing.marker").write_text("x.wav", encoding="utf-8")
        assert lifecycle._pending_work_summary() == "1 interrupted transcription"

    def test_reports_partial_session(self, monkeypatch, tmp_path):
        from whisper_voice.cli import lifecycle

        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / ".whisper").mkdir()
        (tmp_path / ".whisper" / "current_session.jsonl").write_text(
            '{"type": "header", "total_chunks": 3, "started_at": 0}\n'
            '{"type": "chunk", "index": 0, "text": "a", "raw": "a", "ts": 1.0}\n'
            '{"type": "chunk", "index": 1, "text": "b", "raw": "b", "ts": 2.0}\n',
            encoding="utf-8",
        )
        summary = lifecycle._pending_work_summary()
        assert summary and "2 chunks" in summary

    def test_returns_none_when_no_pending_work(self, monkeypatch, tmp_path):
        from whisper_voice.cli import lifecycle

        monkeypatch.setenv("HOME", str(tmp_path))
        assert lifecycle._pending_work_summary() is None


class TestEngineSwitchModelPreparation:
    def test_apple_speech_prepares_native_asset(self, monkeypatch):
        from whisper_voice.cli import settings

        calls = []

        class FakeAppleSpeechEngine:
            last_error = ""

            def start(self):
                calls.append("install")
                return True

            def close(self):
                calls.append("close")

        monkeypatch.setattr(
            "whisper_voice.engines.apple_speech.AppleSpeechEngine",
            FakeAppleSpeechEngine,
        )

        settings._ensure_engine_ready_for_cli("apple_speech")

        assert calls == ["install", "close"]

    def test_cmd_engine_prefetches_managed_model_before_writing_config(self, monkeypatch):
        from whisper_voice.cli import settings

        calls = []
        monkeypatch.setattr(
            settings,
            "_list_engines",
            lambda: {
                "qwen3_asr": SimpleNamespace(
                    description="On-device MLX transcription",
                )
            },
        )
        monkeypatch.setattr(settings, "_is_running", lambda: (False, None))
        monkeypatch.setattr(settings, "_ensure_engine_ready_for_cli", lambda engine: calls.append(("ensure", engine)), raising=False)
        monkeypatch.setattr(settings, "_write_config_engine", lambda engine: calls.append(("write", engine)) or True)

        settings.cmd_engine(["qwen3_asr"])

        assert calls == [("ensure", "qwen3_asr"), ("write", "qwen3_asr")]

    def test_cmd_engine_selects_and_prefetches_qwen_variant_before_config_write(self, monkeypatch):
        from whisper_voice.cli import settings

        calls = []
        monkeypatch.setattr(
            settings,
            "_list_engines",
            lambda: {
                "qwen3_asr": SimpleNamespace(
                    description="On-device MLX transcription",
                )
            },
        )
        monkeypatch.setattr(settings, "_is_running", lambda: (False, None))
        monkeypatch.setattr(settings, "_read_config_engine", lambda: "parakeet_v3")
        monkeypatch.setattr(
            settings,
            "_read_qwen_model",
            lambda: "mlx-community/Qwen3-ASR-1.7B-bf16",
            raising=False,
        )
        monkeypatch.setattr(
            settings,
            "_ensure_engine_ready_for_cli",
            lambda engine, model: calls.append(("ensure", engine, model)),
            raising=False,
        )
        monkeypatch.setattr(
            settings,
            "_write_qwen_model",
            lambda model: calls.append(("model", model)) or True,
            raising=False,
        )
        monkeypatch.setattr(
            settings,
            "_write_config_engine",
            lambda engine: calls.append(("engine", engine)) or True,
        )

        settings.cmd_engine(["qwen3_asr", "0.6b"])

        expected_model = "mlx-community/Qwen3-ASR-0.6B-bf16"
        assert calls == [
            ("ensure", "qwen3_asr", expected_model),
            ("model", expected_model),
            ("engine", "qwen3_asr"),
        ]

    def test_cmd_engine_does_not_write_config_when_prefetch_fails(self, monkeypatch):
        from whisper_voice.cli import settings

        writes = []
        monkeypatch.setattr(
            settings,
            "_list_engines",
            lambda: {
                "qwen3_asr": SimpleNamespace(
                    description="On-device MLX transcription",
                )
            },
        )
        monkeypatch.setattr(settings, "_is_running", lambda: (False, None))

        def fail_prefetch(_engine):
            raise RuntimeError("network down")

        monkeypatch.setattr(settings, "_ensure_engine_ready_for_cli", fail_prefetch, raising=False)
        monkeypatch.setattr(settings, "_write_config_engine", lambda engine: writes.append(engine) or True)

        with pytest.raises(SystemExit):
            settings.cmd_engine(["qwen3_asr"])

        assert writes == []

    def test_cli_whisperkit_switch_requires_cli_before_config_write(self, monkeypatch):
        from whisper_voice.cli import settings
        from whisper_voice.engines import whisperkit_runtime

        calls = []
        monkeypatch.setattr(
            whisperkit_runtime,
            "require_whisperkit_cli",
            lambda: calls.append("check") or "/opt/homebrew/bin/whisperkit-cli",
        )
        monkeypatch.setattr(
            settings,
            "_list_engines",
            lambda: {
                "whisperkit": SimpleNamespace(
                    description="Local WhisperKit server",
                )
            },
        )
        monkeypatch.setattr(settings, "_is_running", lambda: (False, None))
        monkeypatch.setattr(settings, "_write_config_engine", lambda engine: calls.append(("write", engine)) or True)

        settings.cmd_engine(["whisperkit"])

        assert calls == ["check", ("write", "whisperkit")]

    def test_cli_whisperkit_switch_does_not_write_config_when_cli_missing(self, monkeypatch):
        from whisper_voice.cli import settings
        from whisper_voice.engines import whisperkit_runtime

        writes = []

        def fail_check():
            raise RuntimeError("WhisperKit CLI is not installed. Run: wh doctor --fix")

        monkeypatch.setattr(whisperkit_runtime, "require_whisperkit_cli", fail_check)
        monkeypatch.setattr(
            settings,
            "_list_engines",
            lambda: {
                "whisperkit": SimpleNamespace(
                    description="Local WhisperKit server",
                )
            },
        )
        monkeypatch.setattr(settings, "_is_running", lambda: (False, None))
        monkeypatch.setattr(settings, "_write_config_engine", lambda engine: writes.append(engine) or True)

        with pytest.raises(SystemExit):
            settings.cmd_engine(["whisperkit"])

        assert writes == []

    def test_cmd_engine_rolls_back_when_restarted_service_never_becomes_ready(self, monkeypatch):
        from whisper_voice.cli import build, doctor, settings

        writes = []
        restarts = []
        monkeypatch.setattr(
            settings,
            "_list_engines",
            lambda: {
                "parakeet_v3": SimpleNamespace(description="On-device Parakeet"),
                "whisperkit": SimpleNamespace(description="Local WhisperKit server"),
            },
        )
        monkeypatch.setattr(settings, "_read_config_engine", lambda: "parakeet_v3")
        monkeypatch.setattr(settings, "_is_running", lambda: (True, 123))
        monkeypatch.setattr(settings, "_ensure_engine_ready_for_cli", lambda engine: None)
        monkeypatch.setattr(settings, "_write_config_engine", lambda engine: writes.append(engine) or True)
        monkeypatch.setattr(build, "cmd_restart", lambda: restarts.append("restart"))
        monkeypatch.setattr(doctor, "_wait_for_service_ready", lambda timeout=180.0: False)

        with pytest.raises(SystemExit):
            settings.cmd_engine(["whisperkit"])

        assert writes == ["whisperkit", "parakeet_v3"]
        assert restarts == ["restart", "restart"]

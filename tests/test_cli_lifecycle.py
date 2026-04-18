# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Regression tests for CLI lifecycle config reporting.
"""

from pathlib import Path


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

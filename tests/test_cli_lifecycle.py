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

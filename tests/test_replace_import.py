# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Unit tests for ``wh replace import <file>`` bulk-import parser.

These tests exercise ``_import_replacements`` directly rather than spawning
the full CLI so they stay fast and deterministic.
"""


import pytest

from whisper_voice.cli import settings as cli_settings


class _Captured:
    """Collect every add_replacement call for assertions."""

    def __init__(self):
        self.rules: list[tuple[str, str]] = []

    def add(self, spoken: str, replacement: str) -> bool:
        self.rules.append((spoken, replacement))
        return True


@pytest.fixture
def captured(monkeypatch):
    cap = _Captured()

    def fake_add(spoken, replacement):
        return cap.add(spoken, replacement)

    monkeypatch.setattr("whisper_voice.config.add_replacement", fake_add)
    return cap


def test_imports_csv(tmp_path, captured, capsys):
    f = tmp_path / "rules.csv"
    f.write_text("gonna,going to\nwanna,want to\n", encoding="utf-8")
    cli_settings._import_replacements(str(f))
    assert captured.rules == [("gonna", "going to"), ("wanna", "want to")]


def test_imports_tsv(tmp_path, captured):
    f = tmp_path / "rules.tsv"
    f.write_text("open ai\tOpenAI\nchat gpt\tChatGPT\n", encoding="utf-8")
    cli_settings._import_replacements(str(f))
    assert captured.rules == [("open ai", "OpenAI"), ("chat gpt", "ChatGPT")]


def test_imports_toml_style(tmp_path, captured):
    f = tmp_path / "rules.txt"
    f.write_text('"gonna" = "going to"\n"eye phone" = "iPhone"\n', encoding="utf-8")
    cli_settings._import_replacements(str(f))
    assert captured.rules == [("gonna", "going to"), ("eye phone", "iPhone")]


def test_imports_arrow_form(tmp_path, captured):
    f = tmp_path / "rules.txt"
    f.write_text("gonna -> going to\nwanna -> want to\n", encoding="utf-8")
    cli_settings._import_replacements(str(f))
    assert captured.rules == [("gonna", "going to"), ("wanna", "want to")]


def test_skips_blank_and_comment_lines(tmp_path, captured):
    f = tmp_path / "rules.txt"
    f.write_text(
        "\n# This is a comment\n  \ngonna,going to\n# trailing\n",
        encoding="utf-8",
    )
    cli_settings._import_replacements(str(f))
    assert captured.rules == [("gonna", "going to")]


def test_missing_file_exits(tmp_path, captured):
    with pytest.raises(SystemExit):
        cli_settings._import_replacements(str(tmp_path / "does-not-exist.csv"))


def test_empty_file_prints_notice(tmp_path, captured, capsys):
    f = tmp_path / "empty.csv"
    f.write_text("", encoding="utf-8")
    cli_settings._import_replacements(str(f))
    assert captured.rules == []
    out = capsys.readouterr().out
    assert "No rules found" in out


def test_duplicate_keys_reported(tmp_path, captured, capsys):
    f = tmp_path / "rules.csv"
    f.write_text("gonna,going to\ngonna,going tos\n", encoding="utf-8")
    cli_settings._import_replacements(str(f))
    out = capsys.readouterr().out
    assert "duplicate" in out.lower()
    # Both rules reached the writer; the *last* one wins at the config layer.
    assert captured.rules == [("gonna", "going to"), ("gonna", "going tos")]

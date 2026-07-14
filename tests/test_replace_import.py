# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Unit tests for ``wh replace import <file>`` bulk-import parser.

These tests exercise ``_import_replacements`` directly rather than spawning
the full CLI so they stay fast and deterministic. Imports land through ONE
bulk ``add_replacements`` call (a single locked config rewrite), not one
write per rule.
"""


import pytest

from whisper_voice.cli import settings as cli_settings


class _Captured:
    """Collect the bulk add_replacements call for assertions."""

    def __init__(self):
        self.rules: dict = {}
        self.calls: int = 0

    def add_bulk(self, rules: dict) -> bool:
        self.calls += 1
        self.rules.update(rules)
        return True


@pytest.fixture
def captured(monkeypatch):
    cap = _Captured()
    monkeypatch.setattr("whisper_voice.config.add_replacements", cap.add_bulk)
    monkeypatch.setattr("whisper_voice.config._read_replacements_rules", lambda: {})
    return cap


def test_imports_csv(tmp_path, captured, capsys):
    f = tmp_path / "rules.csv"
    f.write_text("gonna,going to\nwanna,want to\n", encoding="utf-8")
    cli_settings._import_replacements(str(f))
    assert captured.rules == {"gonna": "going to", "wanna": "want to"}
    assert captured.calls == 1


def test_imports_tsv(tmp_path, captured):
    f = tmp_path / "rules.tsv"
    f.write_text("open ai\tOpenAI\nchat gpt\tChatGPT\n", encoding="utf-8")
    cli_settings._import_replacements(str(f))
    assert captured.rules == {"open ai": "OpenAI", "chat gpt": "ChatGPT"}


def test_imports_toml_style(tmp_path, captured):
    f = tmp_path / "rules.txt"
    f.write_text('"gonna" = "going to"\n"eye phone" = "iPhone"\n', encoding="utf-8")
    cli_settings._import_replacements(str(f))
    assert captured.rules == {"gonna": "going to", "eye phone": "iPhone"}


def test_imports_arrow_form(tmp_path, captured):
    f = tmp_path / "rules.txt"
    f.write_text("gonna -> going to\nwanna -> want to\n", encoding="utf-8")
    cli_settings._import_replacements(str(f))
    assert captured.rules == {"gonna": "going to", "wanna": "want to"}


def test_arrow_inside_csv_value_not_misparsed(tmp_path, captured):
    # Format is detected per-file: a CSV row whose replacement contains "->"
    # must not be parsed as arrow format.
    f = tmp_path / "rules.csv"
    f.write_text("implies,a -> b\ngonna,going to\n", encoding="utf-8")
    cli_settings._import_replacements(str(f))
    assert captured.rules == {"implies": "a -> b", "gonna": "going to"}


def test_quoted_csv_with_embedded_comma_roundtrips(tmp_path, captured):
    f = tmp_path / "rules.csv"
    f.write_text('"a, b","c"\n"say ""hi""","greeting"\n', encoding="utf-8")
    cli_settings._import_replacements(str(f))
    assert captured.rules == {"a, b": "c", 'say "hi"': "greeting"}


def test_bom_stripped_from_first_key(tmp_path, captured):
    f = tmp_path / "rules.csv"
    f.write_bytes("﻿gonna,going to\n".encode("utf-8"))
    cli_settings._import_replacements(str(f))
    assert captured.rules == {"gonna": "going to"}


def test_skips_blank_and_comment_lines(tmp_path, captured):
    f = tmp_path / "rules.txt"
    f.write_text(
        "\n# This is a comment\n  \ngonna,going to\n# trailing\n",
        encoding="utf-8",
    )
    cli_settings._import_replacements(str(f))
    assert captured.rules == {"gonna": "going to"}


def test_missing_file_exits(tmp_path, captured):
    with pytest.raises(SystemExit):
        cli_settings._import_replacements(str(tmp_path / "does-not-exist.csv"))


def test_empty_file_prints_notice(tmp_path, captured, capsys):
    f = tmp_path / "empty.csv"
    f.write_text("", encoding="utf-8")
    cli_settings._import_replacements(str(f))
    assert captured.rules == {}
    out = capsys.readouterr().out
    assert "No rules found" in out


def test_duplicate_keys_reported_last_wins(tmp_path, captured, capsys):
    f = tmp_path / "rules.csv"
    f.write_text("gonna,going to\ngonna,going tos\n", encoding="utf-8")
    cli_settings._import_replacements(str(f))
    out = capsys.readouterr().out
    assert "duplicate" in out.lower()
    assert captured.rules == {"gonna": "going tos"}


def test_new_vs_updated_reported(tmp_path, captured, capsys, monkeypatch):
    monkeypatch.setattr(
        "whisper_voice.config._read_replacements_rules", lambda: {"gonna": "old"}
    )
    f = tmp_path / "rules.csv"
    f.write_text("gonna,going to\nwanna,want to\n", encoding="utf-8")
    cli_settings._import_replacements(str(f))
    out = capsys.readouterr().out
    assert "1 new" in out
    assert "1 updated" in out


def test_toml_lines_with_writer_escapes_roundtrip(tmp_path, captured):
    # The config writer escapes quotes/newlines; its own output must import.
    f = tmp_path / "rules.txt"
    f.write_text(
        '"say \\"hi\\"" = "greeting"\n"sig" = "line1\\nline2"\n',
        encoding="utf-8",
    )
    cli_settings._import_replacements(str(f))
    assert captured.rules == {'say "hi"': "greeting", "sig": "line1\nline2"}

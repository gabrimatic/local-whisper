# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Unit tests for history export + usage stats.

These tests rely on patched versions of ``Backup`` and ``get_config`` so they
don't hit the real filesystem or config file. They reuse the standard conftest
stubs (sounddevice, AppKit, etc.) so the modules under test import cleanly.
"""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

# Import once at module scope so numpy's C extension is only loaded once.
from whisper_voice import history_export as he
from whisper_voice import stats as st


def _fake_entry(i: int, ts: datetime) -> dict:
    return {
        "path": SimpleNamespace(stem=ts.strftime("%Y%m%d_%H%M%S_%f")),
        "timestamp": ts,
        "raw": f"raw entry {i}",
        "fixed": f"Fixed entry {i}.",
    }


def _fake_entries(n: int, start: datetime | None = None) -> list:
    start = start or datetime(2026, 1, 1, 9, 0, 0)
    return [_fake_entry(i, start + timedelta(minutes=5 * i)) for i in range(n)]


class _FakeBackupFactory:
    """Callable class that pytest.monkeypatch uses in place of ``Backup``.

    Tests assign a list of entries onto the factory to control what the
    patched ``Backup().get_history()`` returns.
    """

    entries: list = []

    def __call__(self):
        return self

    def get_history(self, limit):
        return self.entries[:limit] if limit else self.entries


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestExportFormats:
    def test_markdown_export(self, tmp_path, monkeypatch):
        fake = _FakeBackupFactory()
        fake.entries = _fake_entries(3)
        monkeypatch.setattr(he, "Backup", lambda: fake)

        out = tmp_path / "history.md"
        count = he.export_history(out, fmt="md")
        assert count == 3
        content = out.read_text("utf-8")
        assert content.startswith("# Local Whisper history")
        assert "Fixed entry 0." in content
        assert "Fixed entry 2." in content

    def test_txt_export(self, tmp_path, monkeypatch):
        fake = _FakeBackupFactory()
        fake.entries = _fake_entries(2)
        monkeypatch.setattr(he, "Backup", lambda: fake)

        out = tmp_path / "history.txt"
        count = he.export_history(out, fmt="txt")
        assert count == 2
        content = out.read_text("utf-8")
        assert "[2026-01-01" in content

    def test_json_export(self, tmp_path, monkeypatch):
        fake = _FakeBackupFactory()
        fake.entries = _fake_entries(2)
        monkeypatch.setattr(he, "Backup", lambda: fake)

        out = tmp_path / "history.json"
        he.export_history(out, fmt="json")
        data = json.loads(out.read_text("utf-8"))
        assert len(data) == 2
        assert data[0]["fixed"] == "Fixed entry 0."
        assert data[0]["timestamp"].startswith("2026-01-01")

    def test_unknown_format_raises(self, tmp_path, monkeypatch):
        fake = _FakeBackupFactory()
        monkeypatch.setattr(he, "Backup", lambda: fake)
        with pytest.raises(ValueError):
            he.export_history(tmp_path / "x.pdf", fmt="pdf")

    def test_empty_history_still_writes(self, tmp_path, monkeypatch):
        fake = _FakeBackupFactory()
        fake.entries = []
        monkeypatch.setattr(he, "Backup", lambda: fake)

        out = tmp_path / "history.md"
        count = he.export_history(out, fmt="md")
        assert count == 0
        assert out.exists()
        assert "No transcriptions" in out.read_text("utf-8")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestStats:
    def _patch(self, monkeypatch, entries):
        fake = _FakeBackupFactory()
        fake.entries = entries
        monkeypatch.setattr(st, "Backup", lambda: fake)
        fake_cfg = SimpleNamespace(replacements=SimpleNamespace(enabled=False, rules={}))
        monkeypatch.setattr(st, "get_config", lambda: fake_cfg)

    def test_stats_empty(self, monkeypatch):
        self._patch(monkeypatch, [])
        stats = st.compute_usage_stats()
        assert stats.total_sessions == 0
        assert stats.total_words == 0
        assert st.format_stats_text(stats) == "No transcriptions yet."

    def test_stats_basic_counts(self, monkeypatch):
        entries = _fake_entries(5)
        self._patch(monkeypatch, entries)
        stats = st.compute_usage_stats()
        assert stats.total_sessions == 5
        assert stats.total_words > 0
        assert stats.first_session == entries[0]["timestamp"]
        assert stats.last_session == entries[-1]["timestamp"]
        rendered = st.format_stats_text(stats)
        assert "Total sessions" in rendered
        assert "5" in rendered

    def test_stats_counts_replacement_triggers(self, monkeypatch):
        # Raw text contains the spoken form; fixed text has the replacement.
        # Stats should count by scanning the RAW column so the counter matches
        # "how many times did this rule fire" rather than "how many times does
        # the replacement appear in the output".
        entries = [
            _fake_entry(0, datetime(2026, 1, 1, 9, 0, 0)),
            _fake_entry(1, datetime(2026, 1, 2, 10, 0, 0)),
            _fake_entry(2, datetime(2026, 1, 3, 11, 0, 0)),
        ]
        entries[0]["raw"] = "I saw open ai today."
        entries[0]["fixed"] = "I saw OpenAI today."
        entries[1]["raw"] = "open ai and chat gpt are great."
        entries[1]["fixed"] = "OpenAI and ChatGPT are great."
        entries[2]["raw"] = "nothing relevant here."
        entries[2]["fixed"] = "Nothing relevant here."

        fake = _FakeBackupFactory()
        fake.entries = entries
        monkeypatch.setattr(st, "Backup", lambda: fake)
        fake_cfg = SimpleNamespace(
            replacements=SimpleNamespace(
                enabled=True,
                rules={"open ai": "OpenAI", "chat gpt": "ChatGPT"},
            ),
        )
        monkeypatch.setattr(st, "get_config", lambda: fake_cfg)

        stats = st.compute_usage_stats()
        counts = dict(stats.top_replacements_triggered)
        assert counts.get("open ai") == 2
        assert counts.get("chat gpt") == 1

    def test_stats_top_words_excludes_stopwords(self, monkeypatch):
        entries = _fake_entries(3)
        for i, e in enumerate(entries):
            e["fixed"] = "the quick brown fox and the lazy dog"
        self._patch(monkeypatch, entries)
        stats = st.compute_usage_stats()
        words = [w for w, _ in stats.top_words]
        assert "the" not in words
        assert "and" not in words
        assert any(w in words for w in ("quick", "brown", "fox", "lazy", "dog"))

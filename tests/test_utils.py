# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for utility functions in utils.py.

Only tests pure functions that require no hardware, no network, and no macOS frameworks.
"""

import sys
from datetime import datetime, timedelta
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Import helper
# ---------------------------------------------------------------------------

def _import_utils():
    """Import utils after stubbing out framework-dependent modules."""
    for mod in list(sys.modules.keys()):
        if "whisper_voice" in mod:
            del sys.modules[mod]

    stubs = {
        "rumps": None,
        "sounddevice": None,
        "AppKit": None,
        "Foundation": None,
        "Quartz": None,
    }
    with patch.dict("sys.modules", stubs):
        import whisper_voice.utils as utils_mod
    return utils_mod


# ---------------------------------------------------------------------------
# Hallucination filter: is_hallucination
# ---------------------------------------------------------------------------

class TestIsHallucination:
    def test_empty_string_returns_false(self):
        # Empty string: no pattern to match, so not classified as hallucination.
        u = _import_utils()
        assert u.is_hallucination("") is False

    def test_none_returns_false(self):
        # None guard: function returns False early when text is falsy.
        u = _import_utils()
        assert u.is_hallucination(None) is False

    def test_known_pattern_thank_you_watching(self):
        u = _import_utils()
        assert u.is_hallucination("Thank you for watching") is True

    def test_known_pattern_subscribe(self):
        u = _import_utils()
        assert u.is_hallucination("Subscribe") is True

    def test_known_pattern_music(self):
        u = _import_utils()
        assert u.is_hallucination("[Music]") is True

    def test_known_pattern_applause(self):
        u = _import_utils()
        assert u.is_hallucination("[Applause]") is True

    def test_real_speech_not_hallucination(self):
        u = _import_utils()
        assert u.is_hallucination("Hello, how are you doing today?") is False

    def test_technical_content_not_hallucination(self):
        u = _import_utils()
        assert u.is_hallucination("The function returns a list of integers sorted in ascending order.") is False

    def test_long_text_with_hallucination_suffix_not_filtered(self):
        # Long real content that happens to end with a hallucination pattern
        # should NOT be fully filtered - just the trailing pattern stripped
        u = _import_utils()
        long_text = "This is a really long transcription with a lot of meaningful content. " * 5
        long_text += "Thank you for watching"
        result = u.is_hallucination(long_text)
        # With lots of real content, should NOT be classified as pure hallucination
        assert result is False


# ---------------------------------------------------------------------------
# Hallucination filter: strip_hallucination_lines
# ---------------------------------------------------------------------------

class TestStripHallucinationLines:
    def test_strips_standalone_hallucination_line(self):
        u = _import_utils()
        text = "Real content here.\nThank you for watching"
        cleaned, removed = u.strip_hallucination_lines(text)
        assert removed is True
        assert "thank you for watching" not in cleaned.lower()
        assert "Real content here" in cleaned

    def test_preserves_real_lines(self):
        u = _import_utils()
        text = "Line one.\nLine two.\nLine three."
        cleaned, removed = u.strip_hallucination_lines(text)
        assert removed is False
        assert cleaned == text.strip()

    def test_empty_string_unchanged(self):
        u = _import_utils()
        cleaned, removed = u.strip_hallucination_lines("")
        assert removed is False
        assert cleaned == ""

    def test_only_hallucination_fully_stripped(self):
        u = _import_utils()
        text = "Subscribe"
        cleaned, removed = u.strip_hallucination_lines(text)
        assert removed is True
        assert cleaned == ""

    def test_returns_tuple(self):
        u = _import_utils()
        result = u.strip_hallucination_lines("hello")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_removed_flag_false_for_clean_text(self):
        u = _import_utils()
        _, removed = u.strip_hallucination_lines("This is clean text.")
        assert removed is False


# ---------------------------------------------------------------------------
# time_ago
# ---------------------------------------------------------------------------

class TestTimeAgo:
    def test_just_now_for_recent(self):
        u = _import_utils()
        now = datetime.now()
        result = u.time_ago(now - timedelta(seconds=10))
        assert result == "Just now"

    def test_minutes_ago(self):
        u = _import_utils()
        result = u.time_ago(datetime.now() - timedelta(minutes=5))
        assert "m ago" in result

    def test_hours_ago(self):
        u = _import_utils()
        result = u.time_ago(datetime.now() - timedelta(hours=3))
        assert "h ago" in result

    def test_yesterday(self):
        u = _import_utils()
        result = u.time_ago(datetime.now() - timedelta(days=1))
        assert result == "Yesterday"

    def test_days_ago(self):
        u = _import_utils()
        result = u.time_ago(datetime.now() - timedelta(days=5))
        assert "d ago" in result

    def test_old_date_returns_month_format(self):
        u = _import_utils()
        old = datetime.now() - timedelta(days=40)
        result = u.time_ago(old)
        # Should be something like "Jan 5" rather than "Xd ago"
        assert "ago" not in result

    def test_returns_string(self):
        u = _import_utils()
        result = u.time_ago(datetime.now())
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# truncate
# ---------------------------------------------------------------------------

class TestTruncate:
    def test_short_string_unchanged(self):
        u = _import_utils()
        assert u.truncate("hello", 10) == "hello"

    def test_long_string_truncated_with_ellipsis(self):
        u = _import_utils()
        result = u.truncate("a" * 100, 20)
        assert result.endswith("...")
        assert len(result) == 23  # 20 + "..."

    def test_exact_length_unchanged(self):
        u = _import_utils()
        text = "x" * 60
        assert u.truncate(text, 60) == text

    def test_empty_string_unchanged(self):
        u = _import_utils()
        assert u.truncate("", 10) == ""


# ---------------------------------------------------------------------------
# HALLUCINATION_PATTERNS list
# ---------------------------------------------------------------------------

class TestHallucinationPatterns:
    def test_patterns_list_exists(self):
        u = _import_utils()
        assert hasattr(u, "HALLUCINATION_PATTERNS")

    def test_patterns_is_list(self):
        u = _import_utils()
        assert isinstance(u.HALLUCINATION_PATTERNS, list)

    def test_patterns_non_empty(self):
        u = _import_utils()
        assert len(u.HALLUCINATION_PATTERNS) > 0

    def test_known_patterns_present(self):
        u = _import_utils()
        patterns = [p.lower() for p in u.HALLUCINATION_PATTERNS]
        assert any("thank you for watching" in p for p in patterns)
        assert any("subscribe" in p for p in patterns)

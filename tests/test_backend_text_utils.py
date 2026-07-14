# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Tests for GrammarBackend shared text utilities: input-aware result
cleaning and lossless chunk splitting."""

import sys
from unittest.mock import patch

import pytest


def _make_backend():
    for mod in list(sys.modules.keys()):
        if "whisper_voice" in mod:
            del sys.modules[mod]
    stubs = {"sounddevice": None, "AppKit": None, "Foundation": None, "Quartz": None}
    with patch.dict("sys.modules", stubs):
        from whisper_voice.backends.base import GrammarBackend

    class Dummy(GrammarBackend):
        @property
        def name(self):
            return "Dummy"

        def close(self):
            pass

        def running(self):
            return True

        def start(self):
            return True

        def fix(self, text):
            return text, None

        def fix_with_mode(self, text, mode_id):
            # Identity transform; lets _fix_in_chunks be tested end-to-end.
            return text, None

    return Dummy()


class TestCleanResultStripsModelChatter:
    def test_strips_added_opener(self):
        b = _make_backend()
        out = b._clean_result("Sure, here's the corrected text: Hello world.", "helo world.")
        assert out == "Hello world."

    def test_strips_label_prefix(self):
        b = _make_backend()
        assert b._clean_result("Corrected: Hello.", "helo.") == "Hello."

    def test_strips_trailing_meta(self):
        b = _make_backend()
        out = b._clean_result("Hello world. Let me know if you need more changes.", "helo world")
        assert out == "Hello world."

    def test_unwraps_added_code_fence(self):
        b = _make_backend()
        assert b._clean_result("```text\nHello.\n```", "helo.") == "Hello."

    def test_strips_added_wrapping_quotes(self):
        b = _make_backend()
        assert b._clean_result('"Hello world."', "helo world.") == "Hello world."


class TestCleanResultPreservesEchoedInput:
    """The model echoing the user's own text must never be 'cleaned'."""

    def test_keeps_sure_when_input_starts_with_it(self):
        b = _make_backend()
        text = "Sure, sounds good. See you at 5."
        assert b._clean_result(text, text) == text

    def test_keeps_of_course_when_echoed(self):
        b = _make_backend()
        text = "Of course, I'd love to join you on Friday."
        assert b._clean_result(text, text) == text

    def test_keeps_result_label_when_echoed(self):
        b = _make_backend()
        text = "Result: 42 tests passed."
        assert b._clean_result(text, text) == text

    def test_keeps_trailing_sentence_when_echoed(self):
        b = _make_backend()
        text = "Please let me know if you have any questions."
        assert b._clean_result(text, text) == text

    def test_keeps_feel_free_when_echoed(self):
        b = _make_backend()
        text = "Drop by later. Feel free to bring a friend."
        assert b._clean_result(text, text) == text

    def test_keeps_quotes_when_input_quoted(self):
        b = _make_backend()
        text = '"Hello," she said.'
        # Input starts with a quote, so a leading quote in the result is content.
        assert b._clean_result(text, text) == text

    def test_keeps_code_fence_when_input_fenced(self):
        b = _make_backend()
        text = "```python\nprint('hi')\n```"
        assert b._clean_result(text, text) == text

    def test_okay_heres_the_plan_survives(self):
        b = _make_backend()
        text = "Okay, here's the plan for tomorrow. We meet at nine."
        assert b._clean_result(text, text) == text


class TestSplitLossless:
    def _roundtrip(self, text, max_chars):
        b = _make_backend()
        chunks = b._split_lossless(text, max_chars)
        assert "".join(c + s for c, s in chunks) == text
        return chunks

    def test_short_text_single_chunk(self):
        chunks = self._roundtrip("hello world", 100)
        assert chunks == [("hello world", "")]

    def test_paragraphs_roundtrip(self):
        text = "Para one line.\n\nPara two line.\n\nPara three."
        self._roundtrip(text, 20)

    def test_single_newlines_preserved(self):
        text = "- bullet one\n- bullet two\n- bullet three\n- bullet four"
        chunks = self._roundtrip(text, 30)
        assert len(chunks) > 1

    def test_mixed_whitespace_separators_preserved(self):
        text = "a" * 25 + "\n  \n\t\n" + "b" * 25
        self._roundtrip(text, 30)

    def test_long_sentence_splits(self):
        text = ("word " * 50).strip() + ". " + ("more " * 50).strip() + "."
        chunks = self._roundtrip(text, 100)
        assert all(len(c) <= 100 for c, _ in chunks)

    def test_unbreakable_run_hard_splits(self):
        text = "x" * 250
        chunks = self._roundtrip(text, 100)
        assert all(len(c) <= 100 for c, _ in chunks)

    def test_trailing_newline_preserved(self):
        text = ("a" * 40) + "\n" + ("b" * 40) + "\n"
        self._roundtrip(text, 50)

    def test_fix_in_chunks_identity_reassembles_exactly(self):
        b = _make_backend()
        text = "Line one.\n\n- item a\n- item b\n\nFinal paragraph with more text."
        out, err = b._fix_in_chunks(text, 20, "proofread")
        assert err is None
        assert out == text

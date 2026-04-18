# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Unit tests for voice dictation commands."""

import sys
from unittest.mock import patch


def _import_module():
    for mod in list(sys.modules.keys()):
        if "whisper_voice" in mod:
            del sys.modules[mod]
    stubs = {
        "sounddevice": None,
        "AppKit": None,
        "Foundation": None,
        "Quartz": None,
        "mlx": None,
        "mlx.core": None,
    }
    with patch.dict("sys.modules", stubs):
        from whisper_voice.dictation_commands import (
            DEFAULT_COMMANDS,
            apply_dictation_commands,
        )
    return apply_dictation_commands, DEFAULT_COMMANDS


class TestStructuralCommands:
    def test_new_line(self):
        apply, _ = _import_module()
        assert apply("hello new line world", {"new line": "\n"}) == "hello\nworld"

    def test_new_paragraph(self):
        apply, _ = _import_module()
        assert apply("first new paragraph second", {"new paragraph": "\n\n"}) == "first\n\nsecond"

    def test_new_line_is_case_insensitive(self):
        apply, _ = _import_module()
        assert apply("a NEW LINE b", {"new line": "\n"}) == "a\nb"


class TestPunctuationCommands:
    def test_period_attaches_to_preceding_word(self):
        apply, _ = _import_module()
        assert apply("hello period world period", {"period": "."}) == "hello. world."

    def test_comma_attaches_to_preceding_word(self):
        apply, _ = _import_module()
        assert apply("red comma green comma blue", {"comma": ","}) == "red, green, blue"

    def test_question_mark_attaches(self):
        apply, _ = _import_module()
        assert apply("really question mark", {"question mark": "?"}) == "really?"

    def test_full_set_default_punctuation(self):
        apply, _ = _import_module()
        text = "hello period how are you question mark wow exclamation mark"
        out = apply(text)
        assert out == "Hello. How are you? Wow!" or out.lower() == "hello. how are you? wow!"

    def test_longer_phrase_beats_shorter(self):
        apply, _ = _import_module()
        # "new paragraph" must win over "new" even if a "new" command exists.
        out = apply(
            "para one new paragraph para two",
            {"new paragraph": "\n\n", "new": "NEW"},
        )
        assert "NEW paragraph" not in out
        assert out == "para one\n\npara two"


class TestScratchThat:
    def test_scratch_removes_current_sentence_fragment(self):
        apply, _ = _import_module()
        assert apply("first sentence scratch that replacement", {"scratch that": "__SCRATCH__"}) == "replacement"

    def test_scratch_stops_at_sentence_boundary(self):
        apply, _ = _import_module()
        out = apply("Finished thought. Wrong fragment scratch that right fragment", {"scratch that": "__SCRATCH__"})
        # Everything after the period through "scratch that" is gone.
        assert "Wrong fragment" not in out
        assert "right fragment" in out
        assert "Finished thought." in out

    def test_scratch_with_no_preceding_text(self):
        apply, _ = _import_module()
        assert apply("scratch that hello", {"scratch that": "__SCRATCH__"}) == "hello"

    def test_multiple_scratches_compose(self):
        apply, _ = _import_module()
        out = apply(
            "first try scratch that second try scratch that third try",
            {"scratch that": "__SCRATCH__"},
        )
        assert out == "third try"


class TestConfigIntegration:
    def test_empty_text_round_trips(self):
        apply, _ = _import_module()
        assert apply("") == ""

    def test_disabled_commands_noop(self):
        apply, _ = _import_module()
        # An empty commands dict disables the transform.
        assert apply("hello period world", commands={}) == "hello period world"

    def test_custom_command(self):
        apply, _ = _import_module()
        out = apply("wow smiley", {"smiley": " :)"})
        assert out == "wow :)"


class TestWhitespaceHygiene:
    def test_collapses_doubled_spaces(self):
        apply, _ = _import_module()
        assert apply("a  b period c  d", {"period": "."}) == "a b. c d"

    def test_trims_trailing_whitespace(self):
        apply, _ = _import_module()
        assert apply("hello period  ", {"period": "."}) == "hello."

    def test_no_space_before_punctuation(self):
        apply, _ = _import_module()
        out = apply("yes period no exclamation mark", {"period": ".", "exclamation mark": "!"})
        assert out == "yes. no!"

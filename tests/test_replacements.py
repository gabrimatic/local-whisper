# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Tests for the vocabulary replacement engine."""

from whisper_voice.replacements import apply_replacements


class TestBasicMatching:
    def test_simple_word(self):
        assert apply_replacements("i use eye phone daily", {"eye phone": "iPhone"}) == "i use iPhone daily"

    def test_case_insensitive_match(self):
        assert apply_replacements("Open AI ships models", {"open ai": "OpenAI"}) == "OpenAI ships models"

    def test_no_partial_word_match(self):
        # "cat" must not match inside "catalog" or "cats".
        assert apply_replacements("catalog of cats", {"cat": "feline"}) == "catalog of cats"

    def test_word_boundary_both_sides(self):
        assert apply_replacements("scattered", {"cat": "feline"}) == "scattered"
        assert apply_replacements("the cat sat", {"cat": "feline"}) == "the feline sat"

    def test_multiple_occurrences(self):
        assert apply_replacements("gonna go, gonna stay", {"gonna": "going to"}) == "going to go, going to stay"

    def test_empty_text_and_rules(self):
        assert apply_replacements("", {"a": "b"}) == ""
        assert apply_replacements("hello", {}) == "hello"

    def test_empty_spoken_form_ignored(self):
        assert apply_replacements("hello", {"": "x", " ": "y"}) == "hello"


class TestNonWordBoundaries:
    def test_trailing_symbol_term(self):
        # \b-based matching never fired for terms ending in non-word chars.
        assert apply_replacements("i code in c++ daily", {"c++": "C++"}) == "i code in C++ daily"

    def test_leading_symbol_term(self):
        assert apply_replacements("built on .net today", {".net": ".NET"}) == "built on .NET today"

    def test_symbol_term_not_inside_word(self):
        assert apply_replacements("asp.net rocks", {".net": ".NET"}) == "asp.net rocks"

    def test_punctuation_adjacent(self):
        assert apply_replacements("use c++, not c.", {"c++": "C++"}) == "use C++, not c."

    def test_hyphenated_term(self):
        assert apply_replacements("send an e-mail now", {"e-mail": "email"}) == "send an email now"


class TestOrderingAndOverlap:
    def test_longest_rule_wins(self):
        rules = {"chat gpt": "ChatGPT", "chat gpt four": "GPT-4"}
        assert apply_replacements("i asked chat gpt four things", rules) == "i asked GPT-4 things"

    def test_shorter_rule_still_applies_elsewhere(self):
        rules = {"chat gpt": "ChatGPT", "chat gpt four": "GPT-4"}
        out = apply_replacements("chat gpt four and chat gpt", rules)
        assert out == "GPT-4 and ChatGPT"

    def test_flexible_inner_whitespace(self):
        assert apply_replacements("open  ai wins", {"open ai": "OpenAI"}) == "OpenAI wins"

    def test_no_match_across_newline(self):
        assert apply_replacements("open\nai", {"open ai": "OpenAI"}) == "open\nai"


class TestSmartCase:
    def test_lowercase_replacement_mirrors_capitalized_match(self):
        assert apply_replacements("Gonna be late", {"gonna": "going to"}) == "Going to be late"

    def test_lowercase_replacement_mirrors_allcaps_match(self):
        assert apply_replacements("GONNA GO", {"gonna": "going to"}) == "GOING TO GO"

    def test_cased_replacement_taken_literally(self):
        # User-specified casing always wins, even mid-sentence or at start.
        assert apply_replacements("chat gpt is here", {"chat gpt": "ChatGPT"}) == "ChatGPT is here"
        assert apply_replacements("Chat Gpt is here", {"chat gpt": "ChatGPT"}) == "ChatGPT is here"

    def test_single_letter_capital_not_treated_as_allcaps(self):
        assert apply_replacements("I go", {"i": "we"}) == "We go"

    def test_lowercase_match_stays_lowercase(self):
        assert apply_replacements("gonna go", {"gonna": "going to"}) == "going to go"


class TestUnicode:
    def test_unicode_words(self):
        assert apply_replacements("die strasse ist lang", {"strasse": "Straße"}) == "die Straße ist lang"

    def test_unicode_boundary(self):
        # \w is unicode-aware: no match inside a longer word.
        assert apply_replacements("straßenbahn", {"bahn": "Bahn"}) == "straßenbahn"


class TestRemovalCleanup:
    """Empty replacement = delete-word; the hole it leaves must be tidied."""

    def test_no_double_space_after_removal(self):
        assert apply_replacements("delete um now", {"um": ""}) == "delete now"

    def test_leading_removal_trimmed(self):
        assert apply_replacements("um hello", {"um": ""}) == "hello"

    def test_orphaned_comma_cleaned(self):
        assert apply_replacements("so, um, yes", {"um": ""}) == "so, yes"

    def test_non_removal_rules_untouched_by_cleanup(self):
        # No removal fired: intentional spacing must never be "tidied".
        assert apply_replacements("a  b", {"x": "y"}) == "a  b"

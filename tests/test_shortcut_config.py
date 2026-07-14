# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Tests for shortcut string parsing, validation, and binding-map building."""

from types import SimpleNamespace

import pytest

from whisper_voice.shortcuts import (
    build_shortcut_map,
    normalize_shortcut,
    parse_shortcut,
    validate_shortcut,
)


def _config(proofread="ctrl+shift+g", rewrite="ctrl+shift+r", prompt="ctrl+shift+p", enabled=True):
    return SimpleNamespace(
        shortcuts=SimpleNamespace(
            enabled=enabled,
            proofread=proofread,
            rewrite=rewrite,
            prompt_engineer=prompt,
        )
    )


class TestParseShortcut:
    def test_basic(self):
        assert parse_shortcut("ctrl+shift+g") == ({"ctrl", "shift"}, "g")

    def test_alias_normalization(self):
        assert parse_shortcut("option+t") == ({"alt"}, "t")
        assert parse_shortcut("command+shift+p") == ({"cmd", "shift"}, "p")
        assert parse_shortcut("control+G") == ({"ctrl"}, "g")

    def test_whitespace_tolerated(self):
        assert parse_shortcut(" ctrl + shift + g ") == ({"ctrl", "shift"}, "g")

    def test_bare_key(self):
        assert parse_shortcut("f6") == (set(), "f6")

    def test_empty(self):
        assert parse_shortcut("") == (set(), "")


class TestNormalizeShortcut:
    def test_canonical_order_and_case(self):
        assert normalize_shortcut("Shift+Control+G") == "ctrl+shift+g"
        assert normalize_shortcut("cmd+alt+t") == "alt+cmd+t"

    def test_empty_stays_empty(self):
        assert normalize_shortcut("") == ""


class TestValidateShortcut:
    def test_valid_combos(self):
        assert validate_shortcut("ctrl+shift+g") is None
        assert validate_shortcut("alt+t") is None
        assert validate_shortcut("cmd+1") is None
        assert validate_shortcut("ctrl+.") is None
        assert validate_shortcut("f6") is None  # bare F-keys allowed
        assert validate_shortcut("") is None    # empty = disabled

    def test_unknown_modifier(self):
        assert "unknown modifier" in validate_shortcut("banana+g")

    def test_unsupported_key(self):
        assert "unsupported key" in validate_shortcut("ctrl+escape")

    def test_bare_typing_key_rejected(self):
        # A modifier-less letter would intercept ALL presses of that letter
        # and destroy normal typing system-wide.
        assert "modifier" in validate_shortcut("g")
        assert "modifier" in validate_shortcut("7")

    def test_missing_key(self):
        assert validate_shortcut("ctrl+") is not None


class TestBuildShortcutMap:
    def test_default_bindings(self):
        bindings, problems = build_shortcut_map(_config())
        assert problems == []
        assert bindings[("g", frozenset({"ctrl", "shift"}))] == "proofread"
        assert bindings[("r", frozenset({"ctrl", "shift"}))] == "rewrite"
        assert bindings[("p", frozenset({"ctrl", "shift"}))] == "prompt_engineer"

    def test_same_key_different_modifiers_coexist(self):
        bindings, problems = build_shortcut_map(
            _config(proofread="ctrl+shift+g", rewrite="cmd+g")
        )
        assert problems == []
        assert bindings[("g", frozenset({"ctrl", "shift"}))] == "proofread"
        assert bindings[("g", frozenset({"cmd"}))] == "rewrite"

    def test_exact_conflict_reported_and_skipped(self):
        bindings, problems = build_shortcut_map(
            _config(proofread="ctrl+shift+g", rewrite="shift+ctrl+g")
        )
        assert bindings[("g", frozenset({"ctrl", "shift"}))] == "proofread"
        assert any("conflict" in p for p in problems)

    def test_invalid_shortcut_reported_and_skipped(self):
        bindings, problems = build_shortcut_map(_config(rewrite="banana+r"))
        assert ("r", frozenset({"ctrl", "shift"})) not in bindings
        assert any("rewrite" in p for p in problems)
        # The other two still bind.
        assert len(bindings) == 2

    def test_empty_string_disables_mode(self):
        bindings, problems = build_shortcut_map(_config(prompt=""))
        assert problems == []
        assert len(bindings) == 2
        assert "prompt_engineer" not in bindings.values()

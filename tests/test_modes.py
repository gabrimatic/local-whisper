# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for backends/modes.py.

Covers the mode registry, lookup helpers, and the three prompt-builder
functions (Ollama, LM Studio, Apple Intelligence). No hardware, network,
or macOS frameworks involved.
"""

import sys
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Import helper
# ---------------------------------------------------------------------------

def _import_modes():
    for mod in list(sys.modules.keys()):
        if "whisper_voice" in mod:
            del sys.modules[mod]

    stubs = {
        "sounddevice": None,
        "AppKit": None,
        "Foundation": None,
        "Quartz": None,
    }
    with patch.dict("sys.modules", stubs):
        from whisper_voice.backends.modes import (
            MODE_REGISTRY,
            get_mode,
            get_all_modes,
            get_mode_ollama_prompt,
            get_mode_lm_studio_messages,
            get_mode_apple_intelligence_input,
            ModeNotFoundError,
            Mode,
        )
    return (
        MODE_REGISTRY,
        get_mode,
        get_all_modes,
        get_mode_ollama_prompt,
        get_mode_lm_studio_messages,
        get_mode_apple_intelligence_input,
        ModeNotFoundError,
        Mode,
    )


# ---------------------------------------------------------------------------
# TestModeRegistry
# ---------------------------------------------------------------------------

class TestModeRegistry:
    def test_registry_has_four_modes(self):
        registry, *_ = _import_modes()
        assert set(registry.keys()) == {"proofread", "rewrite", "prompt_engineer", "transcription"}

    def test_all_modes_have_required_fields(self):
        registry, *_, Mode = _import_modes()
        for key, mode in registry.items():
            assert mode.id, f"{key}: id is empty"
            assert mode.name, f"{key}: name is empty"
            assert mode.description, f"{key}: description is empty"
            assert mode.system_prompt, f"{key}: system_prompt is empty"
            assert mode.user_prompt_template, f"{key}: user_prompt_template is empty"
            # shortcut may be empty for transcription; just check it exists
            assert hasattr(mode, "shortcut")

    def test_mode_ids_match_keys(self):
        registry, *_ = _import_modes()
        for key, mode in registry.items():
            assert mode.id == key

    def test_user_prompt_templates_contain_text_placeholder(self):
        registry, *_ = _import_modes()
        for key, mode in registry.items():
            assert "{text}" in mode.user_prompt_template, f"{key}: missing {{text}} placeholder"


# ---------------------------------------------------------------------------
# TestGetMode
# ---------------------------------------------------------------------------

class TestGetMode:
    def test_valid_mode_returns_mode(self):
        _, get_mode, *_, Mode = _import_modes()
        result = get_mode("proofread")
        assert isinstance(result, Mode)
        assert result.id == "proofread"

    def test_unknown_mode_returns_none(self):
        _, get_mode, *_ = _import_modes()
        assert get_mode("nonexistent") is None


# ---------------------------------------------------------------------------
# TestGetAllModes
# ---------------------------------------------------------------------------

class TestGetAllModes:
    def test_returns_list_of_all_modes(self):
        _, _, get_all_modes, *_, Mode = _import_modes()
        modes = get_all_modes()
        assert len(modes) == 4
        assert all(isinstance(m, Mode) for m in modes)


# ---------------------------------------------------------------------------
# TestGetModeOllamaPrompt
# ---------------------------------------------------------------------------

class TestGetModeOllamaPrompt:
    def test_valid_prompt_contains_text(self):
        _, _, _, get_mode_ollama_prompt, *_ = _import_modes()
        result = get_mode_ollama_prompt("proofread", "hello world")
        assert "hello world" in result

    def test_valid_prompt_ends_with_output_marker(self):
        _, _, _, get_mode_ollama_prompt, *_ = _import_modes()
        result = get_mode_ollama_prompt("proofread", "hello world")
        assert result.endswith("Output:\n")

    def test_valid_prompt_contains_system_prompt(self):
        registry, _, _, get_mode_ollama_prompt, *_ = _import_modes()
        mode = registry["proofread"]
        result = get_mode_ollama_prompt("proofread", "hello world")
        assert mode.system_prompt in result

    def test_unknown_mode_raises_mode_not_found(self):
        _, _, _, get_mode_ollama_prompt, _, _, ModeNotFoundError, _ = _import_modes()
        with pytest.raises(ModeNotFoundError):
            get_mode_ollama_prompt("nonexistent", "hello")

    def test_empty_text_raises_value_error(self):
        _, _, _, get_mode_ollama_prompt, *_ = _import_modes()
        with pytest.raises(ValueError):
            get_mode_ollama_prompt("proofread", "")

    def test_none_text_raises_value_error(self):
        _, _, _, get_mode_ollama_prompt, *_ = _import_modes()
        with pytest.raises(ValueError):
            get_mode_ollama_prompt("proofread", None)

    @pytest.mark.parametrize("mode_id", ["proofread", "rewrite", "prompt_engineer", "transcription"])
    def test_all_modes_produce_valid_prompts(self, mode_id):
        _, _, _, get_mode_ollama_prompt, *_ = _import_modes()
        result = get_mode_ollama_prompt(mode_id, "sample text")
        assert "sample text" in result
        assert result.endswith("Output:\n")


# ---------------------------------------------------------------------------
# TestGetModeLmStudioMessages
# ---------------------------------------------------------------------------

class TestGetModeLmStudioMessages:
    def test_returns_two_messages(self):
        _, _, _, _, get_mode_lm_studio_messages, *_ = _import_modes()
        result = get_mode_lm_studio_messages("proofread", "hello")
        assert len(result) == 2

    def test_first_message_is_system(self):
        _, _, _, _, get_mode_lm_studio_messages, *_ = _import_modes()
        result = get_mode_lm_studio_messages("proofread", "hello")
        assert result[0]["role"] == "system"

    def test_second_message_is_user_with_text(self):
        _, _, _, _, get_mode_lm_studio_messages, *_ = _import_modes()
        result = get_mode_lm_studio_messages("proofread", "hello world")
        assert result[1]["role"] == "user"
        assert "hello world" in result[1]["content"]

    def test_unknown_mode_raises(self):
        _, _, _, _, get_mode_lm_studio_messages, _, ModeNotFoundError, _ = _import_modes()
        with pytest.raises(ModeNotFoundError):
            get_mode_lm_studio_messages("nonexistent", "hello")

    def test_empty_text_raises(self):
        _, _, _, _, get_mode_lm_studio_messages, *_ = _import_modes()
        with pytest.raises(ValueError):
            get_mode_lm_studio_messages("proofread", "")


# ---------------------------------------------------------------------------
# TestGetModeAppleIntelligenceInput
# ---------------------------------------------------------------------------

class TestGetModeAppleIntelligenceInput:
    def test_contains_separator(self):
        _, _, _, _, _, get_mode_apple_intelligence_input, *_ = _import_modes()
        result = get_mode_apple_intelligence_input("proofread", "hello")
        assert "\n---SEPARATOR---\n" in result

    def test_contains_text_and_system_prompt(self):
        registry, _, _, _, _, get_mode_apple_intelligence_input, *_ = _import_modes()
        mode = registry["proofread"]
        result = get_mode_apple_intelligence_input("proofread", "hello world")
        assert "hello world" in result
        assert mode.system_prompt in result

    def test_unknown_mode_raises(self):
        _, _, _, _, _, get_mode_apple_intelligence_input, ModeNotFoundError, _ = _import_modes()
        with pytest.raises(ModeNotFoundError):
            get_mode_apple_intelligence_input("nonexistent", "hello")

    def test_empty_text_raises(self):
        _, _, _, _, _, get_mode_apple_intelligence_input, *_ = _import_modes()
        with pytest.raises(ValueError):
            get_mode_apple_intelligence_input("proofread", "")

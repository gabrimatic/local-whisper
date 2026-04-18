# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for TOML helper deduplication behavior.
"""

from whisper_voice.config.toml_helpers import _replace_in_section


class TestReplaceInSection:
    def test_replaces_existing_key_without_duplication(self):
        content = "[qwen3_asr]\ntimeout = 0\nrepetition_context_size = 100\n"

        updated = _replace_in_section(content, "qwen3_asr", "repetition_context_size", "200")

        assert updated.count("repetition_context_size = 200") == 1
        assert "repetition_context_size = 100" not in updated

    def test_removes_duplicate_keys_in_same_section(self):
        content = (
            "[qwen3_asr]\n"
            "model = \"a\"\n"
            "model = \"b\"\n"
            "repetition_context_size = 50\n"
            "repetition_context_size = 100\n"
        )

        updated = _replace_in_section(content, "qwen3_asr", "model", '"c"')
        updated = _replace_in_section(updated, "qwen3_asr", "repetition_context_size", "200")

        assert updated.count('model = "c"') == 1
        assert updated.count("repetition_context_size = 200") == 1
        assert 'model = "a"' not in updated
        assert 'model = "b"' not in updated
        assert "repetition_context_size = 50" not in updated
        assert "repetition_context_size = 100" not in updated

    def test_inserts_key_when_missing(self):
        content = "[grammar]\nbackend = \"apple_intelligence\"\n"

        updated = _replace_in_section(content, "grammar", "enabled", "false")

        assert "enabled = false" in updated

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for TOML helper deduplication behavior.
"""

from whisper_voice.config.toml_helpers import _replace_in_section


class TestReplaceInSection:
    def test_replaces_existing_key_without_duplication(self):
        content = "[qwen3_asr]\nlanguage = \"auto\"\ntimeout = 0\n"

        updated = _replace_in_section(content, "qwen3_asr", "language", '"en"')

        assert updated.count('language = "en"') == 1
        assert 'language = "auto"' not in updated

    def test_removes_duplicate_keys_in_same_section(self):
        content = (
            "[qwen3_asr]\n"
            "language = \"en\"\n"
            "model = \"foo\"\n"
            "language = \"auto\"\n"
            "prefill_step_size = 4096\n"
            "prefill_step_size = 8192\n"
        )

        updated = _replace_in_section(content, "qwen3_asr", "language", '"de"')
        updated = _replace_in_section(updated, "qwen3_asr", "prefill_step_size", "8192")

        assert updated.count('language = "de"') == 1
        assert updated.count("prefill_step_size = 8192") == 1
        assert 'language = "auto"' not in updated
        assert "prefill_step_size = 4096" not in updated

    def test_inserts_key_when_missing(self):
        content = "[grammar]\nbackend = \"apple_intelligence\"\n"

        updated = _replace_in_section(content, "grammar", "enabled", "false")

        assert "enabled = false" in updated

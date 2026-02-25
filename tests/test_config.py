# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for config.py.

All tests use temporary directories and never touch ~/.whisper/.
"""

import importlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config_from(tmp_path: Path, toml_content: str | None = None):
    """
    Load config using a custom CONFIG_FILE path inside tmp_path.
    Reloads the module so the module-level globals are re-evaluated
    with the patched paths each time.
    """
    cfg_file = tmp_path / "config.toml"
    if toml_content is not None:
        cfg_file.write_text(toml_content, encoding="utf-8")

    # Remove cached module so constants are re-evaluated with fresh paths
    for mod in list(sys.modules.keys()):
        if "whisper_voice" in mod:
            del sys.modules[mod]

    with patch("whisper_voice.config.CONFIG_DIR", tmp_path), \
         patch("whisper_voice.config.CONFIG_FILE", cfg_file):
        from whisper_voice import config as cfg_mod
        # Also patch the module-level references that load_config uses
        cfg_mod.CONFIG_DIR = tmp_path
        cfg_mod.CONFIG_FILE = cfg_file
        # Reset global singleton so load_config runs fresh
        cfg_mod._config = None
        result = cfg_mod.load_config()
        return result, cfg_mod


# ---------------------------------------------------------------------------
# Basic loading
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_missing_file_returns_defaults(self, tmp_path):
        """Missing config file should write defaults and return a valid Config."""
        config, _ = _load_config_from(tmp_path, toml_content=None)
        # File should now exist (created by load_config)
        assert (tmp_path / "config.toml").exists()
        # Default engine
        assert config.transcription.engine == "qwen3_asr"

    def test_valid_toml_loads_values(self, tmp_path):
        toml = """
[transcription]
engine = "whisperkit"

[qwen3_asr]
model = "mlx-community/Qwen3-ASR-1.7B-8bit"
prefill_step_size = 2048
"""
        config, _ = _load_config_from(tmp_path, toml)
        assert config.transcription.engine == "whisperkit"
        assert config.qwen3_asr.model == "mlx-community/Qwen3-ASR-1.7B-8bit"
        assert config.qwen3_asr.prefill_step_size == 2048

    def test_invalid_toml_returns_defaults(self, tmp_path):
        """Corrupt TOML must not crash; should fall back to defaults."""
        (tmp_path / "config.toml").write_text("[[[ not valid toml", encoding="utf-8")
        config, _ = _load_config_from(tmp_path)
        # Falls back gracefully
        assert config.transcription.engine == "qwen3_asr"

    def test_empty_toml_returns_defaults(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert config.transcription.engine == "qwen3_asr"


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

class TestDefaultValues:
    def test_engine_default(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert config.transcription.engine == "qwen3_asr"

    def test_model_default(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert "bf16" in config.qwen3_asr.model

    def test_prefill_step_size_default(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert config.qwen3_asr.prefill_step_size == 4096

    def test_grammar_disabled_by_default(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert config.grammar.enabled is False

    def test_hotkey_default(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert config.hotkey.key == "alt_r"

    def test_sample_rate_default(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert config.audio.sample_rate == 16000

    def test_history_limit_default(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert config.backup.history_limit == 100

    def test_overlay_opacity_default(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert 0.0 < config.ui.overlay_opacity <= 1.0


# ---------------------------------------------------------------------------
# Validation / sanitization
# ---------------------------------------------------------------------------

class TestValidation:
    def test_invalid_engine_falls_back(self, tmp_path):
        toml = "[transcription]\nengine = \"nonexistent_engine\"\n"
        config, _ = _load_config_from(tmp_path, toml)
        assert config.transcription.engine == "qwen3_asr"

    def test_invalid_hotkey_falls_back(self, tmp_path):
        toml = "[hotkey]\nkey = \"super_hyper_key\"\n"
        config, _ = _load_config_from(tmp_path, toml)
        assert config.hotkey.key == "alt_r"

    def test_invalid_url_falls_back(self, tmp_path):
        toml = "[whisper]\nurl = \"not-a-url\"\n"
        config, _ = _load_config_from(tmp_path, toml)
        assert config.whisper.url.startswith("http")

    def test_history_limit_clamped_high(self, tmp_path):
        toml = "[backup]\nhistory_limit = 9999\n"
        config, _ = _load_config_from(tmp_path, toml)
        assert config.backup.history_limit <= 1000

    def test_history_limit_clamped_low(self, tmp_path):
        toml = "[backup]\nhistory_limit = 0\n"
        config, _ = _load_config_from(tmp_path, toml)
        assert config.backup.history_limit >= 1

    def test_overlay_opacity_clamped(self, tmp_path):
        toml = "[ui]\noverlay_opacity = 5.0\n"
        config, _ = _load_config_from(tmp_path, toml)
        assert 0.0 <= config.ui.overlay_opacity <= 1.0

    def test_negative_sample_rate_falls_back(self, tmp_path):
        toml = "[audio]\nsample_rate = -100\n"
        config, _ = _load_config_from(tmp_path, toml)
        assert config.audio.sample_rate > 0

    def test_pre_buffer_clamped(self, tmp_path):
        toml = "[audio]\npre_buffer = 999.0\n"
        config, _ = _load_config_from(tmp_path, toml)
        assert config.audio.pre_buffer <= 1.0

    def test_grammar_backend_none_disables_grammar(self, tmp_path):
        toml = "[grammar]\nbackend = \"none\"\nenabled = true\n"
        config, _ = _load_config_from(tmp_path, toml)
        assert config.grammar.enabled is False


# ---------------------------------------------------------------------------
# update_config_field round-trip
# ---------------------------------------------------------------------------

class TestUpdateConfigField:
    def test_update_string_field(self, tmp_path):
        from whisper_voice import config as cfg_mod
        toml = "[qwen3_asr]\nmodel = \"mlx-community/Qwen3-ASR-1.7B-bf16\"\nlanguage = \"auto\"\ntimeout = 0\nprefill_step_size = 4096\n"
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(toml, encoding="utf-8")

        # Reload module with patched paths
        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]

        with patch("whisper_voice.config.CONFIG_DIR", tmp_path), \
             patch("whisper_voice.config.CONFIG_FILE", cfg_file):
            from whisper_voice import config as cfg_mod
            cfg_mod.CONFIG_DIR = tmp_path
            cfg_mod.CONFIG_FILE = cfg_file
            cfg_mod._config = None

            cfg_mod.update_config_field("qwen3_asr", "language", "en")
            written = cfg_file.read_text(encoding="utf-8")
            assert 'language = "en"' in written

    def test_update_bool_field(self, tmp_path):
        from whisper_voice import config as cfg_mod
        toml = "[grammar]\nbackend = \"apple_intelligence\"\nenabled = false\n"
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(toml, encoding="utf-8")

        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]

        with patch("whisper_voice.config.CONFIG_DIR", tmp_path), \
             patch("whisper_voice.config.CONFIG_FILE", cfg_file):
            from whisper_voice import config as cfg_mod
            cfg_mod.CONFIG_DIR = tmp_path
            cfg_mod.CONFIG_FILE = cfg_file
            cfg_mod._config = None
            cfg_mod.load_config()  # prime singleton

            cfg_mod.update_config_field("grammar", "enabled", True)
            written = cfg_file.read_text(encoding="utf-8")
            assert "enabled = true" in written

    def test_update_int_field(self, tmp_path):
        toml = "[qwen3_asr]\nmodel = \"m\"\nlanguage = \"auto\"\ntimeout = 0\nprefill_step_size = 4096\n"
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(toml, encoding="utf-8")

        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]

        with patch("whisper_voice.config.CONFIG_DIR", tmp_path), \
             patch("whisper_voice.config.CONFIG_FILE", cfg_file):
            from whisper_voice import config as cfg_mod
            cfg_mod.CONFIG_DIR = tmp_path
            cfg_mod.CONFIG_FILE = cfg_file
            cfg_mod._config = None
            cfg_mod.load_config()

            cfg_mod.update_config_field("qwen3_asr", "prefill_step_size", 8192)
            written = cfg_file.read_text(encoding="utf-8")
            assert "prefill_step_size = 8192" in written


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_replace_in_section_replaces_string(self):
        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]
        from whisper_voice.config import _replace_in_section
        content = '[qwen3_asr]\nmodel = "old-model"\n'
        result = _replace_in_section(content, "qwen3_asr", "model", '"new-model"')
        assert '"new-model"' in result
        assert '"old-model"' not in result

    def test_replace_in_section_replaces_bool(self):
        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]
        from whisper_voice.config import _replace_in_section
        content = '[grammar]\nenabled = false\n'
        result = _replace_in_section(content, "grammar", "enabled", "true")
        assert "enabled = true" in result

    def test_find_in_section_finds_string(self):
        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]
        from whisper_voice.config import _find_in_section
        content = '[transcription]\nengine = "whisperkit"\n'
        assert _find_in_section(content, "transcription", "engine") == "whisperkit"

    def test_find_in_section_returns_none_for_missing_key(self):
        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]
        from whisper_voice.config import _find_in_section
        content = '[transcription]\nengine = "qwen3_asr"\n'
        assert _find_in_section(content, "transcription", "nonexistent") is None

    def test_serialize_toml_value_bool(self):
        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]
        from whisper_voice.config import _serialize_toml_value
        assert _serialize_toml_value(True) == "true"
        assert _serialize_toml_value(False) == "false"

    def test_serialize_toml_value_int(self):
        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]
        from whisper_voice.config import _serialize_toml_value
        assert _serialize_toml_value(42) == "42"

    def test_serialize_toml_value_string(self):
        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]
        from whisper_voice.config import _serialize_toml_value
        assert _serialize_toml_value("hello") == '"hello"'

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for config.py.

All tests use temporary directories and never touch ~/.whisper/.
"""

import sys
from pathlib import Path

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

    # Remove cached modules so they re-import fresh
    for mod in list(sys.modules.keys()):
        if "whisper_voice" in mod:
            del sys.modules[mod]

    import whisper_voice.config.loader as loader_mod
    import whisper_voice.config.schema as schema_mod
    from whisper_voice import config as cfg_mod

    # Patch the canonical source; both loader and mutations read through schema module
    schema_mod.CONFIG_DIR = tmp_path
    schema_mod.CONFIG_FILE = cfg_file
    # Reset singleton so load_config runs fresh
    loader_mod._config = None

    result = loader_mod.load_config()
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
        assert config.transcription.engine == "parakeet_v3"

    def test_valid_toml_loads_values(self, tmp_path):
        toml = """
[transcription]
engine = "whisperkit"

[qwen3_asr]
model = "mlx-community/Qwen3-ASR-1.7B-8bit"
repetition_context_size = 50
"""
        config, _ = _load_config_from(tmp_path, toml)
        assert config.transcription.engine == "whisperkit"
        assert config.qwen3_asr.model == "mlx-community/Qwen3-ASR-1.7B-8bit"
        assert config.qwen3_asr.repetition_context_size == 50

    def test_invalid_toml_returns_defaults(self, tmp_path):
        """Corrupt TOML must not crash; should fall back to defaults."""
        (tmp_path / "config.toml").write_text("[[[ not valid toml", encoding="utf-8")
        config, _ = _load_config_from(tmp_path)
        # Falls back gracefully
        assert config.transcription.engine == "parakeet_v3"

    def test_empty_toml_returns_defaults(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert config.transcription.engine == "parakeet_v3"

    def test_legacy_qwen_default_config_migrates_to_parakeet(self, tmp_path):
        toml = """
[transcription]
# Transcription engine: "qwen3_asr" (default) or "whisperkit"
engine = "qwen3_asr"

[qwen3_asr]
model = "mlx-community/Qwen3-ASR-1.7B-bf16"
"""
        config, _ = _load_config_from(tmp_path, toml)
        content = (tmp_path / "config.toml").read_text(encoding="utf-8")

        assert config.transcription.engine == "parakeet_v3"
        assert "[parakeet_v3]" in content
        assert 'engine = "parakeet_v3"' in content


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

class TestDefaultValues:
    def test_engine_default(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert config.transcription.engine == "parakeet_v3"

    def test_model_default(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert "bf16" in config.qwen3_asr.model

    def test_whisperkit_best_model_default(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert config.whisper.model == "large-v3-v20240930_626MB"

    def test_apple_speech_defaults(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert config.apple_speech.locale == "en-US"
        assert config.apple_speech.timeout == 0

    def test_apple_speech_config_loads(self, tmp_path):
        config, _ = _load_config_from(
            tmp_path,
            toml_content='[transcription]\nengine = "apple_speech"\n[apple_speech]\nlocale = "de-DE"\ntimeout = 45\n',
        )
        assert config.transcription.engine == "apple_speech"
        assert config.apple_speech.locale == "de-DE"
        assert config.apple_speech.timeout == 45

    def test_apple_speech_config_sanitizes_locale_and_timeout(self, tmp_path):
        config, _ = _load_config_from(
            tmp_path,
            toml_content='[apple_speech]\nlocale = "  de_DE  "\ntimeout = -4\n',
        )
        assert config.apple_speech.locale == "de-DE"
        assert config.apple_speech.timeout == 0

    def test_repetition_context_size_default(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert config.qwen3_asr.repetition_context_size == 100

    def test_max_tokens_default(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert config.qwen3_asr.max_tokens == 0

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

    def test_service_idle_unload_default(self, tmp_path):
        config, _ = _load_config_from(tmp_path, toml_content="")
        assert config.service.idle_unload_minutes == 20

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
        assert config.transcription.engine == "parakeet_v3"

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

    def test_service_idle_unload_loads_from_config(self, tmp_path):
        toml = "[service]\nidle_unload_minutes = 0\n"
        config, _ = _load_config_from(tmp_path, toml)
        assert config.service.idle_unload_minutes == 0

    def test_negative_service_idle_unload_falls_back(self, tmp_path):
        toml = "[service]\nidle_unload_minutes = -5\n"
        config, _ = _load_config_from(tmp_path, toml)
        assert config.service.idle_unload_minutes == 20

    def test_boolean_service_idle_unload_falls_back(self, tmp_path):
        toml = "[service]\nidle_unload_minutes = true\n"
        config, _ = _load_config_from(tmp_path, toml)
        assert config.service.idle_unload_minutes == 20


# ---------------------------------------------------------------------------
# update_config_field round-trip
# ---------------------------------------------------------------------------

class TestUpdateConfigField:
    def test_update_string_field(self, tmp_path):
        toml = "[qwen3_asr]\nmodel = \"mlx-community/Qwen3-ASR-1.7B-bf16\"\ntimeout = 0\n"
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(toml, encoding="utf-8")

        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]

        import whisper_voice.config.loader as loader_mod
        import whisper_voice.config.schema as schema_mod
        from whisper_voice import config as cfg_mod
        schema_mod.CONFIG_DIR = tmp_path
        schema_mod.CONFIG_FILE = cfg_file
        loader_mod._config = None

        cfg_mod.update_config_field("qwen3_asr", "model", "mlx-community/Qwen3-ASR-1.7B-8bit")
        written = cfg_file.read_text(encoding="utf-8")
        assert 'model = "mlx-community/Qwen3-ASR-1.7B-8bit"' in written

    def test_update_bool_field(self, tmp_path):
        toml = "[grammar]\nbackend = \"apple_intelligence\"\nenabled = false\n"
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(toml, encoding="utf-8")

        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]

        import whisper_voice.config.loader as loader_mod
        import whisper_voice.config.schema as schema_mod
        from whisper_voice import config as cfg_mod
        schema_mod.CONFIG_DIR = tmp_path
        schema_mod.CONFIG_FILE = cfg_file
        loader_mod._config = None
        loader_mod.load_config()  # prime singleton

        cfg_mod.update_config_field("grammar", "enabled", True)
        written = cfg_file.read_text(encoding="utf-8")
        assert "enabled = true" in written

    def test_update_int_field(self, tmp_path):
        toml = "[qwen3_asr]\nmodel = \"m\"\ntimeout = 0\nrepetition_context_size = 100\n"
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(toml, encoding="utf-8")

        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]

        import whisper_voice.config.loader as loader_mod
        import whisper_voice.config.schema as schema_mod
        from whisper_voice import config as cfg_mod
        schema_mod.CONFIG_DIR = tmp_path
        schema_mod.CONFIG_FILE = cfg_file
        loader_mod._config = None
        loader_mod.load_config()

        cfg_mod.update_config_field("qwen3_asr", "repetition_context_size", 200)
        written = cfg_file.read_text(encoding="utf-8")
        assert "repetition_context_size = 200" in written

    def test_update_parakeet_section_updates_in_memory_config(self, tmp_path):
        # Regression: the [parakeet_v3] TOML section is backed by the
        # Config.parakeet attribute. update_config_field must sync BOTH,
        # otherwise the engine reloads the old model until service restart.
        toml = '[parakeet_v3]\nmodel = "mlx-community/parakeet-tdt-0.6b-v3"\n'
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(toml, encoding="utf-8")

        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]

        import whisper_voice.config.loader as loader_mod
        import whisper_voice.config.schema as schema_mod
        from whisper_voice import config as cfg_mod
        schema_mod.CONFIG_DIR = tmp_path
        schema_mod.CONFIG_FILE = cfg_file
        loader_mod._config = None
        loader_mod.load_config()

        cfg_mod.update_config_field("parakeet_v3", "model", "mlx-community/parakeet-tdt-1.1b")
        written = cfg_file.read_text(encoding="utf-8")
        assert 'model = "mlx-community/parakeet-tdt-1.1b"' in written
        assert cfg_mod.get_config().parakeet.model == "mlx-community/parakeet-tdt-1.1b"

    def test_update_writes_atomically(self, tmp_path):
        # The rewrite must go through a temp file + os.replace so a crash
        # mid-write can't truncate config.toml; no temp file may linger.
        toml = "[grammar]\nbackend = \"apple_intelligence\"\nenabled = false\n"
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(toml, encoding="utf-8")

        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]

        import whisper_voice.config.loader as loader_mod
        import whisper_voice.config.schema as schema_mod
        from whisper_voice import config as cfg_mod
        schema_mod.CONFIG_DIR = tmp_path
        schema_mod.CONFIG_FILE = cfg_file
        loader_mod._config = None
        loader_mod.load_config()

        assert cfg_mod.update_config_field("grammar", "enabled", True) is True
        assert "enabled = true" in cfg_file.read_text(encoding="utf-8")
        assert not (tmp_path / "config.toml.tmp").exists()

    def test_cli_writers_share_locked_atomic_rewrite(self, tmp_path, monkeypatch):
        # Regression: `wh engine`/`wh backend` used their own flock on
        # config.toml itself with non-atomic writes — invisible to the
        # service's sidecar lock, and re-writing an existing value inserted
        # a duplicate key. Both must go through _locked_config_rewrite.
        import tomllib

        toml = '[transcription]\nengine = "parakeet_v3"\n[grammar]\nbackend = "none"\nenabled = false\n'
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(toml, encoding="utf-8")

        for mod in list(sys.modules.keys()):
            if "whisper_voice" in mod:
                del sys.modules[mod]

        import whisper_voice.config.schema as schema_mod
        from whisper_voice.cli import lifecycle
        schema_mod.CONFIG_DIR = tmp_path
        schema_mod.CONFIG_FILE = cfg_file
        monkeypatch.setattr(lifecycle, "_get_config_path", lambda: cfg_file)

        # Writing the same value twice must not duplicate the key.
        assert lifecycle._write_config_engine("parakeet_v3") is True
        assert lifecycle._write_config_engine("parakeet_v3") is True
        assert lifecycle._write_config_backend("ollama") is True

        written = cfg_file.read_text(encoding="utf-8")
        parsed = tomllib.loads(written)  # raises on duplicate keys
        assert parsed["transcription"]["engine"] == "parakeet_v3"
        assert parsed["grammar"]["backend"] == "ollama"
        assert parsed["grammar"]["enabled"] is True
        assert not (tmp_path / "config.toml.tmp").exists()


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

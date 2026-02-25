# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for the engine and backend registries.

Does NOT instantiate any engine or backend (they require hardware/servers).
Tests only registry structure, factory error behavior, and LANGUAGE_MAP.
"""

import sys
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Module import helpers (avoid pulling in rumps/AppKit/sounddevice)
# ---------------------------------------------------------------------------

def _import_engine_registry():
    for mod in list(sys.modules.keys()):
        if "whisper_voice" in mod:
            del sys.modules[mod]
    # Stub out modules that require hardware or macOS frameworks
    stubs = {
        "rumps": None,
        "sounddevice": None,
        "AppKit": None,
        "Foundation": None,
        "Quartz": None,
        "mlx": None,
        "mlx.core": None,
        "mlx_audio": None,
    }
    with patch.dict("sys.modules", stubs):
        from whisper_voice.engines import ENGINE_REGISTRY, create_engine
    return ENGINE_REGISTRY, create_engine


def _import_backend_registry():
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
        from whisper_voice.backends import BACKEND_REGISTRY, create_backend
    return BACKEND_REGISTRY, create_backend


def _import_language_map():
    for mod in list(sys.modules.keys()):
        if "whisper_voice" in mod:
            del sys.modules[mod]
    stubs = {
        "mlx": None,
        "mlx.core": None,
        "mlx_audio": None,
        "sounddevice": None,
        "AppKit": None,
        "Foundation": None,
        "rumps": None,
    }
    with patch.dict("sys.modules", stubs):
        from whisper_voice.engines.qwen3_asr import LANGUAGE_MAP
    return LANGUAGE_MAP


# ---------------------------------------------------------------------------
# ENGINE_REGISTRY
# ---------------------------------------------------------------------------

class TestEngineRegistry:
    def test_qwen3_asr_registered(self):
        registry, _ = _import_engine_registry()
        assert "qwen3_asr" in registry

    def test_whisperkit_registered(self):
        registry, _ = _import_engine_registry()
        assert "whisperkit" in registry

    def test_engine_info_has_required_fields(self):
        registry, _ = _import_engine_registry()
        for key, info in registry.items():
            assert hasattr(info, "id"), f"Engine {key} missing 'id'"
            assert hasattr(info, "name"), f"Engine {key} missing 'name'"
            assert hasattr(info, "description"), f"Engine {key} missing 'description'"
            assert hasattr(info, "factory"), f"Engine {key} missing 'factory'"
            assert callable(info.factory), f"Engine {key} factory is not callable"

    def test_engine_id_matches_key(self):
        registry, _ = _import_engine_registry()
        for key, info in registry.items():
            assert info.id == key

    def test_create_engine_raises_for_unknown(self):
        _, create_engine = _import_engine_registry()
        with pytest.raises(ValueError, match="Unknown engine"):
            create_engine("definitely_not_a_real_engine")

    def test_error_message_lists_available_engines(self):
        _, create_engine = _import_engine_registry()
        try:
            create_engine("bogus")
        except ValueError as e:
            assert "qwen3_asr" in str(e) or "whisperkit" in str(e)

    def test_registry_is_dict(self):
        registry, _ = _import_engine_registry()
        assert isinstance(registry, dict)

    def test_at_least_two_engines(self):
        registry, _ = _import_engine_registry()
        assert len(registry) >= 2


# ---------------------------------------------------------------------------
# BACKEND_REGISTRY
# ---------------------------------------------------------------------------

class TestBackendRegistry:
    def test_apple_intelligence_registered(self):
        registry, _ = _import_backend_registry()
        assert "apple_intelligence" in registry

    def test_ollama_registered(self):
        registry, _ = _import_backend_registry()
        assert "ollama" in registry

    def test_lm_studio_registered(self):
        registry, _ = _import_backend_registry()
        assert "lm_studio" in registry

    def test_backend_info_has_required_fields(self):
        registry, _ = _import_backend_registry()
        for key, info in registry.items():
            assert hasattr(info, "id"), f"Backend {key} missing 'id'"
            assert hasattr(info, "name"), f"Backend {key} missing 'name'"
            assert hasattr(info, "description"), f"Backend {key} missing 'description'"
            assert hasattr(info, "factory"), f"Backend {key} missing 'factory'"
            assert callable(info.factory), f"Backend {key} factory is not callable"

    def test_backend_id_matches_key(self):
        registry, _ = _import_backend_registry()
        for key, info in registry.items():
            assert info.id == key

    def test_create_backend_raises_for_unknown(self):
        _, create_backend = _import_backend_registry()
        with pytest.raises(ValueError, match="Unknown backend"):
            create_backend("totally_fake_backend")

    def test_error_message_lists_available_backends(self):
        _, create_backend = _import_backend_registry()
        try:
            create_backend("bogus")
        except ValueError as e:
            assert "ollama" in str(e) or "apple_intelligence" in str(e)

    def test_registry_is_dict(self):
        registry, _ = _import_backend_registry()
        assert isinstance(registry, dict)

    def test_at_least_three_backends(self):
        registry, _ = _import_backend_registry()
        assert len(registry) >= 3


# ---------------------------------------------------------------------------
# LANGUAGE_MAP
# ---------------------------------------------------------------------------

class TestLanguageMap:
    REQUIRED_CODES = ["en", "fa", "de", "fr", "es", "ja", "zh", "ko"]

    def test_required_language_codes_present(self):
        lmap = _import_language_map()
        for code in self.REQUIRED_CODES:
            assert code in lmap, f"Missing language code: {code}"

    def test_no_auto_key(self):
        lmap = _import_language_map()
        assert "auto" not in lmap, "'auto' should not be in LANGUAGE_MAP"

    def test_all_values_are_strings(self):
        lmap = _import_language_map()
        for code, name in lmap.items():
            assert isinstance(name, str), f"Language name for '{code}' is not a string"

    def test_all_keys_are_lowercase(self):
        lmap = _import_language_map()
        for code in lmap:
            assert code == code.lower(), f"Language code '{code}' is not lowercase"

    def test_all_values_non_empty(self):
        lmap = _import_language_map()
        for code, name in lmap.items():
            assert name.strip(), f"Language name for '{code}' is empty"

    def test_english_maps_to_english(self):
        lmap = _import_language_map()
        assert lmap["en"] == "English"

    def test_persian_mapped(self):
        lmap = _import_language_map()
        # fa = Persian/Farsi
        assert "fa" in lmap

    def test_map_is_dict(self):
        lmap = _import_language_map()
        assert isinstance(lmap, dict)

    def test_at_least_ten_languages(self):
        lmap = _import_language_map()
        assert len(lmap) >= 10

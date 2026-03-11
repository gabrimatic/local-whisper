# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for Kokoro TTS provider resource cleanup.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from conftest import import_with_stubs


def _import_kokoro_module():
    fake_sd = SimpleNamespace(stop=Mock())
    fake_mx_core = SimpleNamespace(clear_cache=Mock())
    mod = import_with_stubs(
        "whisper_voice.tts.kokoro_tts",
        extra_stubs={
            "sounddevice": fake_sd,
            "mlx": SimpleNamespace(core=fake_mx_core),
            "mlx.core": fake_mx_core,
        },
    )
    return mod, fake_sd, fake_mx_core


KOKORO_MOD, FAKE_SD, FAKE_MX_CORE = _import_kokoro_module()


class TestKokoroTTSProvider:
    def setup_method(self):
        FAKE_SD.stop.reset_mock()
        FAKE_MX_CORE.clear_cache.reset_mock()

    def test_refresh_releases_previous_model_when_model_changes(self):
        provider = KOKORO_MOD.KokoroTTSProvider()
        old_model = Mock()
        provider._model = old_model
        provider._model_id = "old-model"

        with patch.object(KOKORO_MOD, "_clear_runtime_cache") as clear_runtime_cache:
            provider.refresh("new-model")

        old_model.close.assert_called_once()
        clear_runtime_cache.assert_called_once()
        assert provider._model is None
        assert provider._model_id == "new-model"

    def test_speak_clears_runtime_cache_after_synthesis(self):
        provider = KOKORO_MOD.KokoroTTSProvider()
        provider._model = Mock()
        provider._model_id = "test-model"
        stop_event = Mock(is_set=Mock(return_value=False))

        with patch.object(provider, "_load_model", return_value=True), \
             patch.object(KOKORO_MOD, "_synthesize_and_play") as synthesize, \
             patch.object(KOKORO_MOD, "_clear_runtime_cache") as clear_runtime_cache:
            provider.speak("hello world", stop_event, speaker="af_bella")

        synthesize.assert_called_once()
        clear_runtime_cache.assert_called_once()

    def test_close_stops_audio_and_releases_model(self):
        provider = KOKORO_MOD.KokoroTTSProvider()
        model = Mock()
        provider._model = model
        provider._model_id = "test-model"

        with patch.object(KOKORO_MOD, "_clear_runtime_cache") as clear_runtime_cache:
            provider.close()

        FAKE_SD.stop.assert_called_once()
        model.close.assert_called_once()
        clear_runtime_cache.assert_called_once()
        assert provider._model is None
        assert provider._model_id == ""

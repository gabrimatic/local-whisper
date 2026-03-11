# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for Qwen3-ASR runtime cache cleanup.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from conftest import import_with_stubs


def _import_qwen_module():
    fake_mx_core = SimpleNamespace(clear_cache=Mock())
    mod = import_with_stubs(
        "whisper_voice.engines.qwen3_asr",
        extra_stubs={
            "mlx": SimpleNamespace(core=fake_mx_core),
            "mlx.core": fake_mx_core,
        },
    )
    return mod, fake_mx_core


QWEN_MOD, FAKE_MX_CORE = _import_qwen_module()


class TestQwen3ASRCleanup:
    def setup_method(self):
        FAKE_MX_CORE.clear_cache.reset_mock()

    def test_transcribe_clears_runtime_cache_on_success(self):
        engine = QWEN_MOD.Qwen3ASREngine()
        engine._model = Mock()
        engine._model.transcribe.return_value = SimpleNamespace(text=" hello ")

        with patch.object(engine, "_clear_runtime_cache") as clear_runtime_cache:
            text, err = engine.transcribe("fake.wav")

        assert text == "hello"
        assert err is None
        clear_runtime_cache.assert_called_once()

    def test_transcribe_clears_runtime_cache_on_error(self):
        engine = QWEN_MOD.Qwen3ASREngine()
        engine._model = Mock()
        engine._model.transcribe.side_effect = RuntimeError("boom")

        with patch.object(engine, "_clear_runtime_cache") as clear_runtime_cache:
            text, err = engine.transcribe("fake.wav")

        assert text is None
        assert err == "boom"
        clear_runtime_cache.assert_called_once()

    def test_close_releases_model_and_clears_runtime_cache(self):
        engine = QWEN_MOD.Qwen3ASREngine()
        model = Mock()
        engine._model = model

        with patch.object(engine, "_clear_runtime_cache") as clear_runtime_cache:
            engine.close()

        model.close.assert_called_once()
        clear_runtime_cache.assert_called_once()
        assert engine._model is None

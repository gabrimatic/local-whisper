# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for memory-conscious audio handling.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from conftest import import_with_stubs


def _fake_config():
    return SimpleNamespace(audio=SimpleNamespace(sample_rate=16000, pre_buffer=0.0))


class TestRecorderMemory:
    def test_stop_clears_accumulated_chunks(self):
        fake_sd = SimpleNamespace(InputStream=Mock())
        with patch.dict("sys.modules", {"sounddevice": fake_sd}):
            import whisper_voice.audio as audio_mod

        with patch.object(audio_mod, "get_config", return_value=_fake_config()):
            recorder = audio_mod.Recorder()

        recorder._recording.set()
        recorder._chunks = [
            np.array([0.1, 0.2], dtype=np.float32),
            np.array([0.3], dtype=np.float32),
        ]

        audio = recorder.stop()

        assert np.allclose(audio, np.array([0.1, 0.2, 0.3], dtype=np.float32))
        assert recorder._chunks == []


class TestAudioProcessorMemory:
    def test_raw_audio_reuses_original_float32_buffer(self):
        mod = import_with_stubs("whisper_voice.audio_processor")
        cfg = SimpleNamespace(audio=SimpleNamespace(
            vad_enabled=False,
            noise_reduction=False,
            normalize_audio=False,
        ))
        proc = mod.AudioProcessor(cfg)
        audio = np.array([0.1, -0.2, 0.3], dtype=np.float32)

        result = proc.process(audio, 16000)

        assert result.raw_audio is audio
        assert np.allclose(result.audio, audio)

    def test_segment_long_audio_reuses_float32_views(self):
        mod = import_with_stubs("whisper_voice.audio_processor")
        cfg = SimpleNamespace(audio=SimpleNamespace(
            vad_enabled=False,
            noise_reduction=False,
            normalize_audio=False,
        ))
        proc = mod.AudioProcessor(cfg)
        sample_rate = 16000
        audio = np.zeros(304 * sample_rate, dtype=np.float32)

        chunks = proc.segment_long_audio(audio, sample_rate)

        assert len(chunks) == 2
        assert all(chunk.dtype == np.float32 for chunk in chunks)
        assert all(np.shares_memory(chunk, audio) for chunk in chunks)

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for AudioProcessor.

Uses numpy-generated synthetic audio. No microphone or real recordings needed.
"""

import sys
from dataclasses import dataclass, field
from unittest.mock import patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Minimal config stubs (no disk access, no hardware)
# ---------------------------------------------------------------------------

@dataclass
class _AudioConfig:
    sample_rate: int = 16000
    min_duration: float = 0.0
    max_duration: int = 0
    min_rms: float = 0.005
    vad_enabled: bool = True
    noise_reduction: bool = True
    normalize_audio: bool = True
    pre_buffer: float = 0.0


@dataclass
class _Config:
    audio: _AudioConfig = field(default_factory=_AudioConfig)


def _make_processor(vad=True, noise_reduction=True, normalize=True):
    """Create an AudioProcessor with a lightweight stub config."""
    # Clean up cached modules so imports resolve fresh
    for mod in list(sys.modules.keys()):
        if "whisper_voice" in mod:
            del sys.modules[mod]

    audio_cfg = _AudioConfig(vad_enabled=vad, noise_reduction=noise_reduction, normalize_audio=normalize)
    cfg = _Config(audio=audio_cfg)

    # Patch get_config so the module doesn't touch disk or load assets
    with patch.dict("sys.modules", {
        "rumps": None,
        "sounddevice": None,
        "AppKit": None,
        "Foundation": None,
        "Quartz": None,
    }):
        from whisper_voice.audio_processor import AudioProcessor
    return AudioProcessor(cfg), AudioProcessor


SAMPLE_RATE = 16000


def _silence(duration_s: float) -> np.ndarray:
    """All-zero audio (pure silence)."""
    return np.zeros(int(SAMPLE_RATE * duration_s), dtype=np.float32)


def _sine(duration_s: float, freq: float = 440.0, amplitude: float = 0.3) -> np.ndarray:
    """Sine wave at the given frequency (clean speech surrogate)."""
    t = np.linspace(0, duration_s, int(SAMPLE_RATE * duration_s), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _quiet_sine(duration_s: float, freq: float = 440.0, amplitude: float = 0.001) -> np.ndarray:
    """Very quiet sine wave."""
    return _sine(duration_s, freq, amplitude)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def proc():
    processor, _ = _make_processor()
    return processor


@pytest.fixture
def proc_no_vad():
    processor, _ = _make_processor(vad=False)
    return processor


# ---------------------------------------------------------------------------
# Empty / edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_array_returns_no_speech(self, proc):
        result = proc.process(np.array([], dtype=np.float32), SAMPLE_RATE)
        assert result.has_speech is False
        assert result.duration == 0.0
        assert len(result.audio) == 0

    def test_none_audio_returns_no_speech(self, proc):
        result = proc.process(None, SAMPLE_RATE)
        assert result.has_speech is False

    def test_very_short_audio_does_not_crash(self, proc):
        # 50ms of silence - shorter than a VAD window
        audio = _silence(0.05)
        result = proc.process(audio, SAMPLE_RATE)
        assert isinstance(result.has_speech, bool)

    def test_single_sample_does_not_crash(self, proc):
        audio = np.array([0.0], dtype=np.float32)
        result = proc.process(audio, SAMPLE_RATE)
        assert isinstance(result.has_speech, bool)


# ---------------------------------------------------------------------------
# VAD: silence detection
# ---------------------------------------------------------------------------

class TestSilenceDetection:
    def test_all_zeros_has_no_speech(self, proc):
        audio = _silence(1.0)
        result = proc.process(audio, SAMPLE_RATE)
        assert result.has_speech is False

    def test_speech_ratio_zero_for_silence(self, proc):
        audio = _silence(1.0)
        result = proc.process(audio, SAMPLE_RATE)
        assert result.speech_ratio == 0.0

    def test_peak_level_zero_for_silence(self, proc):
        audio = _silence(1.0)
        result = proc.process(audio, SAMPLE_RATE)
        assert result.peak_level == 0.0


# ---------------------------------------------------------------------------
# VAD: speech detection
# ---------------------------------------------------------------------------

class TestSpeechDetection:
    def test_sine_wave_has_speech(self, proc):
        audio = _sine(2.0, amplitude=0.3)
        result = proc.process(audio, SAMPLE_RATE)
        assert result.has_speech is True

    def test_speech_ratio_positive_for_sine(self, proc):
        audio = _sine(2.0, amplitude=0.3)
        result = proc.process(audio, SAMPLE_RATE)
        assert result.speech_ratio > 0.0

    def test_duration_positive_for_speech(self, proc):
        audio = _sine(2.0, amplitude=0.3)
        result = proc.process(audio, SAMPLE_RATE)
        assert result.duration > 0.0

    def test_vad_disabled_always_speech(self):
        # With VAD disabled, even non-silent audio is treated as speech.
        # Use an actual sine wave here because noise reduction on all-zero
        # audio is a degenerate edge case (zero signal_rms).
        processor, _ = _make_processor(vad=False, noise_reduction=False)
        audio = _sine(1.0, amplitude=0.1)
        result = processor.process(audio, SAMPLE_RATE)
        assert result.has_speech is True


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

class TestNormalization:
    def test_quiet_audio_gets_boosted(self):
        processor, _ = _make_processor(vad=False, noise_reduction=False, normalize=True)
        audio = _quiet_sine(1.0, amplitude=0.001)
        result = processor.process(audio, SAMPLE_RATE)
        # Output RMS should be higher than input RMS (boosted)
        input_rms = float(np.sqrt(np.mean(audio ** 2)))
        output_rms = float(np.sqrt(np.mean(result.audio ** 2))) if len(result.audio) > 0 else 0.0
        assert output_rms > input_rms

    def test_normalization_does_not_clip(self):
        processor, _ = _make_processor(vad=False, noise_reduction=False, normalize=True)
        audio = _sine(1.0, amplitude=0.3)
        result = processor.process(audio, SAMPLE_RATE)
        assert float(np.max(np.abs(result.audio))) <= 1.0

    def test_silent_audio_unchanged_by_normalize(self):
        processor, _ = _make_processor(vad=False, noise_reduction=False, normalize=True)
        audio = np.zeros(SAMPLE_RATE, dtype=np.float32)
        result = processor.process(audio, SAMPLE_RATE)
        # Essentially silent audio should not be artificially inflated
        assert float(np.max(np.abs(result.audio))) < 1e-3

    def test_normalization_disabled_preserves_level(self):
        processor, _ = _make_processor(vad=False, noise_reduction=False, normalize=False)
        audio = _quiet_sine(1.0, amplitude=0.001)
        result = processor.process(audio, SAMPLE_RATE)
        input_rms = float(np.sqrt(np.mean(audio ** 2)))
        output_rms = float(np.sqrt(np.mean(result.audio ** 2))) if len(result.audio) > 0 else 0.0
        # Without normalization, level should be approximately equal
        assert abs(output_rms - input_rms) < 0.01


# ---------------------------------------------------------------------------
# ProcessedAudio dataclass fields
# ---------------------------------------------------------------------------

class TestProcessedAudioFields:
    def test_all_fields_present(self, proc):
        audio = _sine(1.0)
        result = proc.process(audio, SAMPLE_RATE)
        assert hasattr(result, "audio")
        assert hasattr(result, "raw_audio")
        assert hasattr(result, "has_speech")
        assert hasattr(result, "speech_ratio")
        assert hasattr(result, "peak_level")
        assert hasattr(result, "duration")
        assert hasattr(result, "segments")

    def test_raw_audio_preserved(self, proc):
        audio = _sine(1.0)
        result = proc.process(audio, SAMPLE_RATE)
        # raw_audio should be the original, unprocessed recording
        assert len(result.raw_audio) > 0
        input_rms = float(np.sqrt(np.mean(audio ** 2)))
        raw_rms = float(np.sqrt(np.mean(result.raw_audio ** 2)))
        assert abs(raw_rms - input_rms) < 0.01

    def test_speech_ratio_between_0_and_1(self, proc):
        audio = _sine(2.0)
        result = proc.process(audio, SAMPLE_RATE)
        assert 0.0 <= result.speech_ratio <= 1.0

    def test_peak_level_between_0_and_1(self, proc):
        audio = _sine(1.0)
        result = proc.process(audio, SAMPLE_RATE)
        assert 0.0 <= result.peak_level <= 1.0


# ---------------------------------------------------------------------------
# segment_long_audio
# ---------------------------------------------------------------------------

class TestSegmentLongAudio:
    def test_short_audio_returns_single_chunk(self, proc):
        audio = _sine(5.0)
        chunks = proc.segment_long_audio(audio, SAMPLE_RATE)
        assert len(chunks) == 1

    def test_chunks_cover_all_samples(self, proc):
        # Build audio longer than the 5-minute threshold
        audio = np.zeros(300 * SAMPLE_RATE + 1, dtype=np.float32)  # just over 5 min
        chunks = proc.segment_long_audio(audio, SAMPLE_RATE)
        total = sum(len(c) for c in chunks)
        assert total == len(audio)

    def test_each_chunk_is_ndarray(self, proc):
        audio = np.zeros(300 * SAMPLE_RATE + 1, dtype=np.float32)
        chunks = proc.segment_long_audio(audio, SAMPLE_RATE)
        for chunk in chunks:
            assert isinstance(chunk, np.ndarray)

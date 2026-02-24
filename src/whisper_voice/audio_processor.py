# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Audio pre-processing pipeline for Local Whisper.

Applies VAD, silence trimming, noise reduction, and normalization
before audio is sent to WhisperKit for transcription.
"""

from dataclasses import dataclass, field

import numpy as np

from .utils import log


# VAD parameters
_SPEECH_THRESHOLD = 0.5        # probability above which a chunk is speech
_PRE_SPEECH_THRESHOLD = 0.2    # lower threshold to detect the onset of speech before confirmation
_MIN_SPEECH_CHUNKS = 8         # ~0.25s of consecutive speech to open a segment
_MIN_SILENCE_CHUNKS = 10       # ~0.3s of consecutive silence to close a segment
_SPEECH_PAD_SAMPLES = 4800     # 0.3s padding around speech segments at 16kHz (must be >= min_speech_duration)

# Noise reduction parameters
_STFT_N_FFT = 1024
_STFT_HOP = 512
_NOISE_GATE_MULTIPLIER = 2.0   # noise floor multiplier for gating (conservative: higher = less aggressive)
_NOISE_GATE_ATTENUATION = 0.3  # gain applied to gated bins (conservative: higher = less speech removed)
# Safety: skip noise reduction if estimated noise floor exceeds this fraction of signal RMS
# (indicates the noise floor estimate is unreliable and gating would destroy speech)
_NOISE_FLOOR_SAFETY_RATIO = 0.3

# Normalization parameters
_TARGET_RMS = 0.1              # -20 dBFS
_MAX_GAIN = 10.0               # 20 dB boost cap
_CLIP_THRESHOLD = 0.99

# Segmentation parameters
_MAX_SEGMENT_SAMPLES_FACTOR = 28   # 28s worth of audio (2s headroom for Whisper's 30s window)
_MIN_SEGMENT_SAMPLES_FACTOR = 3    # 3s minimum
_MAX_INTER_SEGMENT_GAP_FACTOR = 0.3  # 0.3s max silence between kept segments


@dataclass
class ProcessedAudio:
    audio: np.ndarray            # cleaned float32 array (ready for transcription)
    raw_audio: np.ndarray        # original unprocessed float32 array (for backup/retry)
    has_speech: bool             # VAD detected speech
    speech_ratio: float          # ratio of speech frames to total
    peak_level: float            # peak amplitude after normalization
    duration: float              # duration in seconds (after trimming)
    segments: list = field(default_factory=list)  # VAD speech segments (start_sample, end_sample)


class AudioProcessor:
    """
    Applies the full audio pre-processing pipeline:
    VAD -> silence trimming -> noise reduction -> normalization.
    """

    def __init__(self, config):
        self._config = config
        self._vad = None
        self._vad_initialized = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, audio: np.ndarray, sample_rate: int) -> ProcessedAudio:
        """Run the full processing pipeline on raw float32 audio."""
        if audio is None or len(audio) == 0:
            empty = np.array([], dtype=np.float32)
            return ProcessedAudio(
                audio=empty,
                raw_audio=empty,
                has_speech=False,
                speech_ratio=0.0,
                peak_level=0.0,
                duration=0.0,
                segments=[],
            )

        audio = audio.astype(np.float32)
        raw_audio = audio.copy()  # preserve original for backup
        input_duration = len(audio) / sample_rate
        log(f"Audio pipeline: input {input_duration:.2f}s", "INFO")
        segments = []

        # Step 1: VAD speech detection
        if self._config.audio.vad_enabled:
            segments = self._detect_speech(audio, sample_rate)
            has_speech = len(segments) > 0
        else:
            has_speech = True
            segments = [(0, len(audio))]

        # Compute speech ratio before trimming
        if len(audio) > 0 and segments:
            speech_samples = sum(end - start for start, end in segments)
            speech_ratio = speech_samples / len(audio)
        else:
            speech_ratio = 0.0 if not has_speech else 1.0

        if not has_speech:
            log("VAD: no speech detected", "INFO")
            return ProcessedAudio(
                audio=audio,
                raw_audio=raw_audio,
                has_speech=False,
                speech_ratio=0.0,
                peak_level=float(np.max(np.abs(audio))) if len(audio) > 0 else 0.0,
                duration=len(audio) / sample_rate,
                segments=[],
            )

        # Step 2: Silence trimming
        if self._config.audio.vad_enabled and segments:
            audio, segments = self._trim_silence(audio, segments, sample_rate)
            trimmed_duration = len(audio) / sample_rate
            log(f"Audio pipeline: after trim {trimmed_duration:.2f}s (removed {input_duration - trimmed_duration:.2f}s silence)", "INFO")
            if not segments:
                segments = [(0, len(audio))]

        # Step 3: Noise reduction
        if self._config.audio.noise_reduction:
            audio = self._reduce_noise(audio, segments, sample_rate)
        else:
            log("Audio pipeline: noise reduction skipped (disabled)", "INFO")

        # Step 4: Normalization
        if self._config.audio.normalize_audio:
            pre_rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) > 0 else 0.0
            audio = self._normalize(audio)
            post_rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) > 0 else 0.0
            if pre_rms > 1e-6:
                gain_db = 20 * np.log10(post_rms / pre_rms)
                log(f"Audio pipeline: normalization applied {gain_db:+.1f} dB", "INFO")
        else:
            log("Audio pipeline: normalization skipped (disabled)", "INFO")

        peak_level = float(np.max(np.abs(audio))) if len(audio) > 0 else 0.0
        duration = len(audio) / sample_rate

        return ProcessedAudio(
            audio=audio,
            raw_audio=raw_audio,
            has_speech=has_speech,
            speech_ratio=speech_ratio,
            peak_level=peak_level,
            duration=duration,
            segments=segments,
        )

    def segment_long_audio(self, audio: np.ndarray, sample_rate: int) -> list[np.ndarray]:
        """Split audio longer than 28s into segments at speech gaps."""
        max_samples = _MAX_SEGMENT_SAMPLES_FACTOR * sample_rate
        min_samples = _MIN_SEGMENT_SAMPLES_FACTOR * sample_rate

        if len(audio) <= max_samples:
            return [audio]

        segments = self._detect_speech(audio, sample_rate)
        if not segments:
            # No speech: chunk blindly
            return self._chunk_blindly(audio, max_samples, min_samples)

        return self._split_at_gaps(audio, segments, max_samples, min_samples)

    # ------------------------------------------------------------------
    # VAD
    # ------------------------------------------------------------------

    def _init_vad(self):
        """Lazy-initialize Silero VAD on first use."""
        if self._vad_initialized:
            return
        self._vad_initialized = True
        try:
            from silero_vad_lite import SileroVAD
            sample_rate = self._config.audio.sample_rate
            self._vad = SileroVAD(sample_rate)
            log("VAD model loaded", "INFO")
        except Exception as e:
            log(f"VAD init failed: {e}", "WARN")
            self._vad = None

    def _detect_speech(self, audio: np.ndarray, sample_rate: int) -> list[tuple[int, int]]:
        """Run VAD and return list of (start_sample, end_sample) speech segments."""
        self._init_vad()
        if self._vad is None:
            return [(0, len(audio))]

        if len(audio) == 0:
            return []

        total_samples = len(audio)
        chunk_size = self._vad.window_size_samples
        probs = []
        for i in range(0, total_samples, chunk_size):
            chunk = audio[i:i + chunk_size]
            if len(chunk) < chunk_size:
                # Pad short final chunk
                chunk = np.concatenate([chunk, np.zeros(chunk_size - len(chunk), dtype=np.float32)])
            else:
                chunk = chunk.astype(np.float32)
            try:
                prob = self._vad.process(memoryview(chunk.data))
                probs.append(float(prob))
            except Exception:
                probs.append(0.0)

        if not probs:
            return []

        # State machine: accumulate speech/silence runs to form segments
        segments = []
        in_speech = False
        segment_start = 0
        speech_run = 0
        silence_run = 0
        # Track the first chunk where probability crossed the lower pre-speech threshold.
        # This captures the true onset of an utterance before the confirmation window.
        first_above_low_threshold = None

        for idx, prob in enumerate(probs):
            is_speech_chunk = prob >= _SPEECH_THRESHOLD
            sample_pos = idx * chunk_size

            if not in_speech:
                if prob >= _PRE_SPEECH_THRESHOLD:
                    if first_above_low_threshold is None:
                        first_above_low_threshold = idx
                else:
                    # Probability dropped below even the low threshold: reset onset tracking
                    if not is_speech_chunk:
                        first_above_low_threshold = None

                if is_speech_chunk:
                    speech_run += 1
                    silence_run = 0
                    if speech_run >= _MIN_SPEECH_CHUNKS:
                        # Open segment: use the earliest chunk that crossed the pre-speech
                        # threshold as the true speech onset, then subtract padding.
                        in_speech = True
                        onset_idx = first_above_low_threshold if first_above_low_threshold is not None else (idx - speech_run + 1)
                        onset_sample = onset_idx * chunk_size
                        segment_start = max(0, onset_sample - _SPEECH_PAD_SAMPLES)
                        speech_run = 0
                        first_above_low_threshold = None
                else:
                    speech_run = 0
            else:
                if not is_speech_chunk:
                    silence_run += 1
                    speech_run = 0
                    if silence_run >= _MIN_SILENCE_CHUNKS:
                        # Close segment
                        in_speech = False
                        segment_end = min(total_samples, sample_pos + _SPEECH_PAD_SAMPLES)
                        segments.append((segment_start, segment_end))
                        silence_run = 0
                        first_above_low_threshold = None
                else:
                    silence_run = 0
                    speech_run += 1

        # Close any open segment at end of audio
        if in_speech:
            segments.append((segment_start, total_samples))

        log(f"VAD: {len(segments)} speech segment(s) detected", "INFO")
        return segments

    def _trim_silence(self, audio: np.ndarray, segments: list, sample_rate: int) -> tuple[np.ndarray, list]:
        """Trim non-speech from beginning and end; compress inter-segment gaps.

        Returns the trimmed audio and the segment positions adjusted to be
        relative to the trimmed audio (so downstream steps use correct positions).
        """
        if not segments:
            return audio, segments

        max_gap = int(_MAX_INTER_SEGMENT_GAP_FACTOR * sample_rate)

        # Build output by concatenating segments with capped gaps between them.
        # Track where each piece of source audio maps to in the output so we can
        # remap segment positions accurately.
        parts = []
        write_pos = 0           # current write position in the output array
        adjusted_segments = []

        for i, (start, end) in enumerate(segments):
            if i > 0:
                prev_end = segments[i - 1][1]
                gap = start - prev_end
                if gap > max_gap:
                    # Insert a compressed gap
                    gap_audio = audio[prev_end:prev_end + max_gap]
                    parts.append(gap_audio)
                    write_pos += len(gap_audio)
                else:
                    # Keep the gap as-is
                    gap_audio = audio[prev_end:start]
                    parts.append(gap_audio)
                    write_pos += len(gap_audio)

            seg_len = end - start
            seg_start_out = write_pos
            seg_end_out = write_pos + seg_len
            adjusted_segments.append((seg_start_out, seg_end_out))
            parts.append(audio[start:end])
            write_pos += seg_len

        if not parts:
            return audio, segments

        trimmed = np.concatenate(parts).astype(np.float32)
        return trimmed, adjusted_segments

    # ------------------------------------------------------------------
    # Noise reduction
    # ------------------------------------------------------------------

    def _reduce_noise(self, audio: np.ndarray, segments: list, sample_rate: int) -> np.ndarray:
        """Spectral gating noise reduction using pure numpy STFT."""
        min_frame_samples = _STFT_N_FFT
        if len(audio) < min_frame_samples:
            log("Audio pipeline: noise reduction skipped (audio too short)", "INFO")
            return audio

        # Build a Hann window
        window = np.hanning(_STFT_N_FFT).astype(np.float32)

        # STFT
        stft = self._stft(audio, window)
        magnitude = np.abs(stft)
        phase = np.angle(stft)

        # Estimate noise floor
        noise_floor = self._estimate_noise_floor(magnitude, audio, segments, sample_rate)

        # Safety check: if estimated noise floor is suspiciously high relative to signal,
        # the noise floor estimate is unreliable (likely captured speech in "silence" frames).
        # Skip noise reduction rather than destroy speech.
        signal_rms = float(np.sqrt(np.mean(audio ** 2)))
        noise_floor_rms = float(np.mean(noise_floor))
        if signal_rms > 1e-6 and noise_floor_rms / signal_rms > _NOISE_FLOOR_SAFETY_RATIO:
            log(f"Audio pipeline: noise reduction skipped (noise floor too high: {noise_floor_rms / signal_rms:.2f} of signal)", "WARN")
            return audio

        # Spectral gating
        gate_threshold = noise_floor * _NOISE_GATE_MULTIPLIER
        mask = np.where(magnitude >= gate_threshold, 1.0, _NOISE_GATE_ATTENUATION)
        magnitude_filtered = magnitude * mask

        # Inverse STFT
        stft_filtered = magnitude_filtered * np.exp(1j * phase)
        audio_out = self._istft(stft_filtered, window, len(audio))

        log(f"Audio pipeline: noise reduction applied (floor ratio: {noise_floor_rms / signal_rms:.3f})", "INFO")
        return audio_out.astype(np.float32)

    def _stft(self, audio: np.ndarray, window: np.ndarray) -> np.ndarray:
        """Compute Short-Time Fourier Transform."""
        n_fft = _STFT_N_FFT
        hop = _STFT_HOP
        n_frames = 1 + (len(audio) - n_fft) // hop

        if n_frames <= 0:
            return np.zeros((n_fft // 2 + 1, 1), dtype=complex)

        stft = np.zeros((n_fft // 2 + 1, n_frames), dtype=complex)
        for t in range(n_frames):
            start = t * hop
            frame = audio[start:start + n_fft] * window
            spectrum = np.fft.rfft(frame, n=n_fft)
            stft[:, t] = spectrum

        return stft

    def _istft(self, stft: np.ndarray, window: np.ndarray, original_length: int) -> np.ndarray:
        """Compute Inverse Short-Time Fourier Transform with overlap-add."""
        n_fft = _STFT_N_FFT
        hop = _STFT_HOP
        n_frames = stft.shape[1]

        output_length = (n_frames - 1) * hop + n_fft
        audio_out = np.zeros(output_length, dtype=np.float32)
        window_sum = np.zeros(output_length, dtype=np.float32)

        for t in range(n_frames):
            start = t * hop
            frame = np.fft.irfft(stft[:, t], n=n_fft).real.astype(np.float32)
            audio_out[start:start + n_fft] += frame * window
            window_sum[start:start + n_fft] += window ** 2

        # Normalize by window overlap
        nonzero = window_sum > 1e-8
        audio_out[nonzero] /= window_sum[nonzero]

        # Trim or pad to original length
        if len(audio_out) > original_length:
            audio_out = audio_out[:original_length]
        elif len(audio_out) < original_length:
            audio_out = np.concatenate([audio_out, np.zeros(original_length - len(audio_out), dtype=np.float32)])

        return audio_out

    def _estimate_noise_floor(
        self,
        magnitude: np.ndarray,
        audio: np.ndarray,
        segments: list,
        sample_rate: int,
    ) -> np.ndarray:
        """Estimate per-frequency noise floor from non-speech regions or first 0.1s."""
        hop = _STFT_HOP
        n_frames = magnitude.shape[1]

        # Map segments to frame indices
        speech_frames: set[int] = set()
        for start, end in segments:
            f_start = start // hop
            f_end = end // hop
            for f in range(f_start, min(f_end + 1, n_frames)):
                speech_frames.add(f)

        non_speech_frames = [f for f in range(n_frames) if f not in speech_frames]

        if non_speech_frames:
            noise_mag = magnitude[:, non_speech_frames]
            return np.median(noise_mag, axis=1, keepdims=True)

        # All audio is speech: use conservative default from first 0.1s
        first_frames = max(1, int(0.1 * sample_rate / hop))
        first_frames = min(first_frames, n_frames)
        noise_mag = magnitude[:, :first_frames]
        return np.median(noise_mag, axis=1, keepdims=True) * 0.5  # conservative

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _normalize(self, audio: np.ndarray) -> np.ndarray:
        """Scale audio to target RMS with gain cap and clip prevention."""
        if len(audio) == 0:
            return audio

        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < 1e-6:
            return audio  # essentially silent

        gain = _TARGET_RMS / rms
        gain = min(gain, _MAX_GAIN)
        audio = audio * gain

        # Prevent clipping
        peak = float(np.max(np.abs(audio)))
        if peak > _CLIP_THRESHOLD:
            audio = audio * (_CLIP_THRESHOLD / peak)

        return audio.astype(np.float32)

    # ------------------------------------------------------------------
    # Long audio segmentation helpers
    # ------------------------------------------------------------------

    def _split_at_gaps(
        self,
        audio: np.ndarray,
        segments: list,
        max_samples: int,
        min_samples: int,
    ) -> list[np.ndarray]:
        """Split audio at largest inter-segment gaps to stay under max_samples."""
        # Build list of gap sizes between consecutive segments
        gaps = []
        for i in range(1, len(segments)):
            gap_start = segments[i - 1][1]
            gap_end = segments[i][0]
            gaps.append((gap_end - gap_start, gap_start, gap_end, i))

        # Sort gaps descending by size (split at biggest gaps first)
        gaps.sort(key=lambda x: -x[0])

        # Determine split points
        split_points = []
        for gap_size, gap_start, gap_end, seg_idx in gaps:
            # Split in the middle of the gap
            split_points.append((gap_start + gap_end) // 2)
            # Check if the resulting chunks would be small enough
            if self._would_fit(split_points, len(audio), max_samples):
                break

        if not split_points:
            return self._chunk_blindly(audio, max_samples, min_samples)

        split_points = sorted(split_points)
        chunks = []
        prev = 0
        for sp in split_points:
            chunk = audio[prev:sp]
            if len(chunk) > 0:
                chunks.append(chunk)
            prev = sp
        if prev < len(audio):
            chunks.append(audio[prev:])

        # Merge tiny tails into previous
        chunks = self._merge_tiny_tails(chunks, min_samples)

        return [c.astype(np.float32) for c in chunks if len(c) > 0]

    def _would_fit(self, split_points: list, total_length: int, max_samples: int) -> bool:
        """Check if splitting at given points keeps all chunks under max_samples."""
        sorted_pts = sorted(split_points)
        prev = 0
        for sp in sorted_pts:
            if sp - prev > max_samples:
                return False
            prev = sp
        return total_length - prev <= max_samples

    def _chunk_blindly(self, audio: np.ndarray, max_samples: int, min_samples: int) -> list[np.ndarray]:
        """Split audio into fixed-size chunks when no speech segments available."""
        chunks = []
        for start in range(0, len(audio), max_samples):
            chunks.append(audio[start:start + max_samples])
        return self._merge_tiny_tails(chunks, min_samples)

    def _merge_tiny_tails(self, chunks: list, min_samples: int) -> list:
        """Merge trailing chunks smaller than min_samples into the previous one."""
        if not chunks:
            return chunks
        merged = list(chunks)
        while len(merged) > 1 and len(merged[-1]) < min_samples:
            tail = merged.pop()
            merged[-1] = np.concatenate([merged[-1], tail])
        return merged

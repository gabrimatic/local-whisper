# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Audio pre-processing pipeline for Local Whisper.

Applies VAD, silence trimming, noise reduction, and normalization
before audio is sent to the transcription engine.
"""

from dataclasses import dataclass, field

import numpy as np
from numpy.lib.stride_tricks import as_strided

from .utils import log


_SPEECH_PAD_SAMPLES = 4800     # 0.3s padding around speech segments at 16kHz

# Noise reduction parameters
_STFT_N_FFT = 1024
_STFT_HOP = 512
_NOISE_GATE_MULTIPLIER = 2.0   # noise floor multiplier for gating (conservative: higher = less aggressive)
_NOISE_GATE_ATTENUATION = 0.3  # gain applied to gated bins (conservative: higher = less speech removed)
# Safety: skip noise reduction if estimated noise floor exceeds this fraction of signal RMS
# (indicates the noise floor estimate is unreliable and gating would destroy speech)
_NOISE_FLOOR_SAFETY_RATIO = 0.3

# Normalization parameters
_TARGET_RMS = 0.05             # -26 dBFS (conservative target to avoid over-amplifying)
_MAX_GAIN = 3.0                # ~10 dB boost cap (prevents extreme amplification of quiet-but-clean audio)
_CLIP_THRESHOLD = 0.99

# Segmentation parameters
_MAX_SEGMENT_SAMPLES_FACTOR = 300  # 300s (5 min) safety net - WhisperKit handles its own chunking
_MIN_SEGMENT_SAMPLES_FACTOR = 3    # 3s minimum

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
        """Split audio longer than 5 minutes into segments at speech gaps."""
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
    # VAD (energy-based)
    # ------------------------------------------------------------------

    def _detect_speech(self, audio: np.ndarray, sample_rate: int) -> list[tuple[int, int]]:
        """Detect speech segments using RMS energy thresholding."""
        if len(audio) == 0:
            return []

        # Calculate RMS energy in sliding windows (vectorized for long recordings)
        window_size = int(0.03 * sample_rate)  # 30ms windows
        hop_size = window_size  # non-overlapping

        n_windows = (len(audio) - window_size) // hop_size
        if n_windows <= 0:
            return [(0, len(audio))]

        # Reshape into windows for vectorized RMS computation
        # Trim audio to exact multiple of window_size for reshape
        trimmed_len = n_windows * hop_size + window_size
        trimmed = audio[:min(trimmed_len, len(audio))]

        # Use stride tricks for zero-copy windowed view
        item_size = trimmed.strides[0]
        windows = as_strided(
            trimmed,
            shape=(n_windows, window_size),
            strides=(hop_size * item_size, item_size),
        )
        energies = np.sqrt(np.mean(windows ** 2, axis=1))

        # Adaptive threshold: use the quietest 10% as noise floor
        noise_floor = np.percentile(energies, 10)
        median_energy = np.percentile(energies, 50)

        # If the energy is fairly uniform (low dynamic range), the recording is
        # likely all speech with no real silence. Treat the whole thing as speech
        # if the median energy is well above the absolute silence floor.
        if noise_floor > 0 and median_energy / noise_floor < 2.0 and median_energy > 0.01:
            log(f"VAD: uniform energy detected (floor={noise_floor:.4f}, median={median_energy:.4f}), treating as all speech", "INFO")
            return [(0, len(audio))]

        speech_threshold = max(noise_floor * 3.0, 0.003)  # at least 0.003 RMS

        # Find frames above threshold
        is_speech = energies > speech_threshold

        # Smooth: apply majority filter to remove brief spikes/dips
        # Uses a sliding sum (vectorized) instead of per-element median for speed on long audio.
        kernel_size = 5  # ~150ms at 30ms windows
        half_k = kernel_size // 2
        padded = np.pad(is_speech.astype(np.float32), half_k, mode='edge')
        cumsum = np.cumsum(padded)
        # sliding sum of kernel_size elements
        sliding_sum = cumsum[kernel_size:] - cumsum[:-kernel_size]
        is_speech = sliding_sum > (kernel_size / 2.0)

        # Find contiguous speech regions
        segments = []
        in_speech = False
        seg_start = 0

        for i, speech in enumerate(is_speech):
            if speech and not in_speech:
                seg_start = i
                in_speech = True
            elif not speech and in_speech:
                segments.append((seg_start * hop_size, i * hop_size))
                in_speech = False

        if in_speech:
            segments.append((seg_start * hop_size, len(audio)))

        log(f"VAD: {len(segments)} speech segment(s) detected (energy-based, threshold={speech_threshold:.4f})", "INFO")
        return segments

    def _trim_silence(self, audio: np.ndarray, segments: list, sample_rate: int) -> tuple[np.ndarray, list]:
        """Trim silence from the beginning and end of audio only.

        Natural pauses between sentences are preserved intact so Whisper
        has full prosodic context for accurate transcription.
        """
        if not segments:
            return audio, segments

        # Find the earliest speech start and latest speech end across all segments
        first_speech_start = segments[0][0]
        last_speech_end = segments[-1][1]

        trim_start = max(0, first_speech_start - _SPEECH_PAD_SAMPLES)
        trim_end = min(len(audio), last_speech_end + _SPEECH_PAD_SAMPLES)

        trimmed = audio[trim_start:trim_end]

        # Adjust segment positions relative to the trimmed audio
        adjusted = [(s - trim_start, e - trim_start) for s, e in segments]
        adjusted = [(max(0, s), min(len(trimmed), e)) for s, e in adjusted]

        return trimmed, adjusted

    # ------------------------------------------------------------------
    # Noise reduction
    # ------------------------------------------------------------------

    def _reduce_noise(self, audio: np.ndarray, segments: list, sample_rate: int) -> np.ndarray:
        """Spectral gating noise reduction using pure numpy STFT.

        For recordings longer than 3 minutes, processes in overlapping chunks to
        keep memory usage bounded and avoid slow Python-loop STFT on huge arrays.
        """
        min_frame_samples = _STFT_N_FFT
        if len(audio) < min_frame_samples:
            log("Audio pipeline: noise reduction skipped (audio too short)", "INFO")
            return audio

        # For long recordings (>3 min), process in chunks to cap memory and CPU time.
        # Each chunk is processed independently with a crossfade at boundaries.
        _CHUNK_THRESHOLD = 3 * 60 * sample_rate  # 3 minutes in samples
        if len(audio) > _CHUNK_THRESHOLD:
            return self._reduce_noise_chunked(audio, segments, sample_rate)

        return self._reduce_noise_single(audio, segments, sample_rate)

    def _reduce_noise_single(self, audio: np.ndarray, segments: list, sample_rate: int) -> np.ndarray:
        """Noise reduction on a single contiguous audio buffer."""
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

    def _reduce_noise_chunked(self, audio: np.ndarray, segments: list, sample_rate: int) -> np.ndarray:
        """Chunked noise reduction for long recordings (>3 min).

        Splits audio into ~60s chunks with 0.5s overlap, processes each independently,
        and crossfades at boundaries for seamless output.
        """
        chunk_duration = 60  # seconds per chunk
        overlap_duration = 0.5  # seconds of overlap for crossfade
        chunk_samples = chunk_duration * sample_rate
        overlap_samples = int(overlap_duration * sample_rate)

        total_duration = len(audio) / sample_rate
        log(f"Audio pipeline: chunked noise reduction ({total_duration:.1f}s, ~{int(total_duration / chunk_duration) + 1} chunks)", "INFO")

        output = np.zeros_like(audio)
        pos = 0
        chunk_idx = 0

        while pos < len(audio):
            # Define chunk boundaries with overlap
            chunk_end = min(pos + chunk_samples + overlap_samples, len(audio))
            chunk = audio[pos:chunk_end]

            # Find segments that overlap with this chunk
            chunk_segments = []
            for seg_start, seg_end in segments:
                # Translate to chunk-local coordinates
                local_start = max(0, seg_start - pos)
                local_end = min(len(chunk), seg_end - pos)
                if local_start < local_end:
                    chunk_segments.append((local_start, local_end))

            if not chunk_segments:
                chunk_segments = [(0, len(chunk))]

            # Process this chunk
            processed_chunk = self._reduce_noise_single(chunk, chunk_segments, sample_rate)

            # Apply crossfade at the boundary with previous chunk
            if pos > 0 and overlap_samples > 0:
                fade_len = min(overlap_samples, len(processed_chunk), len(audio) - pos)
                if fade_len > 0:
                    fade_in = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
                    fade_out = 1.0 - fade_in
                    output[pos:pos + fade_len] = (
                        output[pos:pos + fade_len] * fade_out
                        + processed_chunk[:fade_len] * fade_in
                    )
                    # Copy the rest of the chunk after the crossfade region
                    if fade_len < len(processed_chunk):
                        write_end = min(pos + len(processed_chunk), len(audio))
                        output[pos + fade_len:write_end] = processed_chunk[fade_len:write_end - pos]
                else:
                    write_end = min(pos + len(processed_chunk), len(audio))
                    output[pos:write_end] = processed_chunk[:write_end - pos]
            else:
                write_end = min(pos + len(processed_chunk), len(audio))
                output[pos:write_end] = processed_chunk[:write_end - pos]

            chunk_idx += 1
            pos += chunk_samples  # advance by chunk_samples (not including overlap)

        log(f"Audio pipeline: chunked noise reduction complete ({chunk_idx} chunks)", "INFO")
        return output.astype(np.float32)

    def _stft(self, audio: np.ndarray, window: np.ndarray) -> np.ndarray:
        """Compute Short-Time Fourier Transform (vectorized)."""
        n_fft = _STFT_N_FFT
        hop = _STFT_HOP
        n_frames = 1 + (len(audio) - n_fft) // hop

        if n_frames <= 0:
            return np.zeros((n_fft // 2 + 1, 1), dtype=complex)

        # Build windowed frames using stride tricks (zero-copy view)
        item_size = audio.strides[0]
        frames = as_strided(
            audio,
            shape=(n_frames, n_fft),
            strides=(hop * item_size, item_size),
        )
        # Apply window and compute FFT in one vectorized call
        windowed = frames * window[np.newaxis, :]
        stft = np.fft.rfft(windowed, n=n_fft, axis=1).T  # shape: (n_fft//2+1, n_frames)

        return stft

    def _istft(self, stft: np.ndarray, window: np.ndarray, original_length: int) -> np.ndarray:
        """Compute Inverse Short-Time Fourier Transform with overlap-add."""
        n_fft = _STFT_N_FFT
        hop = _STFT_HOP
        n_frames = stft.shape[1]

        output_length = (n_frames - 1) * hop + n_fft
        audio_out = np.zeros(output_length, dtype=np.float32)
        window_sum = np.zeros(output_length, dtype=np.float32)

        # Batch IRFFT (vectorized)
        frames = np.fft.irfft(stft.T, n=n_fft, axis=1).real.astype(np.float32)  # (n_frames, n_fft)
        window_sq = window ** 2

        # Overlap-add (must be sequential due to overlapping writes)
        for t in range(n_frames):
            start = t * hop
            audio_out[start:start + n_fft] += frames[t] * window
            window_sum[start:start + n_fft] += window_sq

        # Normalize by window overlap
        nonzero = window_sum > 1e-8
        audio_out[nonzero] /= window_sum[nonzero]

        # Trim or pad to original length
        if len(audio_out) > original_length:
            audio_out = audio_out[:original_length]
        elif len(audio_out) < original_length:
            audio_out = np.concatenate([audio_out, np.zeros(original_length - len(audio_out), dtype=np.float32)])

        # Clip to prevent edge amplification from Hann window zero endpoints
        audio_out = np.clip(audio_out, -1.0, 1.0)

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

        # All audio is speech: use the quietest 5% of frames as noise estimate
        # (more robust than first 0.1s which may contain speech, especially with pre-buffer)
        frame_energies = np.mean(np.abs(magnitude), axis=0)  # vectorized
        quiet_threshold = np.percentile(frame_energies, 5)
        quiet_mask = frame_energies <= quiet_threshold
        if np.any(quiet_mask):
            noise_mag = magnitude[:, quiet_mask]
        else:
            # Absolute fallback: use the single quietest frame
            noise_mag = magnitude[:, [np.argmin(frame_energies)]]
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

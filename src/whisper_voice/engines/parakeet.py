# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Parakeet-TDT transcription engine for Local Whisper.

Uses parakeet-mlx to run NVIDIA's Parakeet-TDT model locally via MLX. The default
mlx-community/parakeet-tdt-0.6b-v3 checkpoint tops the HuggingFace Open ASR
Leaderboard and supports English plus 24 European languages. Long audio is
handled natively via chunking with overlap; no server required.
"""

import concurrent.futures
import gc
import time
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from ..config import get_config
from ..utils import log
from .base import TranscriptionEngine

_DEFAULT_MODEL = "mlx-community/parakeet-tdt-0.6b-v3"


def _quick_duration(path: str) -> Optional[float]:
    """Return wav duration in seconds using the stdlib ``wave`` module.
    ``None`` if the file isn't a readable PCM wav."""
    try:
        import wave
        with wave.open(path, "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            if rate <= 0:
                return None
            return frames / float(rate)
    except Exception:
        return None


class ParakeetEngine(TranscriptionEngine):
    """Transcription engine backed by Parakeet-TDT via parakeet-mlx."""

    _LEAK_LOG_THRESHOLD = 2

    def __init__(self):
        self._model = None
        self._timeout = 0
        self._leaked_workers = 0

    @property
    def name(self) -> str:
        return "Parakeet-TDT v3"

    @property
    def supports_long_audio(self) -> bool:
        return True

    def start(self) -> bool:
        config = get_config()
        cfg = getattr(config, "parakeet", None)
        model_name = getattr(cfg, "model", _DEFAULT_MODEL) if cfg else _DEFAULT_MODEL
        self._timeout = getattr(cfg, "timeout", 0) if cfg else 0
        local_attention = bool(getattr(cfg, "local_attention", False)) if cfg else False
        local_ctx = int(getattr(cfg, "local_attention_context_size", 256)) if cfg else 256

        log(f"Loading Parakeet model ({model_name})...", "INFO")
        load_start = time.monotonic()
        try:
            from parakeet_mlx import from_pretrained
            self._model = from_pretrained(model_name)
        except ImportError:
            log("parakeet-mlx is not installed. Run: pip install parakeet-mlx", "ERR")
            return False
        except Exception as e:
            log(f"Parakeet failed to load: {e}", "ERR")
            return False
        log(f"Parakeet model loaded in {time.monotonic() - load_start:.1f}s", "INFO")

        if local_attention:
            try:
                self._model.encoder.set_attention_model(
                    "rel_pos_local_attn",
                    (local_ctx, local_ctx),
                )
                log(f"Parakeet local attention enabled (ctx={local_ctx})", "INFO")
            except Exception as e:
                log(f"Parakeet local attention setup failed: {e}", "WARN")

        log("Warming up Parakeet...", "INFO")
        warm_start = time.monotonic()
        try:
            self._warm_up()
            log(f"Parakeet warm-up complete in {time.monotonic() - warm_start:.1f}s", "OK")
        except Exception as e:
            log(
                f"Parakeet warm-up failed (first inference will be slower): {e}",
                "WARN",
            )

        log("Parakeet ready", "OK")
        return True

    def _warm_up(self) -> None:
        """Prime the MLX graph with a 0.5s silent wav so first real inference is fast."""
        import tempfile
        import wave
        sr = int(getattr(self._model.preprocessor_config, "sample_rate", 16000))
        silence = np.zeros(int(sr * 0.5), dtype=np.int16)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes(silence.tobytes())
            self._model.transcribe(path)
        finally:
            try:
                import os
                os.unlink(path)
            except OSError:
                pass

    def running(self) -> bool:
        return self._model is not None

    def transcribe(self, path: Path) -> Tuple[Optional[str], Optional[str]]:
        if self._model is None:
            return None, "Model not loaded"

        start = time.monotonic()
        duration_seconds: Optional[float] = None
        try:
            config = get_config()
            cfg = getattr(config, "parakeet", None)
            timeout = getattr(cfg, "timeout", self._timeout) if cfg else self._timeout

            kwargs: dict = {
                "chunk_duration": getattr(cfg, "chunk_duration", 120.0) if cfg else 120.0,
                "overlap_duration": getattr(cfg, "overlap_duration", 15.0) if cfg else 15.0,
            }

            decoding_cfg = self._build_decoding_config(cfg)
            if decoding_cfg is not None:
                kwargs["decoding_config"] = decoding_cfg

            text, err = self._invoke(str(path), kwargs, timeout)
            if err:
                return None, err
            if text:
                self._leaked_workers = 0
                duration_seconds = _quick_duration(str(path))
                self._log_timing(start, duration_seconds)
                return text, None

            return None, "Empty transcription"
        except Exception as e:
            return None, str(e)
        finally:
            self._clear_runtime_cache()

    def _build_decoding_config(self, cfg):
        """Assemble a DecodingConfig from user settings, or None for defaults."""
        if cfg is None:
            return None
        decoding = getattr(cfg, "decoding", "greedy")
        if decoding != "beam":
            return None
        try:
            from parakeet_mlx import DecodingConfig
        except ImportError:
            return None
        kwargs = {
            "beam_size": int(getattr(cfg, "beam_size", 5)),
            "length_penalty": float(getattr(cfg, "length_penalty", 0.013)),
            "patience": float(getattr(cfg, "patience", 3.5)),
            "duration_reward": float(getattr(cfg, "duration_reward", 0.67)),
        }
        try:
            return DecodingConfig(**kwargs)
        except TypeError:
            # Older parakeet-mlx signatures nest beam parameters under a Beam struct.
            try:
                from parakeet_mlx import Beam
                return DecodingConfig(decoding=Beam(**kwargs))
            except Exception:
                return None

    @staticmethod
    def _log_timing(start: float, duration: Optional[float]) -> None:
        elapsed = time.monotonic() - start
        if duration and duration > 0:
            rtf = elapsed / duration
            log(
                f"Parakeet: {elapsed:.2f}s for {duration:.1f}s audio (RTF={rtf:.2f})",
                "INFO",
            )
        else:
            log(f"Parakeet: {elapsed:.2f}s", "INFO")

    def _invoke(self, path: str, kwargs: dict, timeout: int):
        """Run transcribe with an optional hard timeout. Returns (text, error)."""
        timeout_val = timeout if timeout and timeout > 0 else None
        if timeout_val is None:
            result = self._model.transcribe(path, **kwargs)
        else:
            # Not `with`: __exit__ blocks on the runaway worker and defeats the timeout.
            executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="parakeet-transcribe"
            )
            future = executor.submit(self._model.transcribe, path, **kwargs)
            try:
                result = future.result(timeout=timeout_val)
                executor.shutdown(wait=True)
            except concurrent.futures.TimeoutError:
                executor.shutdown(wait=False, cancel_futures=True)
                self._leaked_workers += 1
                if self._leaked_workers >= self._LEAK_LOG_THRESHOLD:
                    log(
                        f"Parakeet: {self._leaked_workers} abandoned workers; "
                        "reload pending",
                        "WARN",
                    )
                return "", f"Transcription timed out after {timeout_val}s"
        text = result.text.strip() if result and hasattr(result, "text") and result.text else ""
        return text, None

    def unload(self) -> None:
        """Release model from RAM without destroying the engine."""
        if self._model is not None:
            self._model = None
            self._clear_runtime_cache()
            log("Parakeet model unloaded (idle)", "INFO")
        self._leaked_workers = 0

    def close(self) -> None:
        self._model = None
        self._clear_runtime_cache()
        log("Parakeet model unloaded", "INFO")
        self._leaked_workers = 0

    def _clear_runtime_cache(self) -> None:
        gc.collect()
        try:
            import mlx.core as mx

            mx.clear_cache()
        except Exception:
            pass

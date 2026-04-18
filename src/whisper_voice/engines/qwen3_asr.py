# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Qwen3-ASR transcription engine for Local Whisper.

Uses qwen3-asr-mlx to run Qwen3-ASR locally via MLX, supporting up to 20 minutes
of audio natively without chunking. English-only.
"""

import concurrent.futures
import gc
import time
from pathlib import Path
from typing import Optional, Tuple

from ..config import get_config
from ..utils import log
from .base import TranscriptionEngine

_DEFAULT_MODEL = "mlx-community/Qwen3-ASR-1.7B-bf16"
_LANGUAGE = "English"


def _quick_duration(path: str) -> Optional[float]:
    """Return wav duration in seconds using the stdlib ``wave`` module.
    ``None`` if the file isn't a readable PCM wav (the model will raise
    a more descriptive error on the real call)."""
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


class Qwen3ASREngine(TranscriptionEngine):
    """Transcription engine backed by Qwen3-ASR via qwen3-asr-mlx."""

    _LEAK_LOG_THRESHOLD = 2

    def __init__(self):
        self._model = None
        self._timeout = 0
        self._leaked_workers = 0

    @property
    def name(self) -> str:
        return "Qwen3-ASR"

    @property
    def supports_long_audio(self) -> bool:
        return True

    def start(self) -> bool:
        config = get_config()
        qwen_cfg = getattr(config, "qwen3_asr", None)
        model_name = getattr(qwen_cfg, "model", _DEFAULT_MODEL) if qwen_cfg else _DEFAULT_MODEL
        self._timeout = getattr(qwen_cfg, "timeout", 0) if qwen_cfg else 0

        log(f"Loading Qwen3-ASR model ({model_name})...", "INFO")
        load_start = time.monotonic()
        try:
            from qwen3_asr_mlx import Qwen3ASR
            self._model = Qwen3ASR.from_pretrained(model_name)
        except ImportError:
            log("qwen3-asr-mlx is not installed. Run: pip install qwen3-asr-mlx", "ERR")
            return False
        except Exception as e:
            log(f"Qwen3-ASR failed to load: {e}", "ERR")
            return False
        log(f"Qwen3-ASR model loaded in {time.monotonic() - load_start:.1f}s", "INFO")

        log("Warming up Qwen3-ASR...", "INFO")
        warm_start = time.monotonic()
        try:
            self._model.warm_up()
            log(f"Qwen3-ASR warm-up complete in {time.monotonic() - warm_start:.1f}s", "OK")
        except Exception as e:
            log(
                f"Qwen3-ASR warm-up failed (first inference will be slower): {e}",
                "WARN",
            )

        log("Qwen3-ASR ready", "OK")
        return True

    def running(self) -> bool:
        return self._model is not None

    def transcribe(self, path: Path) -> Tuple[Optional[str], Optional[str]]:
        if self._model is None:
            return None, "Model not loaded"

        start = time.monotonic()
        duration_seconds: Optional[float] = None
        try:
            config = get_config()
            qwen3_cfg = getattr(config, "qwen3_asr", None)
            timeout = getattr(qwen3_cfg, "timeout", self._timeout) if qwen3_cfg else self._timeout

            kwargs: dict = {
                "language": _LANGUAGE,
                "temperature": getattr(qwen3_cfg, "temperature", 0.0) if qwen3_cfg else 0.0,
                "top_p": getattr(qwen3_cfg, "top_p", 1.0) if qwen3_cfg else 1.0,
                "top_k": getattr(qwen3_cfg, "top_k", 0) if qwen3_cfg else 0,
                "repetition_penalty": getattr(qwen3_cfg, "repetition_penalty", 1.2) if qwen3_cfg else 1.2,
                "repetition_context_size": getattr(qwen3_cfg, "repetition_context_size", 100) if qwen3_cfg else 100,
                "chunk_duration": getattr(qwen3_cfg, "chunk_duration", 1200.0) if qwen3_cfg else 1200.0,
            }
            max_tokens = getattr(qwen3_cfg, "max_tokens", 0) if qwen3_cfg else 0
            if max_tokens and max_tokens > 0:
                kwargs["max_tokens"] = int(max_tokens)

            text, err = self._invoke(str(path), kwargs, timeout)
            if err:
                return None, err
            if text:
                self._leaked_workers = 0
                duration_seconds = _quick_duration(str(path))
                self._log_timing(start, duration_seconds, retried=False)
                return text, None

            # Retry empty result with sampling, but only on short clips.
            duration_seconds = _quick_duration(str(path))
            _RETRY_MAX_SECONDS = 60.0
            if duration_seconds is not None and duration_seconds > _RETRY_MAX_SECONDS:
                log(
                    f"Qwen3-ASR: empty result on long clip ({duration_seconds:.0f}s), "
                    "skipping retry",
                    "WARN",
                )
                return None, "Empty transcription"

            retry_kwargs = dict(kwargs)
            if retry_kwargs.get("temperature", 0.0) == 0.0:
                retry_kwargs["temperature"] = 0.2
                retry_kwargs["top_p"] = 0.95
                log("Qwen3-ASR: empty result, retrying with sampling", "WARN")
                # Halve the budget so timeout=60 can't become 120s worst case.
                retry_timeout = (timeout // 2) if timeout and timeout > 0 else 0
                text, err = self._invoke(str(path), retry_kwargs, retry_timeout)
                if err:
                    return None, err
                if text:
                    self._leaked_workers = 0
                    self._log_timing(start, duration_seconds, retried=True)
                    return text, None
            return None, "Empty transcription"
        except Exception as e:
            return None, str(e)
        finally:
            self._clear_runtime_cache()

    @staticmethod
    def _log_timing(start: float, duration: Optional[float], retried: bool) -> None:
        elapsed = time.monotonic() - start
        if duration and duration > 0:
            rtf = elapsed / duration
            suffix = " (retry)" if retried else ""
            log(
                f"Qwen3-ASR: {elapsed:.2f}s for {duration:.1f}s audio (RTF={rtf:.2f}){suffix}",
                "INFO",
            )
        else:
            suffix = " (retry)" if retried else ""
            log(f"Qwen3-ASR: {elapsed:.2f}s{suffix}", "INFO")

    def _invoke(self, path: str, kwargs: dict, timeout: int):
        """Run transcribe with an optional hard timeout. Returns (text, error)."""
        timeout_val = timeout if timeout and timeout > 0 else None
        if timeout_val is None:
            result = self._model.transcribe(path, **kwargs)
        else:
            # Not `with`: __exit__ blocks on the runaway worker and defeats the timeout.
            executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="qwen3-transcribe"
            )
            future = executor.submit(self._model.transcribe, path, **kwargs)
            try:
                result = future.result(timeout=timeout_val)
                executor.shutdown(wait=True)
            except concurrent.futures.TimeoutError:
                executor.shutdown(wait=False, cancel_futures=True)
                # MLX transcribe is uninterruptable; the worker keeps running.
                self._leaked_workers += 1
                if self._leaked_workers >= self._LEAK_LOG_THRESHOLD:
                    log(
                        f"Qwen3-ASR: {self._leaked_workers} abandoned workers; "
                        "reload pending",
                        "WARN",
                    )
                return "", f"Transcription timed out after {timeout_val}s"
        text = result.text.strip() if result and hasattr(result, "text") and result.text else ""
        return text, None

    def unload(self) -> None:
        """Release model from RAM without destroying the engine."""
        if self._model is not None:
            try:
                self._model.close()
            except Exception:
                pass
            self._model = None
            self._clear_runtime_cache()
            log("Qwen3-ASR model unloaded (idle)", "INFO")
        self._leaked_workers = 0

    def close(self) -> None:
        if self._model is not None:
            try:
                self._model.close()
            except Exception:
                pass
        self._model = None
        self._clear_runtime_cache()
        log("Qwen3-ASR model unloaded", "INFO")
        self._leaked_workers = 0

    def _clear_runtime_cache(self) -> None:
        gc.collect()
        try:
            import mlx.core as mx

            mx.clear_cache()
        except Exception:
            pass

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Per-stage timeout wrapper for the transcription pipeline."""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .utils import log


@dataclass(frozen=True)
class TimedOut:
    stage: str
    seconds: float


def run_with_timeout(
    fn: Callable[..., Any],
    *args: Any,
    timeout_seconds: Optional[float],
    stage: str,
    **kwargs: Any,
) -> Any:
    """Run ``fn`` with a hard timeout. Returns the result or :class:`TimedOut`.

    Exceptions propagate. Timeout of 0 / None runs inline.
    """
    if timeout_seconds is None or timeout_seconds <= 0:
        return fn(*args, **kwargs)

    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix=f"watchdog-{stage}"
    )
    future = executor.submit(fn, *args, **kwargs)
    try:
        result = future.result(timeout=timeout_seconds)
        executor.shutdown(wait=True)
        return result
    except concurrent.futures.TimeoutError:
        log(f"Watchdog: {stage} exceeded {timeout_seconds:.1f}s, skipping", "WARN")
        executor.shutdown(wait=False, cancel_futures=True)
        return TimedOut(stage=stage, seconds=timeout_seconds)

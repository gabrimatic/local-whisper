# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Per-stage timeout wrapper for the transcription pipeline."""

from __future__ import annotations

import queue
import threading
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

    The worker is a daemon thread, not a ThreadPoolExecutor: executor workers
    are non-daemon and joined at interpreter exit, so a wedged engine call
    that outlived its timeout would block process shutdown forever.
    """
    if timeout_seconds is None or timeout_seconds <= 0:
        return fn(*args, **kwargs)

    result_queue: queue.Queue = queue.Queue(maxsize=1)

    def _worker():
        try:
            result_queue.put(("ok", fn(*args, **kwargs)))
        except BaseException as e:  # noqa: BLE001 - re-raised on the caller thread
            result_queue.put(("err", e))

    worker = threading.Thread(target=_worker, daemon=True, name=f"watchdog-{stage}")
    worker.start()
    try:
        kind, payload = result_queue.get(timeout=timeout_seconds)
    except queue.Empty:
        log(f"Watchdog: {stage} exceeded {timeout_seconds:.1f}s, skipping", "WARN")
        return TimedOut(stage=stage, seconds=timeout_seconds)
    if kind == "err":
        raise payload
    return payload

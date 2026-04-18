# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Tests for whisper_voice.watchdog."""

from __future__ import annotations

import threading
import time

import pytest

from whisper_voice.watchdog import TimedOut, run_with_timeout


def test_returns_value_when_under_budget():
    result = run_with_timeout(lambda: 42, timeout_seconds=1.0, stage="unit")
    assert result == 42


def test_zero_timeout_disables_watchdog():
    # 0 or None disables the timeout — the callable runs inline and the
    # executor is never created.
    started_on = []

    def work():
        started_on.append(threading.current_thread().name)
        return "ok"

    assert run_with_timeout(work, timeout_seconds=0, stage="inline") == "ok"
    assert run_with_timeout(work, timeout_seconds=None, stage="inline") == "ok"
    # Both invocations must have run on the caller's thread, not in a
    # watchdog worker.
    assert all(name != "watchdog-inline" for name in started_on)


def test_timeout_returns_sentinel_and_does_not_block():
    released = threading.Event()

    def slow():
        # Sleep longer than the watchdog but still return so the worker
        # thread exits cleanly after the timeout fires.
        time.sleep(0.4)
        released.set()
        return "late"

    start = time.monotonic()
    result = run_with_timeout(slow, timeout_seconds=0.05, stage="slow")
    elapsed = time.monotonic() - start

    assert isinstance(result, TimedOut)
    assert result.stage == "slow"
    assert result.seconds == pytest.approx(0.05, abs=0.01)
    # The watchdog must return quickly — the point is that we don't wait
    # for the runaway worker.
    assert elapsed < 0.3, f"watchdog blocked for {elapsed:.3f}s"


def test_exceptions_propagate():
    def bad():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_with_timeout(bad, timeout_seconds=1.0, stage="bad")


def test_args_and_kwargs_forwarded():
    def add(a, b, *, c):
        return a + b + c

    assert run_with_timeout(add, 1, 2, c=3, timeout_seconds=1.0, stage="add") == 6

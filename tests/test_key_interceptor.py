# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Tests for the CGEventTap key interceptor callback contract."""

import pytest

Quartz = pytest.importorskip("Quartz")

from whisper_voice import key_interceptor as ki  # noqa: E402


class TestTapDisabledRecovery:
    def test_disabled_by_timeout_reenables_tap(self, monkeypatch):
        # macOS delivers kCGEventTapDisabledByTimeout when it disables a tap
        # it considers slow. The callback must re-enable the stored tap or
        # recording-key suppression silently dies until service restart.
        interceptor = ki.KeyInterceptor()
        sentinel_tap = object()
        interceptor._tap = sentinel_tap

        enabled_calls = []
        monkeypatch.setattr(
            ki, "CGEventTapEnable", lambda tap, on: enabled_calls.append((tap, on))
        )

        event = object()
        result = interceptor._callback(
            None, Quartz.kCGEventTapDisabledByTimeout, event, None
        )

        assert result is event
        assert enabled_calls == [(sentinel_tap, True)]

    def test_disabled_by_user_input_reenables_tap(self, monkeypatch):
        interceptor = ki.KeyInterceptor()
        sentinel_tap = object()
        interceptor._tap = sentinel_tap

        enabled_calls = []
        monkeypatch.setattr(
            ki, "CGEventTapEnable", lambda tap, on: enabled_calls.append((tap, on))
        )

        event = object()
        result = interceptor._callback(
            None, Quartz.kCGEventTapDisabledByUserInput, event, None
        )

        assert result is event
        assert enabled_calls == [(sentinel_tap, True)]

    def test_disabled_event_without_tap_is_passthrough(self, monkeypatch):
        interceptor = ki.KeyInterceptor()
        assert interceptor._tap is None

        monkeypatch.setattr(
            ki, "CGEventTapEnable", lambda *_: pytest.fail("must not enable a None tap")
        )

        event = object()
        result = interceptor._callback(
            None, Quartz.kCGEventTapDisabledByTimeout, event, None
        )
        assert result is event

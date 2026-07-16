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


# ---------------------------------------------------------------------------
# Binding-match contract
# ---------------------------------------------------------------------------

KEY_G = 0x05
KEY_T = 0x11
KEY_F6 = 0x61
KEY_SPACE = 49
KEY_ESC = 53
KEYDOWN = Quartz.kCGEventKeyDown

_FLAG_FOR = {
    "ctrl": Quartz.kCGEventFlagMaskControl,
    "shift": Quartz.kCGEventFlagMaskShift,
    "cmd": Quartz.kCGEventFlagMaskCommand,
    "alt": Quartz.kCGEventFlagMaskAlternate,
}


def _flags(*modifiers):
    value = 0
    for m in modifiers:
        value |= _FLAG_FOR[m]
    return value


class _FakeEvent:
    def __init__(self, keycode, flags=0):
        self.keycode = keycode
        self.flags = flags


class _ImmediateThread:
    """Run the interceptor's off-thread callbacks inline for assertions."""

    def __init__(self, target, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


@pytest.fixture
def interceptor(monkeypatch):
    monkeypatch.setattr(
        ki, "CGEventGetIntegerValueField", lambda event, field: event.keycode
    )
    monkeypatch.setattr(ki, "CGEventGetFlags", lambda event: event.flags)
    monkeypatch.setattr(ki.threading, "Thread", _ImmediateThread)
    return ki.KeyInterceptor()


def _press(interceptor, keycode, flags=0):
    event = _FakeEvent(keycode, flags)
    return interceptor._callback(None, KEYDOWN, event, None), event


class TestBindingMatch:
    def test_exact_match_fires_and_suppresses(self, interceptor):
        fired = []
        interceptor.register_shortcut({"ctrl", "shift"}, "g", lambda: fired.append(1))
        result, _ = _press(interceptor, KEY_G, _flags("ctrl", "shift"))
        assert result is None  # suppressed
        assert fired == [1]

    def test_superset_modifiers_do_not_fire(self, interceptor):
        # ctrl+shift+g must NOT steal ctrl+shift+cmd+g.
        fired = []
        interceptor.register_shortcut({"ctrl", "shift"}, "g", lambda: fired.append(1))
        result, event = _press(interceptor, KEY_G, _flags("ctrl", "shift", "cmd"))
        assert result is event  # passes through
        assert fired == []

    def test_subset_modifiers_do_not_fire(self, interceptor):
        fired = []
        interceptor.register_shortcut({"ctrl", "shift"}, "g", lambda: fired.append(1))
        result, event = _press(interceptor, KEY_G, _flags("ctrl"))
        assert result is event
        assert fired == []

    def test_two_bindings_same_key_different_modifiers(self, interceptor):
        fired = []
        interceptor.register_shortcut({"ctrl", "shift"}, "g", lambda: fired.append("a"))
        interceptor.register_shortcut({"cmd"}, "g", lambda: fired.append("b"))
        _press(interceptor, KEY_G, _flags("ctrl", "shift"))
        _press(interceptor, KEY_G, _flags("cmd"))
        assert fired == ["a", "b"]

    def test_same_combo_reregistration_replaces(self, interceptor):
        fired = []
        interceptor.register_shortcut({"alt"}, "t", lambda: fired.append("old"))
        interceptor.register_shortcut({"alt"}, "t", lambda: fired.append("new"))
        _press(interceptor, KEY_T, _flags("alt"))
        assert fired == ["new"]

    def test_unregister_specific_combo(self, interceptor):
        fired = []
        interceptor.register_shortcut({"ctrl", "shift"}, "g", lambda: fired.append("a"))
        interceptor.register_shortcut({"cmd"}, "g", lambda: fired.append("b"))
        interceptor.unregister_shortcut("g", {"cmd"})
        result, event = _press(interceptor, KEY_G, _flags("cmd"))
        assert result is event
        _press(interceptor, KEY_G, _flags("ctrl", "shift"))
        assert fired == ["a"]

    def test_clear_shortcuts_removes_everything(self, interceptor):
        fired = []
        interceptor.register_shortcut({"ctrl", "shift"}, "g", lambda: fired.append(1))
        interceptor.clear_shortcuts()
        result, event = _press(interceptor, KEY_G, _flags("ctrl", "shift"))
        assert result is event
        assert fired == []

    def test_function_key_binding(self, interceptor):
        fired = []
        interceptor.register_shortcut(set(), "f6", lambda: fired.append(1))
        result, _ = _press(interceptor, KEY_F6)
        assert result is None
        assert fired == [1]

    def test_guard_busy_suppresses_our_combo_without_firing(self, interceptor):
        # A busy guard must swallow OUR combo (not leak a stray character),
        # but only for combos we own.
        fired = []
        interceptor.register_shortcut({"ctrl", "shift"}, "g", lambda: fired.append(1))
        interceptor.set_enabled_guard(lambda: False)
        result, _ = _press(interceptor, KEY_G, _flags("ctrl", "shift"))
        assert result is None
        assert fired == []
        # Unrelated keys still pass through untouched.
        result, event = _press(interceptor, KEY_T, _flags("cmd"))
        assert result is event

    def test_unbound_key_passes_through(self, interceptor):
        result, event = _press(interceptor, KEY_T, _flags("cmd"))
        assert result is event

    def test_capture_guard_passes_our_combo_through_without_firing(self, interceptor):
        # While a Settings shortcut recorder is capturing, OUR combos must
        # PASS THROUGH (so the recorder's local monitor can see and refuse
        # them) — not fire, and not be swallowed like the busy guard does.
        fired = []
        interceptor.register_shortcut({"ctrl", "shift"}, "g", lambda: fired.append(1))
        interceptor.set_capture_guard(lambda: True)
        result, event = _press(interceptor, KEY_G, _flags("ctrl", "shift"))
        assert result is event
        assert fired == []
        # Capture over: the binding fires and suppresses again.
        interceptor.set_capture_guard(lambda: False)
        result, _ = _press(interceptor, KEY_G, _flags("ctrl", "shift"))
        assert result is None
        assert fired == [1]


class TestRecordKeySuppression:
    def test_record_keycode_swallowed_when_idle(self, interceptor):
        interceptor.set_record_keycode(KEY_F6)
        result, _ = _press(interceptor, KEY_F6)
        assert result is None

    def test_record_keycode_routed_to_recording_handler(self, interceptor):
        seen = []
        interceptor.set_record_keycode(KEY_F6)
        interceptor.set_recording_handler(lambda keycode, flags: seen.append(keycode))
        interceptor.set_recording_active(True)
        result, _ = _press(interceptor, KEY_F6)
        assert result is None
        assert seen == [KEY_F6]

    def test_space_and_esc_suppressed_only_while_recording(self, interceptor):
        seen = []
        interceptor.set_recording_handler(lambda keycode, flags: seen.append(keycode))

        result, event = _press(interceptor, KEY_SPACE)
        assert result is event  # not recording: space passes through

        interceptor.set_recording_active(True)
        result, _ = _press(interceptor, KEY_SPACE)
        assert result is None
        result, _ = _press(interceptor, KEY_ESC)
        assert result is None
        assert seen == [KEY_SPACE, KEY_ESC]

    def test_no_record_keycode_for_modifier_triggers(self, interceptor):
        interceptor.set_record_keycode(None)
        result, event = _press(interceptor, KEY_F6)
        assert result is event

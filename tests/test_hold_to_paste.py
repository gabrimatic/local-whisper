# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Tests for hold-to-record output routing."""

import threading
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np


class _CapturedThread:
    calls = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        _CapturedThread.calls.append(self)

    def start(self):
        pass


def test_hold_recording_pastes_when_processing_finishes(monkeypatch):
    import whisper_voice.app_recording as recording_mod
    from whisper_voice.app_recording import RecordingMixin

    class DummyApp(RecordingMixin):
        pass

    app = DummyApp()
    audio = np.ones(16000, dtype=np.float32)
    app._hold_recording = True
    app._key_interceptor = None
    app._max_timer = None
    app._state_lock = threading.Lock()
    app._busy = False
    app.recorder = SimpleNamespace(
        recording=True,
        stop=Mock(return_value=audio),
        start_monitoring=Mock(),
    )
    app.config = SimpleNamespace(audio=SimpleNamespace(sample_rate=16000, min_duration=0))
    app._send_state_update = Mock()
    app._process = Mock()

    _CapturedThread.calls = []
    monkeypatch.setattr(recording_mod.threading, "Thread", _CapturedThread)

    app._stop_recording()

    assert app._hold_recording is False
    assert _CapturedThread.calls
    assert _CapturedThread.calls[-1].kwargs["target"] is app._process
    assert _CapturedThread.calls[-1].kwargs["args"] == (audio,)
    assert _CapturedThread.calls[-1].kwargs["kwargs"] == {"paste_at_cursor": True}


def test_hold_key_release_preserves_paste_route(monkeypatch):
    import whisper_voice.app_recording as recording_mod
    from whisper_voice.app_recording import RecordingMixin

    class DummyApp(RecordingMixin):
        pass

    app = DummyApp()
    record_key = object()
    audio = np.ones(16000, dtype=np.float32)
    app._record_key = record_key
    app._hold_timer = None
    app._hold_recording = True
    app._key_pressed = True
    app._key_interceptor = None
    app._max_timer = None
    app._state_lock = threading.Lock()
    app._busy = False
    app.recorder = SimpleNamespace(
        recording=True,
        stop=Mock(return_value=audio),
        start_monitoring=Mock(),
    )
    app.config = SimpleNamespace(audio=SimpleNamespace(sample_rate=16000, min_duration=0))
    app._send_state_update = Mock()
    app._process = Mock()

    _CapturedThread.calls = []
    monkeypatch.setattr(recording_mod.threading, "Thread", _CapturedThread)

    app._on_key_release(record_key)

    assert app._hold_recording is False
    assert _CapturedThread.calls
    assert _CapturedThread.calls[-1].kwargs["kwargs"] == {"paste_at_cursor": True}


def test_double_tap_recording_keeps_default_output_route(monkeypatch):
    import whisper_voice.app_recording as recording_mod
    from whisper_voice.app_recording import RecordingMixin

    class DummyApp(RecordingMixin):
        pass

    app = DummyApp()
    audio = np.ones(16000, dtype=np.float32)
    app._hold_recording = False
    app._key_interceptor = None
    app._max_timer = None
    app._state_lock = threading.Lock()
    app._busy = False
    app.recorder = SimpleNamespace(
        recording=True,
        stop=Mock(return_value=audio),
        start_monitoring=Mock(),
    )
    app.config = SimpleNamespace(audio=SimpleNamespace(sample_rate=16000, min_duration=0))
    app._send_state_update = Mock()
    app._process = Mock()

    _CapturedThread.calls = []
    monkeypatch.setattr(recording_mod.threading, "Thread", _CapturedThread)

    app._stop_recording()

    assert _CapturedThread.calls[-1].kwargs["kwargs"] == {"paste_at_cursor": False}


def test_hold_output_pastes_even_when_auto_paste_is_disabled():
    from whisper_voice.app_pipeline import PipelineMixin

    class DummyApp(PipelineMixin):
        pass

    app = DummyApp()
    app.config = SimpleNamespace(ui=SimpleNamespace(auto_paste=False))
    app._paste_text_at_cursor = Mock(return_value=True)
    app._copy_to_clipboard = Mock(return_value=True)

    assert app._deliver_transcription_text("hello", paste_at_cursor=True) is True
    app._paste_text_at_cursor.assert_called_once_with("hello")
    app._copy_to_clipboard.assert_not_called()


def test_double_tap_output_copies_when_auto_paste_is_disabled():
    from whisper_voice.app_pipeline import PipelineMixin

    class DummyApp(PipelineMixin):
        pass

    app = DummyApp()
    app.config = SimpleNamespace(ui=SimpleNamespace(auto_paste=False))
    app._paste_text_at_cursor = Mock(return_value=True)
    app._copy_to_clipboard = Mock(return_value=True)

    assert app._deliver_transcription_text("hello", paste_at_cursor=False) is True
    app._copy_to_clipboard.assert_called_once_with("hello", show_error=False)
    app._paste_text_at_cursor.assert_not_called()

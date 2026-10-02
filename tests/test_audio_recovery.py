# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Regression tests for stale macOS audio input recovery."""

import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np


class _ImmediateTimer:
    def __init__(self, *_args, **_kwargs):
        pass

    def start(self):
        pass


def test_hotkey_recording_resets_audio_host_after_all_zero_capture(monkeypatch):
    import whisper_voice.app_recording as recording_mod
    from whisper_voice.app_recording import RecordingMixin

    recorder = SimpleNamespace(
        recording=True,
        stop=Mock(return_value=np.zeros(32, dtype=np.float32)),
        start_monitoring=Mock(),
        reset_audio_host=Mock(),
    )

    class DummyApp(RecordingMixin):
        pass

    app = DummyApp()
    app._hold_recording = False
    app._key_interceptor = None
    app._max_timer = None
    app._state_lock = threading.Lock()
    app._busy = False
    app.recorder = recorder
    app.config = SimpleNamespace(audio=SimpleNamespace(sample_rate=16000, min_duration=0))
    app._send_state_error = Mock()
    app._reset_to_idle = Mock()

    monkeypatch.setattr(recording_mod, "play_sound", Mock())
    monkeypatch.setattr(recording_mod.threading, "Timer", _ImmediateTimer)

    app._stop_recording()

    recorder.reset_audio_host.assert_called_once_with(close_stream=False)
    app._send_state_error.assert_called_once_with("Mic permission?")


def test_cli_listen_resets_audio_host_after_all_zero_capture():
    from whisper_voice.app_commands import CommandsMixin

    recorder = SimpleNamespace(
        recording=False,
        stop=Mock(return_value=np.zeros(32, dtype=np.float32)),
        reset_audio_host=Mock(),
        start_monitoring=Mock(),
    )
    recorder.start = Mock(side_effect=lambda: setattr(recorder, "recording", True) or True)

    class DummyApp(CommandsMixin):
        def _touch_model_activity(self):
            pass

        def _reset_to_idle(self):
            pass

    app = DummyApp()
    app._state_lock = threading.Lock()
    app._busy = False
    app._ready = True
    app.recorder = recorder
    app.config = SimpleNamespace(audio=SimpleNamespace(sample_rate=16000))

    sent = []
    app._cmd_listen(
        {"max_duration": 0, "raw": True},
        sent.append,
        SimpleNamespace(wait=lambda timeout=None: None),
    )

    recorder.reset_audio_host.assert_called_once_with(close_stream=False)
    assert sent[-1] == {"type": "error", "message": "No audio captured"}


def test_recorder_start_uses_backoff_after_audio_host_reset(monkeypatch):
    import whisper_voice.audio as audio_mod
    from whisper_voice.audio import Recorder

    cfg = SimpleNamespace(audio=SimpleNamespace(sample_rate=16000, pre_buffer=0))
    monkeypatch.setattr(audio_mod, "get_config", Mock(return_value=cfg))

    class FakeStream:
        active = True

        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def close(self):
            pass

    sleeps = []
    recorder = Recorder()
    recorder._start_retries = 2
    recorder._wait_for_live_input = Mock(side_effect=[False, True])
    recorder.reset_audio_host = Mock()

    monkeypatch.setattr(audio_mod.sd, "InputStream", FakeStream)
    monkeypatch.setattr(audio_mod.time, "sleep", lambda seconds: sleeps.append(seconds))

    assert recorder.start() is True
    recorder.reset_audio_host.assert_called_once_with(close_stream=False)
    assert sleeps == [0.5]


def test_wait_for_live_input_keeps_waiting_through_initial_silence(monkeypatch):
    import whisper_voice.audio as audio_mod
    from whisper_voice.audio import Recorder

    cfg = SimpleNamespace(audio=SimpleNamespace(sample_rate=16000, pre_buffer=0))
    monkeypatch.setattr(audio_mod, "get_config", Mock(return_value=cfg))

    recorder = Recorder()
    recorder._input_warmup_timeout = 0.5
    recorder._reset_input_health()
    recorder._recording.set()

    result = {}

    def wait_for_input():
        result["ok"] = recorder._wait_for_live_input()

    waiter = threading.Thread(target=wait_for_input)
    waiter.start()

    # First CoreAudio callback after wake can be all zeros. That should make
    # the stream observable, but not fail the warm-up before the deadline.
    time_info = SimpleNamespace()
    recorder._callback(np.zeros((512, 1), dtype=np.float32), 512, time_info, None)
    time.sleep(0.03)
    assert waiter.is_alive()

    recorder._callback(np.ones((128, 1), dtype=np.float32) * 0.001, 128, time_info, None)
    waiter.join(timeout=1.0)

    assert result == {"ok": True}


def test_reset_audio_host_refreshes_device_query_and_swallows_query_errors(monkeypatch):
    import whisper_voice.audio as audio_mod
    from whisper_voice.audio import Recorder

    cfg = SimpleNamespace(audio=SimpleNamespace(sample_rate=16000, pre_buffer=0))
    monkeypatch.setattr(audio_mod, "get_config", Mock(return_value=cfg))

    recorder = Recorder()
    calls = []
    monkeypatch.setattr(audio_mod.sd, "_terminate", lambda: calls.append("terminate"), raising=False)
    monkeypatch.setattr(audio_mod.sd, "_initialize", lambda: calls.append("initialize"), raising=False)

    def fail_query_devices():
        calls.append("query_devices")
        raise RuntimeError("CoreAudio cache still settling")

    monkeypatch.setattr(audio_mod.sd, "query_devices", fail_query_devices, raising=False)

    recorder.reset_audio_host(close_stream=False)

    assert calls == ["terminate", "initialize", "query_devices"]


def test_post_wake_resync_resets_audio_host_even_without_prebuffer():
    from whisper_voice.app_audio_health import AudioHealthMixin

    class DummyApp(AudioHealthMixin):
        pass

    recorder = SimpleNamespace(
        recording=False,
        reset_audio_host=Mock(),
        stop_monitoring=Mock(),
        start_monitoring=Mock(),
    )
    app = DummyApp()
    app.recorder = recorder

    app._resync_audio()

    recorder.reset_audio_host.assert_called_once_with(close_stream=False)
    recorder.stop_monitoring.assert_called_once()
    recorder.start_monitoring.assert_called_once()


def test_start_recording_does_not_duplicate_generic_mic_error_log(monkeypatch):
    import whisper_voice.app_recording as recording_mod
    from whisper_voice.app_recording import RecordingMixin

    class DummyApp(RecordingMixin):
        pass

    app = DummyApp()
    app._tts_processor = None
    app._state_lock = threading.Lock()
    app._busy = False
    app._ready = True
    app._key_interceptor = None
    app._max_timer = None
    app.config = SimpleNamespace(audio=SimpleNamespace(max_duration=0))
    app.recorder = SimpleNamespace(recording=False, start=Mock(return_value=False))
    app._send_state_error = Mock()
    app._reset_to_idle = Mock()

    log = Mock()
    monkeypatch.setattr(recording_mod, "log", log)
    monkeypatch.setattr(recording_mod, "play_sound", Mock())
    monkeypatch.setattr(recording_mod.threading, "Timer", _ImmediateTimer)

    app._start_recording()

    assert ("Mic error", "ERR") not in [call.args for call in log.call_args_list]
    app._send_state_error.assert_called_once_with("Mic error")


def test_start_recording_surfaces_recorder_error_message(monkeypatch):
    import whisper_voice.app_recording as recording_mod
    from whisper_voice.app_recording import RecordingMixin

    class DummyApp(RecordingMixin):
        pass

    app = DummyApp()
    app._tts_processor = None
    app._state_lock = threading.Lock()
    app._busy = False
    app._ready = True
    app._key_interceptor = None
    app._max_timer = None
    app.config = SimpleNamespace(audio=SimpleNamespace(max_duration=0))
    app.recorder = SimpleNamespace(
        recording=False,
        start=Mock(return_value=False),
        last_error_message="No live microphone signal from BlackHole 2ch.",
    )
    app._send_state_error = Mock()
    app._reset_to_idle = Mock()

    monkeypatch.setattr(recording_mod, "log", Mock())
    monkeypatch.setattr(recording_mod, "play_sound", Mock())
    monkeypatch.setattr(recording_mod.threading, "Timer", _ImmediateTimer)

    app._start_recording()

    app._send_state_error.assert_called_once_with("No live microphone signal from BlackHole 2ch.")


def test_recorder_no_signal_message_names_virtual_default_input(monkeypatch):
    import whisper_voice.audio as audio_mod
    from whisper_voice.audio import Recorder

    cfg = SimpleNamespace(audio=SimpleNamespace(sample_rate=16000, pre_buffer=0))
    monkeypatch.setattr(audio_mod, "get_config", Mock(return_value=cfg))
    monkeypatch.setattr(
        audio_mod.sd,
        "default",
        SimpleNamespace(device=[7, 2]),
        raising=False,
    )

    def query_devices(device=None, kind=None):
        if device == 7:
            return {"name": "BlackHole 2ch", "max_input_channels": 2}
        if kind == "input":
            return {"name": "BlackHole 2ch", "max_input_channels": 2}
        return []

    monkeypatch.setattr(audio_mod.sd, "query_devices", query_devices, raising=False)

    recorder = Recorder()

    message = recorder.no_signal_error_message()

    assert "BlackHole 2ch" in message
    assert "Select a real input device" in message


def test_recorder_start_failure_keeps_user_facing_last_error(monkeypatch):
    import whisper_voice.audio as audio_mod
    from whisper_voice.audio import Recorder

    cfg = SimpleNamespace(audio=SimpleNamespace(sample_rate=16000, pre_buffer=0))
    monkeypatch.setattr(audio_mod, "get_config", Mock(return_value=cfg))
    monkeypatch.setattr(audio_mod.sd, "default", SimpleNamespace(device=[7, 2]), raising=False)
    monkeypatch.setattr(
        audio_mod.sd,
        "query_devices",
        lambda device=None, kind=None: {"name": "BlackHole 2ch", "max_input_channels": 2},
        raising=False,
    )

    class FakeStream:
        active = True

        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def close(self):
            pass

    recorder = Recorder()
    recorder._start_retries = 1
    recorder._wait_for_live_input = Mock(return_value=False)

    monkeypatch.setattr(audio_mod.sd, "InputStream", FakeStream)

    assert recorder.start() is False
    assert recorder.last_error_message is not None
    assert "BlackHole 2ch" in recorder.last_error_message

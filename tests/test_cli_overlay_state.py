"""CLI jobs must release the busy overlay on success and failure."""

import threading
from types import SimpleNamespace

import pytest

from whisper_voice.app_commands import CommandsMixin
from whisper_voice.app_ipc import IPCMixin
from whisper_voice.app_pipeline import PipelineMixin
from whisper_voice.app_recording import RecordingMixin


class _App(CommandsMixin, PipelineMixin, RecordingMixin, IPCMixin):
    def __init__(self, *, transcription_error=None):
        self._state_lock = threading.Lock()
        self._grammar_lock = threading.Lock()
        self._busy = False
        self._ready = True
        self._current_status = "Ready"
        self.messages = []
        self.ipc = SimpleNamespace(send=self.messages.append)
        self.config = SimpleNamespace(
            grammar=SimpleNamespace(enabled=True),
            replacements=SimpleNamespace(enabled=False, rules={}),
        )
        self.grammar = SimpleNamespace(fix=lambda text: (text + ".", None))
        self._grammar_ready = True
        self.transcriber = SimpleNamespace(
            transcribe=lambda path: (
                (None, transcription_error) if transcription_error else ("the bottle is on the desk", None)
            ),
        )
        self.recorder = SimpleNamespace(
            recording=False,
            start=lambda: False,
            start_monitoring=lambda: None,
            last_error_message="Microphone unavailable",
        )

    def _touch_model_activity(self):
        return True

    def _check_grammar_connection(self):
        return True


@pytest.mark.parametrize("error", [None, "Transcription failed"])
def test_file_transcription_releases_overlay_after_job(tmp_path, error):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio is supplied by the isolated engine boundary")
    app = _App(transcription_error=error)
    responses = []

    app._cmd_transcribe({"path": str(audio)}, responses.append, threading.Event())

    assert responses[-1]["type"] == ("error" if error else "done")
    assert app._busy is False
    assert app.messages, "CLI completion did not publish an idle state"
    assert app.messages[-1]["phase"] == "idle"
    assert app.messages[-1]["status_text"] == "Ready"
    if error is None:
        assert responses[-1]["text"] == "the bottle is on the desk."
        assert any(message["phase"] == "processing" for message in app.messages)


def test_failed_microphone_capture_releases_overlay():
    app = _App()
    responses = []

    app._cmd_listen({}, responses.append, threading.Event())

    assert responses[-1] == {"type": "error", "message": "Microphone unavailable"}
    assert app._busy is False
    assert app.messages, "Failed capture did not publish an idle state"
    assert app.messages[-1]["phase"] == "idle"


def test_rejected_cli_job_preserves_another_jobs_busy_state(tmp_path):
    audio = tmp_path / "audio.wav"
    audio.touch()
    app = _App()
    app._busy = True
    responses = []

    app._cmd_transcribe({"path": str(audio)}, responses.append, threading.Event())

    assert responses == [{"type": "error", "message": "Service is busy"}]
    assert app._busy is True
    assert app.messages == []

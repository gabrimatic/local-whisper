# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Regression tests for model cache truth and inline download progress."""

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def test_engine_status_rejects_incomplete_huggingface_cache(monkeypatch, tmp_path):
    import whisper_voice.engines.status as status_mod

    monkeypatch.setattr(status_mod, "MODEL_DIR", tmp_path)
    cache = tmp_path / "models--mlx-community--parakeet-tdt-0.6b-v3"
    (cache / "refs").mkdir(parents=True)
    (cache / "refs" / "main").write_text("abc123", encoding="utf-8")

    state = status_mod.engine_model_status("parakeet_v3")

    assert state["downloaded"] is False
    assert state["download_status"] == "partial"
    assert state["size_mb"] > 0


def test_engine_status_requires_complete_snapshot_files(monkeypatch, tmp_path):
    import whisper_voice.engines.status as status_mod

    monkeypatch.setattr(status_mod, "MODEL_DIR", tmp_path)
    snapshot = (
        tmp_path
        / "models--mlx-community--parakeet-tdt-0.6b-v3"
        / "snapshots"
        / "abc123"
    )
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "model.safetensors").write_bytes(b"weights")

    state = status_mod.engine_model_status("parakeet_v3")

    assert state["downloaded"] is True
    assert state["download_status"] == "downloaded"
    assert state["size_mb"] > 0


def test_engine_status_uses_configured_qwen_model_cache(monkeypatch, tmp_path):
    import whisper_voice.engines.status as status_mod

    monkeypatch.setattr(status_mod, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(
        "whisper_voice.config.get_config",
        lambda: SimpleNamespace(
            qwen3_asr=SimpleNamespace(model="mlx-community/Qwen3-ASR-1.7B-8bit"),
        ),
    )
    snapshot = (
        tmp_path
        / "models--mlx-community--Qwen3-ASR-1.7B-8bit"
        / "snapshots"
        / "abc123"
    )
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "model.safetensors").write_bytes(b"weights")

    state = status_mod.engine_model_status("qwen3_asr")

    assert state["downloaded"] is True
    assert state["hf_repo"] == "mlx-community/Qwen3-ASR-1.7B-8bit"
    assert state["cache_dir"].endswith("models--mlx-community--Qwen3-ASR-1.7B-8bit")


def test_qwen_prefetch_can_target_variant_without_changing_config(monkeypatch, tmp_path):
    import whisper_voice.engines.status as status_mod

    monkeypatch.setattr(status_mod, "MODEL_DIR", tmp_path)
    configured = "mlx-community/Qwen3-ASR-1.7B-bf16"
    requested = "mlx-community/Qwen3-ASR-0.6B-bf16"
    monkeypatch.setattr(
        "whisper_voice.config.get_config",
        lambda: SimpleNamespace(qwen3_asr=SimpleNamespace(model=configured)),
    )

    metadata = status_mod.engine_model_metadata("qwen3_asr", hf_repo=requested)

    assert metadata["hf_repo"] == requested
    assert metadata["cache_dir"].endswith("models--mlx-community--Qwen3-ASR-0.6B-bf16")


def test_apple_speech_status_reports_system_managed_asset(monkeypatch):
    import whisper_voice.engines.status as status_mod

    monkeypatch.setattr(
        "whisper_voice.engines.apple_speech.apple_speech_model_status",
        lambda: {
            "availability": "installed",
            "installed": True,
            "locale": "en-US",
            "message": "Ready",
        },
    )

    state = status_mod.engine_model_status("apple_speech")

    assert state["downloaded"] is True
    assert state["download_status"] == "installed"
    assert state["managed_by"] == "apple"
    assert state["available"] is True
    assert state["removable"] is True
    assert state["locale"] == "en-US"
    assert state["cache_dir"] is None


def _make_whisperkit_model(base: Path, model: str, *, complete: bool = True) -> Path:
    """Lay down a whisperkit-cli model dir the way `serve` does on disk."""
    model_dir = base / f"openai_{model}"
    packages = ("AudioEncoder.mlmodelc", "TextDecoder.mlmodelc", "MelSpectrogram.mlmodelc")
    for pkg in packages if complete else packages[:1]:
        p = model_dir / pkg
        p.mkdir(parents=True)
        (p / "model.mil").write_bytes(b"coreml")
    return model_dir


def test_whisperkit_status_reports_managed_removable_cache(monkeypatch, tmp_path):
    import whisper_voice.engines.status as status_mod

    monkeypatch.setattr(status_mod, "WHISPERKIT_MODELS_DIR", tmp_path)
    monkeypatch.setattr(
        "whisper_voice.config.get_config",
        lambda: SimpleNamespace(whisper=SimpleNamespace(model="whisper-large-v3-v20240930")),
    )
    model_dir = _make_whisperkit_model(tmp_path, "whisper-large-v3-v20240930")

    state = status_mod.engine_model_status("whisperkit")

    assert state["downloaded"] is True
    assert state["download_status"] == "downloaded"
    assert state["size_mb"] > 0
    assert state["removable"] is True
    assert state["managed_by"] == "whisperkit"
    assert state["cache_dir"] == str(model_dir)
    # No hf_repo: keeps whisperkit out of the HF DownloadWatcher/snapshot path.
    assert state["hf_repo"] is None
    assert state["warmed"] is False


def test_whisperkit_status_partial_when_a_coreml_package_is_missing(monkeypatch, tmp_path):
    import whisper_voice.engines.status as status_mod

    monkeypatch.setattr(status_mod, "WHISPERKIT_MODELS_DIR", tmp_path)
    monkeypatch.setattr(
        "whisper_voice.config.get_config",
        lambda: SimpleNamespace(whisper=SimpleNamespace(model="whisper-large-v3-v20240930")),
    )
    _make_whisperkit_model(tmp_path, "whisper-large-v3-v20240930", complete=False)

    state = status_mod.engine_model_status("whisperkit")

    assert state["downloaded"] is False
    assert state["download_status"] == "partial"
    assert state["removable"] is False


def test_whisperkit_status_missing_when_never_downloaded(monkeypatch, tmp_path):
    import whisper_voice.engines.status as status_mod

    monkeypatch.setattr(status_mod, "WHISPERKIT_MODELS_DIR", tmp_path)
    monkeypatch.setattr(
        "whisper_voice.config.get_config",
        lambda: SimpleNamespace(whisper=SimpleNamespace(model="whisper-large-v3-v20240930")),
    )

    state = status_mod.engine_model_status("whisperkit")

    assert state["downloaded"] is False
    assert state["download_status"] == "missing"
    assert state["size_mb"] is None
    assert state["removable"] is False
    # Still reports the deterministic target path so the switch can find it.
    assert state["cache_dir"].endswith("openai_whisper-large-v3-v20240930")


def test_whisperkit_remove_deletes_only_the_configured_model(monkeypatch, tmp_path):
    import whisper_voice.engines.status as status_mod

    monkeypatch.setattr(status_mod, "WHISPERKIT_MODELS_DIR", tmp_path)
    monkeypatch.setattr(
        "whisper_voice.config.get_config",
        lambda: SimpleNamespace(whisper=SimpleNamespace(model="whisper-large-v3-v20240930")),
    )
    target = _make_whisperkit_model(tmp_path, "whisper-large-v3-v20240930")
    other = _make_whisperkit_model(tmp_path, "whisper-tiny")

    assert status_mod.remove_engine_cache("whisperkit") is True
    assert not target.exists()
    # A different variant must survive — we only remove the configured model.
    assert other.exists()
    # A second removal is a no-op, not an error.
    assert status_mod.remove_engine_cache("whisperkit") is False


def test_apple_speech_switch_prepares_asset_before_unloading_current_engine(monkeypatch):
    import whisper_voice.app_switching as switching_mod
    from whisper_voice.app_switching import SwitchingMixin

    calls = []

    class FakeTranscriber:
        def __init__(self, engine_id):
            self.engine_id = engine_id

        def start(self):
            calls.append(("start", self.engine_id))
            return True

        def close(self):
            calls.append(("close", self.engine_id))

    class DummyApp(SwitchingMixin):
        pass

    app = DummyApp()
    app._busy = False
    app._state_lock = threading.Lock()
    app._download_cancel_lock = threading.Lock()
    app._download_cancel_events = {}
    app.config = SimpleNamespace(transcription=SimpleNamespace(engine="parakeet_v3"))
    app.transcriber = FakeTranscriber("parakeet_v3")
    app.recorder = SimpleNamespace(recording=False)
    app.ipc = SimpleNamespace(send=Mock())
    app._current_status = "Ready"
    app._send_state_update = Mock()
    app._send_state_error = Mock()
    app._send_engines_status = Mock()
    app._send_config_snapshot = Mock()

    monkeypatch.setattr(
        switching_mod,
        "engine_model_status",
        Mock(return_value={
            "downloaded": False,
            "cache_dir": None,
            "hf_repo": None,
            "managed_by": "apple",
        }),
    )
    monkeypatch.setattr(switching_mod, "Transcriber", FakeTranscriber)
    monkeypatch.setattr(
        "whisper_voice.engines.apple_speech.AppleSpeechEngine",
        lambda: FakeTranscriber("apple_speech"),
    )
    monkeypatch.setattr(switching_mod, "get_config", lambda: app.config)
    monkeypatch.setattr(
        "whisper_voice.config.update_config_field",
        lambda section, key, value: setattr(app.config.transcription, key, value),
    )

    app._switch_engine("apple_speech")

    assert calls.index(("start", "apple_speech")) < calls.index(("close", "parakeet_v3"))
    assert calls[-1] == ("start", "apple_speech")


def test_download_watcher_reports_aggregate_cache_bytes(tmp_path):
    from whisper_voice.engines.download_progress import DownloadWatcher

    cache = tmp_path / "models--org--model"
    cache.mkdir()
    (cache / "partial.bin").write_bytes(b"x" * 100)
    messages = []

    watcher = DownloadWatcher("test_model", cache, 200, messages.append)
    watcher.start()
    watcher.finish()

    first = messages[0]
    assert first["bytes"] == 100
    assert first["percent"] == 0.5


def test_download_watcher_has_distinct_canceled_phase(tmp_path):
    from whisper_voice.engines.download_progress import DownloadWatcher

    cache = tmp_path / "models--org--model"
    cache.mkdir()
    messages = []

    watcher = DownloadWatcher("test_model", cache, 0, messages.append)
    watcher.start()
    watcher.finish(error="Download canceled", phase="canceled")

    assert messages[-1]["phase"] == "canceled"
    assert messages[-1]["error"] == "Download canceled"


def test_transcription_panel_does_not_optimistically_mark_engine_active():
    root = Path(__file__).resolve().parents[1]
    panel = (
        root
        / "LocalWhisperUI"
        / "Sources"
        / "LocalWhisperUI"
        / "TranscriptionPanel.swift"
    ).read_text(encoding="utf-8")

    assert "appState.config.transcription.engine = id" not in panel
    assert 'sendAction("cancel_download"' in panel


def test_canceled_downloads_do_not_render_as_failed_selection_state():
    root = Path(__file__).resolve().parents[1]
    app_state = (
        root
        / "LocalWhisperUI"
        / "Sources"
        / "LocalWhisperUI"
        / "AppState.swift"
    ).read_text(encoding="utf-8")
    shared_views = (
        root
        / "LocalWhisperUI"
        / "Sources"
        / "LocalWhisperUI"
        / "SharedViews.swift"
    ).read_text(encoding="utf-8")

    assert 'progress.phase == "ready" || progress.phase == "canceled"' in app_state
    assert 'case "canceled":    return "Canceled"' in shared_views


def test_about_external_links_are_not_rendered_as_selected_state():
    root = Path(__file__).resolve().parents[1]
    about = (
        root
        / "LocalWhisperUI"
        / "Sources"
        / "LocalWhisperUI"
        / "AboutView.swift"
    ).read_text(encoding="utf-8")

    assert ".buttonStyle(.borderedProminent)" not in about


def test_permission_buttons_request_prompts_instead_of_only_opening_settings():
    root = Path(__file__).resolve().parents[1]
    onboarding = (
        root
        / "LocalWhisperUI"
        / "Sources"
        / "LocalWhisperUI"
        / "OnboardingView.swift"
    ).read_text(encoding="utf-8")
    advanced = (
        root
        / "LocalWhisperUI"
        / "Sources"
        / "LocalWhisperUI"
        / "AdvancedPanel.swift"
    ).read_text(encoding="utf-8")
    app_ipc = (root / "src" / "whisper_voice" / "app_ipc.py").read_text(encoding="utf-8")

    for source in (onboarding, advanced, app_ipc):
        assert "request_microphone_permission" in source
        assert "request_accessibility_permission" in source


def test_settings_model_downloads_stay_out_of_overlay_phase():
    root = Path(__file__).resolve().parents[1]
    switching = (root / "src" / "whisper_voice" / "app_switching.py").read_text(encoding="utf-8")

    assert 'self._send_state_update("idle", status_text=text)' in switching
    assert "model downloads do not open the" in switching


def test_engine_switch_download_failure_keeps_current_engine_loaded(monkeypatch, tmp_path):
    import whisper_voice.app_switching as switching_mod
    from whisper_voice.app_switching import SwitchingMixin

    class FakeWatcher:
        def __init__(self, *args, **kwargs):
            self.finished = False

        def start(self):
            pass

        def set_phase(self, phase):
            pass

        def finish(self, error=None):
            self.finished = True

    class DummyApp(SwitchingMixin):
        pass

    old_transcriber = SimpleNamespace(close=Mock())
    app = DummyApp()
    app._busy = False
    app._state_lock = threading.Lock()
    app._download_cancel_lock = threading.Lock()
    app._download_cancel_events = {}
    app.config = SimpleNamespace(transcription=SimpleNamespace(engine="parakeet_v3"))
    app.transcriber = old_transcriber
    app.recorder = SimpleNamespace(recording=False)
    app.ipc = SimpleNamespace(send=Mock())
    app._current_status = "Ready"
    app._send_state_update = Mock()
    app._send_state_error = Mock()
    app._send_engines_status = Mock()
    app._send_config_snapshot = Mock()
    app._prefetch_hf_snapshot = Mock(return_value=(False, "network down"))

    monkeypatch.setattr(
        switching_mod,
        "engine_model_status",
        Mock(return_value={
            "downloaded": False,
            "cache_dir": str(tmp_path / "models--org--model"),
            "hf_repo": "org/model",
        }),
    )
    assert "expected_size_bytes" not in switching_mod.__dict__
    monkeypatch.setattr(switching_mod, "DownloadWatcher", FakeWatcher)

    app._switch_engine("qwen3_asr")

    old_transcriber.close.assert_not_called()
    assert app.transcriber is old_transcriber
    assert app._settings_operation_active is False
    assert app._busy is False
    app._send_state_error.assert_not_called()
    assert all(call.args[0] == "idle" for call in app._send_state_update.call_args_list)


def test_whisperkit_switch_install_failure_keeps_current_engine_loaded(monkeypatch):
    import whisper_voice.app_switching as switching_mod
    from whisper_voice.app_switching import SwitchingMixin

    class DummyApp(SwitchingMixin):
        pass

    old_transcriber = SimpleNamespace(close=Mock())
    app = DummyApp()
    app._busy = False
    app._state_lock = threading.Lock()
    app._download_cancel_lock = threading.Lock()
    app._download_cancel_events = {}
    app.config = SimpleNamespace(transcription=SimpleNamespace(engine="parakeet_v3"))
    app.transcriber = old_transcriber
    app.recorder = SimpleNamespace(recording=False)
    app.ipc = SimpleNamespace(send=Mock())
    app._current_status = "Ready"
    app._send_state_update = Mock()
    app._send_state_error = Mock()
    app._send_engines_status = Mock()
    app._send_config_snapshot = Mock()

    monkeypatch.setattr(
        switching_mod,
        "engine_model_status",
        Mock(return_value={
            "downloaded": False,
            "cache_dir": None,
            "hf_repo": None,
        }),
    )
    monkeypatch.setattr(
        switching_mod,
        "require_whisperkit_cli",
        Mock(side_effect=RuntimeError("brew unavailable")),
    )

    app._switch_engine("whisperkit")

    old_transcriber.close.assert_not_called()
    assert app.transcriber is old_transcriber
    assert app._settings_operation_active is False
    assert app._busy is False
    app._send_config_snapshot.assert_not_called()


def test_engine_switch_failure_rolls_back_pending_model_config(monkeypatch, tmp_path):
    import whisper_voice.app_switching as switching_mod
    import whisper_voice.config as config_mod
    from whisper_voice.app_switching import SwitchingMixin

    class FakeWatcher:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def set_phase(self, phase):
            pass

        def finish(self, error=None, phase=None):
            pass

    class DummyApp(SwitchingMixin):
        pass

    old_transcriber = SimpleNamespace(close=Mock())
    app = DummyApp()
    app._busy = False
    app._state_lock = threading.Lock()
    app._download_cancel_lock = threading.Lock()
    app._download_cancel_events = {}
    app.config = SimpleNamespace(transcription=SimpleNamespace(engine="qwen3_asr"))
    app.transcriber = old_transcriber
    app.recorder = SimpleNamespace(recording=False)
    app.ipc = SimpleNamespace(send=Mock())
    app._current_status = "Ready"
    app._send_state_update = Mock()
    app._send_state_error = Mock()
    app._send_engines_status = Mock()
    app._send_config_snapshot = Mock()
    app._prefetch_hf_snapshot = Mock(return_value=(False, "network down"))

    monkeypatch.setattr(
        switching_mod,
        "engine_model_status",
        Mock(return_value={
            "downloaded": False,
            "cache_dir": str(tmp_path / "models--org--model"),
            "hf_repo": "org/model",
        }),
    )
    monkeypatch.setattr(switching_mod, "DownloadWatcher", FakeWatcher)
    updates = []
    monkeypatch.setattr(config_mod, "update_config_field", lambda *args: updates.append(args))
    monkeypatch.setattr(switching_mod, "get_config", lambda: app.config)

    app._switch_engine("qwen3_asr", ("qwen3_asr", "model", "old/model"))

    assert ("qwen3_asr", "model", "old/model") in updates
    old_transcriber.close.assert_not_called()
    assert app.transcriber is old_transcriber
    app._send_config_snapshot.assert_called_once()


def test_settings_operation_busy_snapshot_stays_idle():
    from whisper_voice.app_ipc import IPCMixin

    class DummyApp(IPCMixin):
        pass

    sent = []
    app = DummyApp()
    app.ipc = SimpleNamespace(send=sent.append)
    app.recorder = SimpleNamespace(recording=False, duration=0.0, rms_level=0.0)
    app._busy = True
    app._settings_operation_active = True
    app._current_status = "Downloading Qwen3-ASR model..."

    app._send_state_update()

    assert sent[-1]["phase"] == "idle"
    assert sent[-1]["status_text"] == "Downloading Qwen3-ASR model..."


def test_engine_switch_registers_cancel_before_first_progress(monkeypatch, tmp_path):
    import whisper_voice.app_switching as switching_mod
    from whisper_voice.app_switching import SwitchingMixin

    class DummyApp(SwitchingMixin):
        pass

    old_transcriber = SimpleNamespace(close=Mock())
    app = DummyApp()
    app._busy = False
    app._state_lock = threading.Lock()
    app._download_cancel_lock = threading.Lock()
    app._download_cancel_events = {}
    app.config = SimpleNamespace(transcription=SimpleNamespace(engine="parakeet_v3"))
    app.transcriber = old_transcriber
    app.recorder = SimpleNamespace(recording=False)
    app.ipc = SimpleNamespace(send=Mock())
    app._current_status = "Ready"
    app._send_state_update = Mock()
    app._send_state_error = Mock()
    app._send_engines_status = Mock()
    app._send_config_snapshot = Mock()

    class CancelOnFirstProgressWatcher:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            app._cancel_download("qwen3_asr")

        def set_phase(self, phase):
            pass

        def finish(self, error=None, phase=None):
            pass

    def prefetch(_target, _repo, cancel_event):
        assert cancel_event.is_set()
        return False, "Download canceled"

    app._prefetch_hf_snapshot = Mock(side_effect=prefetch)
    monkeypatch.setattr(
        switching_mod,
        "engine_model_status",
        Mock(return_value={
            "downloaded": False,
            "cache_dir": str(tmp_path / "models--org--model"),
            "hf_repo": "org/model",
        }),
    )
    monkeypatch.setattr(switching_mod, "DownloadWatcher", CancelOnFirstProgressWatcher)

    app._switch_engine("qwen3_asr")

    old_transcriber.close.assert_not_called()
    assert app._settings_operation_active is False
    assert app._busy is False
    assert any("download canceled" in (call.kwargs.get("status_text") or "").lower()
               for call in app._send_state_update.call_args_list)
    assert app._download_cancel_events == {}


def test_transcriber_start_prefetches_managed_model_before_engine_load(monkeypatch):
    import whisper_voice.transcriber as transcriber_mod

    calls = []

    class FakeEngine:
        name = "Qwen3-ASR"

        def start(self):
            calls.append("start")
            return True

        def running(self):
            return True

        def transcribe(self, path):
            return "ok", None

        def close(self):
            pass

    monkeypatch.setattr(transcriber_mod, "create_engine", lambda engine_id: FakeEngine())
    monkeypatch.setattr(
        transcriber_mod,
        "ensure_engine_model_cached",
        lambda engine_id: calls.append(("ensure", engine_id)),
        raising=False,
    )

    transcriber = transcriber_mod.Transcriber(engine_id="qwen3_asr")

    assert transcriber.start() is True
    assert calls == [("ensure", "qwen3_asr"), "start"]


def test_transcriber_normalizes_string_paths_before_engine_call(monkeypatch, tmp_path):
    import whisper_voice.transcriber as transcriber_mod

    seen = []

    class FakeEngine:
        name = "Qwen3-ASR"

        def start(self):
            return True

        def running(self):
            return True

        def transcribe(self, path):
            seen.append(path)
            return "ok", None

        def close(self):
            pass

    monkeypatch.setattr(transcriber_mod, "create_engine", lambda engine_id: FakeEngine())
    monkeypatch.setattr(transcriber_mod, "ensure_engine_model_cached", lambda engine_id: None)

    transcriber = transcriber_mod.Transcriber(engine_id="qwen3_asr")
    audio_path = tmp_path / "audio.wav"

    assert transcriber.transcribe(str(audio_path)) == ("ok", None)
    assert seen == [audio_path]


def test_whisperkit_engine_start_does_not_install_cli(monkeypatch):
    import whisper_voice.engines.whisperkit as whisperkit_mod
    from whisper_voice.engines.whisperkit import WhisperKitEngine

    monkeypatch.setattr(
        whisperkit_mod,
        "get_config",
        lambda: SimpleNamespace(
            whisper=SimpleNamespace(
                check_url="http://localhost:50060/health",
                model="large-v3-v20240930_626MB",
            ),
        ),
    )
    monkeypatch.setattr(WhisperKitEngine, "running", lambda self: False)
    monkeypatch.setattr(
        whisperkit_mod,
        "require_whisperkit_cli",
        Mock(side_effect=RuntimeError("WhisperKit CLI is not installed. Run: wh doctor --fix")),
    )
    popen = Mock()
    monkeypatch.setattr(whisperkit_mod.subprocess, "Popen", popen)

    engine = WhisperKitEngine()

    try:
        engine.start()
    except RuntimeError as exc:
        assert "wh doctor --fix" in str(exc)
    else:
        raise AssertionError("expected missing WhisperKit CLI to fail")

    popen.assert_not_called()

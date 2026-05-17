# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Single-instance service guard."""

from whisper_voice.app import _acquire_service_lock, _release_service_lock
from whisper_voice.cli import lifecycle
from whisper_voice.cli.constants import LOCK_FILE


def test_service_lock_allows_only_one_owner(tmp_path):
    lock_path = tmp_path / "service.lock"

    first = _acquire_service_lock(str(lock_path))
    assert first is not None
    try:
        assert _acquire_service_lock(str(lock_path)) is None
    finally:
        _release_service_lock(first)

    second = _acquire_service_lock(str(lock_path))
    assert second is not None
    _release_service_lock(second)


def test_service_lock_is_not_home_scoped():
    assert ".whisper" not in LOCK_FILE
    assert "local-whisper" in LOCK_FILE


def test_stop_cleans_legacy_processes_without_current_lock(monkeypatch, capsys):
    stopped = []

    monkeypatch.setattr(lifecycle, "_is_running", lambda: (False, None))
    monkeypatch.setattr(lifecycle, "_find_pids", lambda: [111, 222])
    monkeypatch.setattr(lifecycle, "_terminate_pids", lambda pids: stopped.append(pids))
    monkeypatch.setattr(lifecycle, "_cleanup_lock", lambda: None)

    lifecycle.cmd_stop()

    assert stopped == [[111, 222]]
    assert "Stopping legacy service processes" in capsys.readouterr().out


def test_homebrew_service_process_path_is_detected():
    command = (
        "/opt/homebrew/Cellar/python@3.12/3.12.13_2/Frameworks/Python.framework/"
        "Versions/3.12/Resources/Python.app/Contents/MacOS/Python "
        "/opt/homebrew/opt/local-whisper/bin/wh _run"
    )

    assert lifecycle._is_service_command(command)

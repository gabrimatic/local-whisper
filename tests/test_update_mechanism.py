# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Update command behavior."""

from types import SimpleNamespace

from whisper_voice.cli import doctor


def _ok(stdout="", stderr=""):
    return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)


def test_homebrew_update_refreshes_upgrades_models_and_restarts(monkeypatch):
    calls = []
    envs = []
    statuses = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        envs.append(kwargs.get("env"))
        if cmd == ["/opt/homebrew/bin/brew", "--prefix", doctor.FORMULA_NAME]:
            return _ok(stdout="/opt/homebrew/opt/local-whisper\n")
        return _ok()

    monkeypatch.setattr(doctor, "get_install_method", lambda: doctor.INSTALL_BREW)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/opt/homebrew/bin/{name}" if name == "brew" else None)
    monkeypatch.setattr(doctor.Path, "exists", lambda self: True)
    monkeypatch.setattr(doctor.subprocess, "run", fake_run)
    monkeypatch.setattr(doctor, "_wait_for_service_ready", lambda: True)

    assert doctor.cmd_update(status_callback=lambda phase, text: statuses.append((phase, text)))

    assert calls == [
        ["/opt/homebrew/bin/brew", "update"],
        ["/opt/homebrew/bin/brew", "upgrade", doctor.FORMULA_NAME],
        ["/opt/homebrew/bin/brew", "--prefix", doctor.FORMULA_NAME],
        ["/opt/homebrew/opt/local-whisper/bin/wh", "_prepare_models"],
        ["/opt/homebrew/bin/brew", "services", "restart", doctor.FORMULA_NAME],
    ]
    assert all(env is None or env.get("HOMEBREW_NO_INSTALL_CLEANUP") == "1" for env in envs)
    assert statuses[-1] == ("done", "Update complete")


def test_source_update_uses_fast_forward_pull_and_waits_for_ready(monkeypatch, tmp_path):
    calls = []
    statuses = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if cmd[:4] == ["/usr/bin/git", "-C", str(tmp_path), "symbolic-ref"]:
            return _ok(stdout="main\n")
        return _ok()

    monkeypatch.setattr(doctor, "get_install_method", lambda: doctor.INSTALL_SOURCE)
    monkeypatch.setattr(doctor.Path, "resolve", lambda self: tmp_path / "src/whisper_voice/cli/doctor.py")
    monkeypatch.setattr(doctor, "_get_venv_python", lambda: "/tmp/python")
    monkeypatch.setattr(doctor.shutil, "which", lambda name: { "git": "/usr/bin/git", "swift": "/usr/bin/swift" }.get(name))
    monkeypatch.setattr(doctor.subprocess, "run", fake_run)
    monkeypatch.setattr(doctor.subprocess, "check_output", lambda *args, **kwargs: "abc123\n")
    monkeypatch.setattr(doctor, "_update_models", lambda required=False: True)
    monkeypatch.setattr(doctor, "_wait_for_service_ready", lambda: True)
    monkeypatch.setattr(
        "whisper_voice.cli.build._local_whisper_ui_sources_newer_than_binary",
        lambda: False,
    )
    restarted = []

    assert doctor.cmd_update(
        status_callback=lambda phase, text: statuses.append((phase, text)),
        restart_callback=lambda: restarted.append(True),
    )

    assert ["/usr/bin/git", "-C", str(tmp_path), "fetch", "--prune", "origin"] in calls
    assert ["/usr/bin/git", "-C", str(tmp_path), "pull", "--ff-only", "origin", "main"] in calls
    assert ["/tmp/python", "-m", "pip", "install", "-e", str(tmp_path), "--upgrade", "--upgrade-strategy", "eager"] in calls
    assert restarted == [True]
    assert statuses[-1] == ("processing", "Updating: restarting service...")


def test_update_fails_before_restart_when_active_model_cannot_prepare(monkeypatch):
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if cmd == ["/opt/homebrew/bin/brew", "--prefix", doctor.FORMULA_NAME]:
            return _ok(stdout="/opt/homebrew/opt/local-whisper\n")
        if cmd == ["/opt/homebrew/opt/local-whisper/bin/wh", "_prepare_models"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="model missing")
        return _ok()

    monkeypatch.setattr(doctor, "get_install_method", lambda: doctor.INSTALL_BREW)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/opt/homebrew/bin/{name}" if name == "brew" else None)
    monkeypatch.setattr(doctor.Path, "exists", lambda self: True)
    monkeypatch.setattr(doctor.subprocess, "run", fake_run)

    assert not doctor.cmd_update()
    assert ["/opt/homebrew/bin/brew", "services", "restart", doctor.FORMULA_NAME] not in calls

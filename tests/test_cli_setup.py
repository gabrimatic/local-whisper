# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""CLI setup behavior."""

from types import SimpleNamespace

from whisper_voice.cli import lifecycle


def test_homebrew_start_uses_brew_services_without_existing_plist(monkeypatch, capsys):
    """Homebrew installs should create/start the service through brew services."""
    calls = []

    def fake_run(cmd, capture_output=False):
        calls.append((cmd, capture_output))
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(lifecycle, "get_install_method", lambda: lifecycle.INSTALL_BREW)
    monkeypatch.setattr(lifecycle, "_is_running", lambda: (False, None))
    monkeypatch.setattr(lifecycle.subprocess, "run", fake_run)

    lifecycle.cmd_start()

    assert calls == [(["brew", "services", "start", "local-whisper"], True)]
    assert "via brew services" in capsys.readouterr().out

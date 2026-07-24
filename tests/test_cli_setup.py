# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""CLI setup behavior."""

from pathlib import Path
from types import SimpleNamespace

from whisper_voice.cli import lifecycle

ROOT = Path(__file__).resolve().parents[1]


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


def test_source_setup_model_preparation_is_bounded():
    setup = (ROOT / "setup.sh").read_text(encoding="utf-8")

    assert "MODEL_PREP_TIMEOUT_SECONDS=180" in setup
    assert "run_with_timeout \"$MODEL_PREP_TIMEOUT_SECONDS\"" in setup


def test_source_setup_uses_configured_qwen_model_for_download_and_warmup():
    setup = (ROOT / "setup.sh").read_text(encoding="utf-8")

    assert "QWEN_MODEL=" in setup
    assert "print(load_config().qwen3_asr.model)" in setup
    assert setup.count("Qwen3ASR.from_pretrained(os.environ['QWEN_MODEL'])") == 2

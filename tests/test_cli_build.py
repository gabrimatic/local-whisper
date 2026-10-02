"""Rebuilding a signed executable must preserve its running inode."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from whisper_voice.cli import build


def _bundle_fixture(tmp_path, monkeypatch):
    source = tmp_path / "source/LocalWhisperUI"
    binaries = source / ".build/release"
    binaries.mkdir(parents=True)
    home = tmp_path / "home"
    installed = home / ".whisper/LocalWhisperUI.app/Contents/MacOS"
    installed.mkdir(parents=True)
    for name in ("LocalWhisperUI", "LocalWhisperSpeech"):
        (binaries / name).write_bytes(b"new executable")
        (installed / name).write_bytes(b"running executable")
    monkeypatch.setattr(build, "_local_whisper_ui_dir", lambda: source)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(build.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    return installed


@pytest.mark.parametrize("name", ["LocalWhisperUI", "LocalWhisperSpeech"])
def test_rebuild_preserves_running_executable_inode(tmp_path, monkeypatch, name):
    installed = _bundle_fixture(tmp_path, monkeypatch)
    destination = installed / name
    with destination.open("rb") as running:
        assert build._build_local_whisper_ui("swift")
        assert destination.read_bytes() == b"new executable"
        assert destination.stat().st_mode & 0o777 == 0o755
        assert running.read() == b"running executable"


def test_interrupted_copy_preserves_installed_executable(tmp_path, monkeypatch):
    installed = _bundle_fixture(tmp_path, monkeypatch)

    def failed_copy(source, destination):
        Path(destination).write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(build.shutil, "copy2", failed_copy)
    with pytest.raises(OSError, match="disk full"):
        build._build_local_whisper_ui("swift")

    assert (installed / "LocalWhisperUI").read_bytes() == b"running executable"
    assert sorted(path.name for path in installed.iterdir()) == ["LocalWhisperSpeech", "LocalWhisperUI"]

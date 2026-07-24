from whisper_voice import ui_bundle


def test_preferred_ui_binary_uses_current_homebrew_bundle(monkeypatch, tmp_path):
    cellar = tmp_path / "cellar" / "LocalWhisperUI"
    home = tmp_path / "home" / "LocalWhisperUI"
    cellar.parent.mkdir(parents=True)
    home.parent.mkdir(parents=True)
    cellar.touch()
    home.touch()

    monkeypatch.setattr(ui_bundle, "homebrew_ui_binary", lambda: cellar)
    monkeypatch.setattr(ui_bundle, "home_ui_binary", lambda: home)

    assert ui_bundle.preferred_ui_binary() == cellar


def test_preferred_ui_binary_falls_back_to_user_bundle(monkeypatch, tmp_path):
    cellar = tmp_path / "missing" / "LocalWhisperUI"
    home = tmp_path / "home" / "LocalWhisperUI"
    home.parent.mkdir(parents=True)
    home.touch()

    monkeypatch.setattr(ui_bundle, "homebrew_ui_binary", lambda: cellar)
    monkeypatch.setattr(ui_bundle, "home_ui_binary", lambda: home)

    assert ui_bundle.preferred_ui_binary() == home


def test_preferred_ui_binary_returns_user_path_when_neither_exists(monkeypatch, tmp_path):
    cellar = tmp_path / "missing-cellar" / "LocalWhisperUI"
    home = tmp_path / "missing-home" / "LocalWhisperUI"

    monkeypatch.setattr(ui_bundle, "homebrew_ui_binary", lambda: cellar)
    monkeypatch.setattr(ui_bundle, "home_ui_binary", lambda: home)

    assert ui_bundle.preferred_ui_binary() == home

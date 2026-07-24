# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Product contract checks for user-facing copy and source-of-truth metadata.
"""

import re
import tomllib
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_apple_intelligence_requirement_is_consistent():
    """Apple Intelligence copy should match the public macOS 26+ requirement."""
    paths = [
        "setup.sh",
        "src/whisper_voice/backends/__init__.py",
        "src/whisper_voice/grammar.py",
        "src/whisper_voice/cli/doctor.py",
        "LocalWhisperUI/Sources/LocalWhisperUI/OnboardingView.swift",
        "LocalWhisperUI/Sources/LocalWhisperUI/GrammarPanel.swift",
    ]

    for path in paths:
        content = _read(path)
        assert "macOS 15+" not in content, path
        assert "macOS 26+" in content, path


def test_apple_intelligence_optional_install_is_gated_to_macos_26():
    """Setup and doctor should not install Foundation Models support on unsupported macOS versions."""
    setup = _read("setup.sh")
    doctor = _read("src/whisper_voice/cli/doctor.py")

    assert 'if [[ "$MACOS_MAJOR" -ge 26 ]]' in setup
    assert "macos_major >= 26" in doctor


def test_user_facing_privacy_copy_allows_setup_network_access():
    """Privacy copy should not imply setup, model downloads, or updates never use the network."""
    paths = [
        "src/whisper_voice/__init__.py",
        "LocalWhisperUI/Sources/LocalWhisperUI/AboutView.swift",
        "LocalWhisperUI/Sources/LocalWhisperUI/OnboardingView.swift",
    ]

    for path in paths:
        content = _read(path).lower()
        assert "no internet" not in content, path
        assert "everything runs on your mac" not in content, path


def test_project_does_not_use_mlx_audio_runtime():
    """Transcription support must not depend on mlx-audio."""
    checked_paths = [
        "pyproject.toml",
        "setup.sh",
        "src/whisper_voice/engines/__init__.py",
        "src/whisper_voice/engines/status.py",
    ]

    for path in checked_paths:
        content = _read(path).lower()
        assert "mlx-audio" not in content, path
        assert "mlx_audio" not in content, path


def test_qwen3_product_surfaces_offer_both_supported_mlx_models():
    """The two maintained bf16 variants should be explicit in app and CLI configuration."""
    swift_settings = _read("LocalWhisperUI/Sources/LocalWhisperUI/EngineSettingsSections.swift")
    cli_editor = _read("src/whisper_voice/cli/editor.py")
    cli_help = _read("src/whisper_voice/cli/main.py")

    for content in (swift_settings, cli_editor):
        assert "mlx-community/Qwen3-ASR-1.7B-bf16" in content
        assert "mlx-community/Qwen3-ASR-0.6B-bf16" in content

    assert "Higher quality" in swift_settings
    assert "Lower memory" in swift_settings
    assert "wh engine qwen3_asr [1.7b|0.6b]" in cli_help


def test_qwen3_docs_state_runtime_boundary_and_variant_tradeoff():
    """Public docs must distinguish the community MLX path from Qwen's official runtime."""
    paths = [
        "README.md",
        "doc/product/engines.mdx",
        "doc/reference/configuration.mdx",
    ]

    for path in paths:
        content = _read(path)
        assert "mlx-community/Qwen3-ASR-1.7B-bf16" in content, path
        assert "mlx-community/Qwen3-ASR-0.6B-bf16" in content, path
        assert "community-maintained" in content, path
        assert "official PyTorch" in content, path
        assert "memory" in content.lower(), path
        assert "latency" in content.lower(), path


def test_qwen3_vocabulary_context_is_visible_and_capability_gated():
    """Product surfaces must explain the bounded local Vocabulary integration."""
    swift_settings = _read("LocalWhisperUI/Sources/LocalWhisperUI/EngineSettingsSections.swift")
    vocabulary_panel = _read("LocalWhisperUI/Sources/LocalWhisperUI/VocabularyPanel.swift")
    cli_editor = _read("src/whisper_voice/cli/editor.py")
    pyproject = tomllib.loads(_read("pyproject.toml"))

    assert "Use Vocabulary as context" in swift_settings
    assert "4,096 characters" in swift_settings
    assert "local context before transcription" in vocabulary_panel
    assert "Qwen vocabulary" in cli_editor
    assert "qwen3-asr-mlx==0.2.0" in pyproject["project"]["dependencies"]

    for path in (
        "README.md",
        "doc/product/engines.mdx",
        "doc/reference/configuration.mdx",
        "doc/reference/security.mdx",
    ):
        content = _read(path)
        assert "Vocabulary" in content, path
        assert "context" in content.lower(), path
        assert "4,096" in content, path
        assert "local" in content.lower(), path


def test_recommended_install_path_uses_homebrew_and_guided_setup():
    """Recommended install copy should lead with one command and finish with wh setup."""
    readme = _read("README.md")
    install_doc = _read("doc/reference/installation.mdx")
    installer = _read("install.sh")
    cli = _read("src/whisper_voice/cli/main.py")

    assert "https://gabrimatic.github.io/local-whisper/install.sh" in readme
    assert "https://gabrimatic.github.io/local-whisper/install.sh" in install_doc
    assert "raw.githubusercontent.com/gabrimatic/local-whisper/main/install.sh" not in readme
    assert "raw.githubusercontent.com/gabrimatic/local-whisper/main/install.sh" not in install_doc
    assert "brew install gabrimatic/local-whisper/local-whisper" in install_doc
    assert "wh setup" in install_doc
    assert "brew install gabrimatic/local-whisper/local-whisper" in installer
    assert 'elif cmd in ("setup", "install")' in cli
    combined = "\n".join([readme, install_doc, installer])
    assert "begin" + "ner" not in combined.lower()


def test_service_controls_are_clear_near_setup_docs():
    """Non-technical users should see service control commands before deep CLI details."""
    readme = _read("README.md")
    quickstart = _read("doc/quickstart.mdx")
    install_doc = _read("doc/reference/installation.mdx")

    for content in [readme, quickstart, install_doc]:
        assert "wh status    # Check whether Local Whisper is running" in content
        assert "wh start     # Start it again" in content
        assert "wh stop      # Stop it" in content
        assert "wh restart   # Stop and start cleanly" in content
        assert "Only one service can run at a time" in content


def test_legacy_docs_directory_has_moved_to_mintlify_doc():
    """The old docs directory should be represented only in the Mintlify doc source."""
    assert not (ROOT / "docs").exists()

    for path in [
        "doc/reference/configuration.mdx",
        "doc/reference/installation.mdx",
        "doc/product/mobile.mdx",
    ]:
        assert (ROOT / path).is_file(), path


def test_readme_links_to_published_documentation_site():
    """README should send readers to the published docs, not local source files."""
    readme = _read("README.md")

    assert "https://gabrimatic.github.io/local-whisper/" in readme
    assert "https://gabrimatic.github.io/local-whisper/reference/installation/" in readme
    assert "https://gabrimatic.github.io/local-whisper/reference/configuration/" in readme
    assert "https://gabrimatic.github.io/local-whisper/product/mobile/" in readme
    assert "[doc/" not in readme
    assert "](doc/" not in readme


def test_github_pages_auto_deploys_mintlify_doc_updates():
    """App docs pushes to main should automatically publish the Mintlify export to Pages."""
    workflow = _read(".github/workflows/docs-pages.yml")

    assert "push:" in workflow
    assert "branches: [main]" in workflow
    assert '"doc/**"' in workflow
    assert '"install.sh"' in workflow
    assert '".github/workflows/docs-pages.yml"' in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert "pages: write" in workflow
    assert "id-token: write" in workflow
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "cp ../install.sh ../_site/install.sh" in workflow
    assert "Deploy GitHub Pages" in workflow
    assert "actions/deploy-pages@v5" in workflow


def test_general_ci_does_not_run_expensive_jobs_for_docs_only_changes():
    """Docs-only updates should use the Ubuntu Pages workflow instead of full CI."""
    workflow = _read(".github/workflows/ci.yml")

    assert '      - "doc/**"' in workflow
    assert '      - "README.md"' in workflow
    assert '      - ".github/workflows/docs-pages.yml"' in workflow
    assert "group: ci-${{ github.ref }}" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "setup.sh syntax check" in workflow
    assert "runs-on: ubuntu-latest" in workflow


def test_configuration_reference_matches_generated_default_config():
    """The full TOML reference should stay aligned with generated config files."""
    from whisper_voice.config.schema import DEFAULT_CONFIG

    docs = _read("doc/reference/configuration.mdx")
    match = re.search(r"```toml\n(.*?)\n```", docs, re.DOTALL)
    assert match is not None

    default_config = tomllib.loads(DEFAULT_CONFIG)
    documented_config = tomllib.loads(match.group(1))

    assert documented_config.keys() == default_config.keys()
    for section in default_config:
        assert documented_config[section].keys() == default_config[section].keys(), section


def test_github_actions_use_current_node24_ready_actions():
    """CI should avoid deprecated Node 20 GitHub Actions runtimes."""
    workflow = _read(".github/workflows/ci.yml")
    pages_workflow = _read(".github/workflows/docs-pages.yml")
    dependabot = _read(".github/dependabot.yml")

    combined_workflows = f"{workflow}\n{pages_workflow}"

    assert "uses: actions/checkout@v7" in workflow
    assert "uses: actions/checkout@v7" in pages_workflow
    assert "uses: actions/checkout@v6" not in combined_workflows
    assert "uses: actions/setup-python@v6" in workflow
    assert 'package-ecosystem: "github-actions"' in dependabot


def test_ci_runs_flutter_static_and_widget_gates():
    """The mobile app is a public product surface and should be covered by CI."""
    workflow = _read(".github/workflows/ci.yml")
    dependabot = _read(".github/dependabot.yml")

    assert "src/flutter/local_whisper" in workflow
    assert "flutter analyze" in workflow
    assert "flutter test" in workflow
    assert 'package-ecosystem: "pub"' in dependabot
    assert 'directory: "/src/flutter/local_whisper"' in dependabot


def test_android_keyboard_honors_quick_insert_setting():
    """The Android input method should match the app's keyboard quick-insert toggle."""
    keyboard = _read(
        "src/flutter/local_whisper/android/app/src/main/kotlin/info/gabrimatic/localwhisper/LocalWhisperInputMethodService.kt"
    )

    assert "quickInsertEnabled()" in keyboard
    assert "if (quickInsertEnabled())" in keyboard
    assert '"[Clean] "' in keyboard
    assert '"[Prompt] "' in keyboard


def test_pydantic_core_pin_matches_pydantic_runtime_requirement():
    """The packaged Kokoro path must not ship mismatched pydantic-core wheels."""
    pyproject = tomllib.loads(_read("pyproject.toml"))
    dependencies = set(pyproject["project"]["dependencies"])
    pydantic_requires = {requirement.split(";", maxsplit=1)[0].strip() for requirement in metadata.requires("pydantic") or []}

    assert "pyobjc-framework-AVFoundation>=12.2" in dependencies
    assert "pyobjc-framework-ApplicationServices>=12.2" in dependencies
    assert "pydantic==2.13.4" in dependencies
    assert not any(dependency.startswith("pydantic-core==") for dependency in dependencies)
    assert "pydantic-core==2.46.4" in pydantic_requires

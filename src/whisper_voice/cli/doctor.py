# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Doctor and update commands."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from .constants import (
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_GREEN,
    C_RED,
    C_RESET,
    C_YELLOW,
    INSTALL_BREW,
    INSTALL_SOURCE,
    MODEL_DIR,
    get_install_method,
)
from .lifecycle import _get_config_path, _is_running


def _doctor_pass(msg: str):
    print(f"  {C_GREEN}✓{C_RESET}  {msg}")

def _doctor_fail(msg: str, hint: str = ""):
    print(f"  {C_RED}✗{C_RESET}  {msg}")
    if hint:
        print(f"      {C_DIM}→ {hint}{C_RESET}")

def _doctor_warn(msg: str, hint: str = ""):
    print(f"  {C_YELLOW}⚠{C_RESET}  {msg}")
    if hint:
        print(f"      {C_DIM}→ {hint}{C_RESET}")

def _doctor_info(msg: str):
    print(f"  {C_DIM}›{C_RESET}  {msg}")

def _doctor_fixing(msg: str):
    print(f"      {C_CYAN}→ {msg}{C_RESET}")


def _get_macos_major() -> Optional[int]:
    """Return the major macOS version number, or None."""
    try:
        result = subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True)
        return int(result.stdout.strip().split(".")[0])
    except Exception:
        return None


def _get_venv_python() -> Optional[str]:
    """Return the python interpreter for this installation."""
    if get_install_method() == INSTALL_BREW:
        return sys.executable

    # Source install: look for project venv
    try:
        project_root = Path(__file__).resolve().parents[3]
        for candidate in [
            project_root / ".venv" / "bin" / "python",
            project_root / "venv" / "bin" / "python",
        ]:
            if candidate.exists():
                return str(candidate)
    except (IndexError, OSError):
        pass
    return sys.executable


def cmd_doctor(args: list):
    """Check system health and optionally fix issues.

    Flags:
        --fix               Attempt automatic repair for fixable issues.
        --report [PATH]     Write a redacted, shareable diagnostic report.
                            Defaults to ~/Desktop/local-whisper-doctor.md.
    """
    fix = "--fix" in args
    report_idx = -1
    for flag in ("--report", "-r"):
        if flag in args:
            report_idx = args.index(flag)
            break
    if report_idx >= 0:
        report_path: Path
        if report_idx + 1 < len(args) and not args[report_idx + 1].startswith("-"):
            report_path = Path(args[report_idx + 1]).expanduser()
        else:
            report_path = Path.home() / "Desktop" / "local-whisper-doctor.md"
        from .doctor_report import write_doctor_report
        write_doctor_report(report_path)
        return

    core_ok = True
    install_method = get_install_method()
    python = _get_venv_python()

    print()
    print(f"  {C_BOLD}Core{C_RESET}")
    print()

    # 1. Python version
    v = sys.version_info
    if v >= (3, 11):
        _doctor_pass(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        _doctor_fail(f"Python {v.major}.{v.minor}.{v.micro}", "Python 3.11+ required")
        core_ok = False

    # 2. Virtual environment (source installs only)
    if install_method == INSTALL_SOURCE:
        project_root = Path(__file__).resolve().parents[3]
        venv_dir = project_root / ".venv"
        if venv_dir.is_dir():
            _doctor_pass("Virtual environment")
        else:
            _doctor_fail("Virtual environment not found", f"Run: python3 -m venv {venv_dir}")
            core_ok = False
    elif install_method == INSTALL_BREW:
        _doctor_pass("Homebrew installation")

    # 3. Core Python packages
    missing_pkgs = []
    for pkg in ["sounddevice", "numpy", "pynput", "parakeet_mlx", "qwen3_asr_mlx",
                "kokoro_mlx", "requests", "soundfile", "misaki"]:
        try:
            __import__(pkg)
        except ImportError:
            missing_pkgs.append(pkg)
    if not missing_pkgs:
        _doctor_pass("Core Python packages")
    else:
        if install_method == INSTALL_BREW:
            hint = "Run: brew reinstall local-whisper"
        elif not fix:
            hint = "Run: wh doctor --fix"
        else:
            hint = ""
        _doctor_fail(f"Missing packages: {', '.join(missing_pkgs)}", hint)
        if fix and install_method == INSTALL_SOURCE:
            project_root = Path(__file__).resolve().parents[3]
            macos_major = _get_macos_major()
            extras = "[apple-intelligence]" if macos_major and macos_major >= 15 else ""
            install_path = str(project_root) + extras
            _doctor_fixing(f"pip install -e {install_path}")
            result = subprocess.run(
                [python, "-m", "pip", "install", "-e", install_path],
                capture_output=True,
            )
            if result.returncode == 0:
                _doctor_pass("Packages installed")
            else:
                _doctor_fail("pip install failed")
                core_ok = False
        elif install_method != INSTALL_BREW:
            core_ok = False

    # 4. espeak-ng
    espeak_found = shutil.which("espeak-ng") is not None
    if not espeak_found:
        # Check via brew even if not on PATH
        try:
            result = subprocess.run(["brew", "list", "espeak-ng"], capture_output=True)
            espeak_found = result.returncode == 0
        except Exception:
            pass
    if espeak_found:
        _doctor_pass("espeak-ng")
    else:
        hint = "Run: brew install espeak-ng" if not fix else ""
        _doctor_fail("espeak-ng not installed", hint)
        if fix:
            _doctor_fixing("brew install espeak-ng")
            result = subprocess.run(["brew", "install", "espeak-ng"], capture_output=True)
            if result.returncode == 0:
                _doctor_pass("espeak-ng installed")
            else:
                _doctor_fail("brew install espeak-ng failed")
                core_ok = False
        else:
            core_ok = False

    # 5. spaCy model (only required when TTS is enabled)
    try:
        from whisper_voice.config import load_config
        tts_enabled = load_config().tts.enabled
    except Exception:
        tts_enabled = False

    if tts_enabled:
        spacy_ok = False
        try:
            result = subprocess.run(
                [python, "-c", "import spacy; spacy.load('en_core_web_sm')"],
                capture_output=True, timeout=15,
            )
            spacy_ok = result.returncode == 0
        except Exception:
            pass
        if spacy_ok:
            _doctor_pass("spaCy model (en_core_web_sm)")
        else:
            hint = "Run: python -m spacy download en_core_web_sm" if not fix else ""
            _doctor_fail("spaCy model en_core_web_sm not found", hint)
            if fix:
                _doctor_fixing("python -m spacy download en_core_web_sm")
                result = subprocess.run(
                    [python, "-m", "spacy", "download", "en_core_web_sm"],
                    capture_output=True,
                )
                if result.returncode == 0:
                    _doctor_pass("spaCy model installed")
                else:
                    _doctor_fail("spaCy model download failed")
                    core_ok = False
            else:
                core_ok = False
    else:
        _doctor_info("spaCy model (TTS disabled, not required)")

    # 6. Active transcription model only. Users who switch engines later
    # download + warm on that engine's first call (lazy-loaded).
    try:
        from whisper_voice.config import load_config
        active_engine = load_config().transcription.engine
    except Exception:
        active_engine = "parakeet_v3"

    engine_model_map = {
        "parakeet_v3": (
            "Parakeet-TDT v3",
            "models--mlx-community--parakeet-tdt-0.6b-v3",
            "from parakeet_mlx import from_pretrained; "
            "from_pretrained('mlx-community/parakeet-tdt-0.6b-v3')",
        ),
        "qwen3_asr": (
            "Qwen3-ASR",
            "models--mlx-community--Qwen3-ASR-1.7B-bf16",
            "from qwen3_asr_mlx import Qwen3ASR; "
            "Qwen3ASR.from_pretrained('mlx-community/Qwen3-ASR-1.7B-bf16')",
        ),
    }

    if active_engine in engine_model_map:
        label, dir_name, fetch_cmd = engine_model_map[active_engine]
        model_path = MODEL_DIR / dir_name
        if model_path.is_dir():
            _doctor_pass(f"{label} model (active engine)")
        else:
            hint = "Run: wh doctor --fix" if not fix else ""
            _doctor_fail(f"{label} model not found", hint)
            if fix:
                _doctor_fixing(f"Downloading {label} model...")
                MODEL_DIR.mkdir(parents=True, exist_ok=True)
                model_env = os.environ.copy()
                model_env["HF_HUB_CACHE"] = str(MODEL_DIR)
                model_env["HF_HUB_DISABLE_TELEMETRY"] = "1"
                model_env["HF_HUB_OFFLINE"] = "0"
                result = subprocess.run(
                    [python, "-c", fetch_cmd],
                    env=model_env, capture_output=True, timeout=600,
                )
                if result.returncode == 0:
                    _doctor_pass(f"{label} model downloaded")
                else:
                    _doctor_fail(f"{label} model download failed")
                    core_ok = False
            else:
                core_ok = False
    else:
        _doctor_info(f"Active engine '{active_engine}' manages its own model")

    # 7. Kokoro TTS model (only required when TTS is enabled)
    if tts_enabled:
        kokoro_model_dir = MODEL_DIR / "models--mlx-community--Kokoro-82M-bf16"
        if kokoro_model_dir.is_dir():
            _doctor_pass("Kokoro TTS model")
        else:
            hint = "Run: wh doctor --fix" if not fix else ""
            _doctor_fail("Kokoro TTS model not found", hint)
            if fix:
                _doctor_fixing("Downloading Kokoro TTS model...")
                MODEL_DIR.mkdir(parents=True, exist_ok=True)
                model_env = os.environ.copy()
                model_env["HF_HUB_CACHE"] = str(MODEL_DIR)
                model_env["HF_HUB_DISABLE_TELEMETRY"] = "1"
                model_env["HF_HUB_OFFLINE"] = "0"
                result = subprocess.run(
                    [python, "-c",
                     "from kokoro_mlx import KokoroTTS; "
                     "KokoroTTS.from_pretrained('mlx-community/Kokoro-82M-bf16')"],
                    env=model_env, capture_output=True, timeout=300,
                )
                if result.returncode == 0:
                    _doctor_pass("Kokoro TTS model downloaded")
                else:
                    _doctor_fail("Kokoro TTS model download failed")
                    core_ok = False
            else:
                core_ok = False
    else:
        _doctor_info("Kokoro TTS model (TTS disabled, not required)")

    # 8. Config file
    config_path = _get_config_path()
    if config_path.exists():
        _doctor_pass("Config file")
    else:
        hint = "Run: wh doctor --fix" if not fix else ""
        _doctor_fail("Config file not found", hint)
        if fix:
            _doctor_fixing("Creating default config...")
            try:
                from whisper_voice.config import CONFIG_DIR, DEFAULT_CONFIG
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
                _doctor_pass("Config file created")
            except Exception as e:
                _doctor_fail(f"Failed: {e}")
                core_ok = False
        else:
            core_ok = False

    # 9. Swift UI binary
    from .build import _homebrew_ui_binary
    from .constants import LAUNCHAGENT_PLIST
    ui_app = Path.home() / ".whisper" / "LocalWhisperUI.app"
    ui_found = ui_app.is_dir() or (install_method == INSTALL_BREW and _homebrew_ui_binary().exists())
    if ui_found:
        _doctor_pass("LocalWhisperUI.app")
    else:
        _doctor_warn("LocalWhisperUI.app not found", "Service will run headless without it")
        if fix:
            _doctor_fixing("Building Swift UI...")
            from .build import cmd_build
            cmd_build()
            if ui_app.is_dir() or _homebrew_ui_binary().exists():
                _doctor_pass("LocalWhisperUI.app built")
            else:
                _doctor_warn("Swift UI build failed (service works without it)")

    # 10. LaunchAgent / Homebrew service
    if install_method == INSTALL_BREW:
        brew_plist = Path.home() / "Library" / "LaunchAgents" / "homebrew.mxcl.local-whisper.plist"
        if brew_plist.exists():
            _doctor_pass("Homebrew service plist installed")
        else:
            _doctor_warn("Homebrew service not installed", "Run: brew services start local-whisper")
    elif LAUNCHAGENT_PLIST.exists():
        result = subprocess.run(
            ["launchctl", "list", "com.local-whisper"],
            capture_output=True,
        )
        if result.returncode == 0:
            _doctor_pass("LaunchAgent installed and loaded")
        else:
            hint = f"Run: launchctl load {LAUNCHAGENT_PLIST}" if not fix else ""
            _doctor_warn("LaunchAgent plist exists but not loaded", hint)
            if fix:
                _doctor_fixing("launchctl load")
                load_result = subprocess.run(
                    ["launchctl", "load", str(LAUNCHAGENT_PLIST)],
                    capture_output=True,
                    text=True,
                )
                if load_result.returncode == 0:
                    _doctor_pass("LaunchAgent loaded")
                else:
                    stderr = (load_result.stderr or "").strip()
                    _doctor_fail(
                        "launchctl load failed",
                        stderr or "Check the plist and permissions manually",
                    )
                    core_ok = False
    else:
        _doctor_fail("LaunchAgent not installed", "Run ./setup.sh to install")
        core_ok = False

    # 11. Accessibility permission
    try:
        from whisper_voice.utils import check_accessibility_trusted
        if check_accessibility_trusted():
            _doctor_pass("Accessibility permission")
        else:
            _doctor_fail("Accessibility permission not granted",
                         "System Settings → Privacy & Security → Accessibility")
            core_ok = False
    except Exception:
        _doctor_warn("Could not check Accessibility permission")

    # 12. Microphone permission
    try:
        from whisper_voice.utils import check_microphone_permission
        mic_ok, _ = check_microphone_permission()
        if mic_ok:
            _doctor_pass("Microphone permission")
        else:
            _doctor_fail("Microphone permission not granted",
                         "System Settings → Privacy & Security → Microphone")
            core_ok = False
    except Exception:
        _doctor_warn("Could not check Microphone permission")

    # 13. Service status
    running, pid = _is_running()
    if running:
        pid_str = str(pid) if pid else "unknown"
        _doctor_pass(f"Service running (pid {pid_str})")
    else:
        hint = "Run: wh start" if not fix else ""
        _doctor_fail("Service not running", hint)
        if fix:
            _doctor_fixing("Starting service...")
            from .lifecycle import cmd_start
            cmd_start()
            time.sleep(2)
            running, pid = _is_running()
            if running:
                _doctor_pass(f"Service started (pid {pid})")
            else:
                _doctor_fail("Service failed to start")
                core_ok = False
        else:
            core_ok = False

    # --- Optional ---
    print()
    print(f"  {C_BOLD}Optional{C_RESET}")
    print()

    # 14. Ollama
    if shutil.which("ollama"):
        try:
            import requests
            requests.get("http://localhost:11434/", timeout=2)
            _doctor_info("Ollama installed, server running")
        except Exception:
            _doctor_info("Ollama installed, server not running")
    else:
        _doctor_info("Ollama not installed")

    # 15. LM Studio
    if shutil.which("lms"):
        try:
            import requests
            requests.get("http://localhost:1234/", timeout=2)
            _doctor_info("LM Studio installed, server running")
        except Exception:
            _doctor_info("LM Studio installed, server not running")
    else:
        _doctor_info("LM Studio not installed")

    # 16. Apple Intelligence
    try:
        import apple_fm_sdk as fm
        try:
            if fm.SystemLanguageModel().is_available():
                _doctor_info("Apple Intelligence available")
            else:
                _doctor_info("Apple Intelligence SDK installed, model not available")
        except Exception:
            _doctor_info("Apple Intelligence SDK installed")
    except ImportError:
        _doctor_info("Apple Intelligence SDK not installed (optional, macOS 15+)")

    # 17. WhisperKit
    if shutil.which("whisperkit-cli"):
        _doctor_info("WhisperKit CLI installed")
    else:
        _doctor_info("WhisperKit CLI not installed (optional)")

    # Summary
    print()
    if core_ok:
        print(f"  {C_GREEN}{C_BOLD}All core checks passed.{C_RESET}")
    else:
        print(f"  {C_RED}{C_BOLD}Some core checks failed.{C_RESET}")
        if not fix:
            print(f"  {C_DIM}Run: wh doctor --fix{C_RESET}")
    print()

    sys.exit(0 if core_ok else 1)


def cmd_update():
    """Pull latest code, update dependencies, check model, rebuild Swift, and restart."""
    install_method = get_install_method()

    if install_method == INSTALL_BREW:
        print(f"\n  {C_BOLD}Updating via Homebrew...{C_RESET}")
        result = subprocess.run(["brew", "upgrade", "local-whisper"])
        if result.returncode != 0:
            print(f"{C_YELLOW}  brew upgrade returned non-zero (may already be up to date){C_RESET}")
        else:
            print(f"  {C_GREEN}Done{C_RESET}")

        # Still check models (brew upgrade doesn't download them)
        _update_models()

        print(f"\n  {C_BOLD}Restarting service...{C_RESET}")
        subprocess.run(["brew", "services", "restart", "local-whisper"])
        print(f"\n  {C_GREEN}{C_BOLD}Update complete.{C_RESET}")
        return

    project_root = Path(__file__).resolve().parents[3]
    python = _get_venv_python()

    # Step 1: git pull. Capture the pre-pull HEAD so a later step failure can
    # surface a "roll back to <sha>" hint rather than leaving the user guessing.
    print(f"\n  {C_BOLD}1/5  Pulling latest code...{C_RESET}")
    git = shutil.which("git")
    pre_pull_sha = None
    pulled = False
    if git:
        try:
            pre_pull_sha = subprocess.check_output(
                [git, "-C", str(project_root), "rev-parse", "HEAD"],
                text=True,
            ).strip()
        except Exception:
            pre_pull_sha = None
        result = subprocess.run(
            [git, "-C", str(project_root), "pull"],
        )
        if result.returncode != 0:
            print(f"{C_RED}  git pull failed. Aborting update so the service stays on known-good code.{C_RESET}", file=sys.stderr)
            print(f"  {C_DIM}Resolve the issue (conflicts, auth, or network) and rerun: wh update{C_RESET}", file=sys.stderr)
            sys.exit(1)
        pulled = True
        print(f"  {C_GREEN}Done{C_RESET}")
    else:
        print(f"  {C_YELLOW}git not found, skipping source refresh{C_RESET}")

    # Step 2: pip install -e . --upgrade
    print(f"\n  {C_BOLD}2/5  Updating Python dependencies...{C_RESET}")
    result = subprocess.run(
        [python, "-m", "pip", "install", "-e", str(project_root), "--upgrade", "--upgrade-strategy", "eager"],
    )
    if result.returncode != 0:
        print(f"{C_RED}  pip install failed{C_RESET}", file=sys.stderr)
        if pulled and pre_pull_sha and git:
            print(
                f"{C_DIM}  Local code was updated but dependencies failed. To roll back:{C_RESET}",
                file=sys.stderr,
            )
            print(
                f"{C_DIM}    git -C {project_root} reset --hard {pre_pull_sha}{C_RESET}",
                file=sys.stderr,
            )
        sys.exit(1)
    print(f"  {C_GREEN}Done{C_RESET}")

    # Step 3: check for model updates
    print(f"\n  {C_BOLD}3/5  Checking models...{C_RESET}")
    _update_models()

    # Step 4: rebuild LocalWhisperUI if sources newer than binary
    print(f"\n  {C_BOLD}4/5  Rebuilding LocalWhisperUI if needed...{C_RESET}")
    from .build import _build_local_whisper_ui, _local_whisper_ui_sources_newer_than_binary
    swift = shutil.which("swift")
    needs_ui_rebuild = _local_whisper_ui_sources_newer_than_binary()

    if not swift and needs_ui_rebuild:
        print(f"  {C_YELLOW}swift not found - skipping LocalWhisperUI rebuild{C_RESET}")
    else:
        if needs_ui_rebuild and swift:
            if not _build_local_whisper_ui(swift):
                print(f"  {C_RED}LocalWhisperUI build failed{C_RESET}", file=sys.stderr)
        elif not needs_ui_rebuild:
            print(f"  {C_DIM}LocalWhisperUI up to date{C_RESET}")

    # Step 5: restart the service
    print(f"\n  {C_BOLD}5/5  Restarting service...{C_RESET}")
    from .build import cmd_restart
    cmd_restart()
    print(f"\n  {C_GREEN}{C_BOLD}Update complete.{C_RESET}")


def _update_models():
    """Check and download updates for the active engine's model + Kokoro TTS."""
    python = _get_venv_python()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_env = os.environ.copy()
    model_env["HF_HUB_OFFLINE"] = "0"
    model_env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    model_env["HF_HUB_CACHE"] = str(MODEL_DIR)

    try:
        from whisper_voice.config import load_config
        active_engine = load_config().transcription.engine
    except Exception:
        active_engine = "parakeet_v3"

    engine_fetch = {
        "parakeet_v3": (
            "Parakeet-TDT v3",
            "from parakeet_mlx import from_pretrained; "
            "from_pretrained('mlx-community/parakeet-tdt-0.6b-v3'); "
            "print('Parakeet-TDT v3 up to date.')",
        ),
        "qwen3_asr": (
            "Qwen3-ASR",
            "from qwen3_asr_mlx import Qwen3ASR; "
            "Qwen3ASR.from_pretrained('mlx-community/Qwen3-ASR-1.7B-bf16'); "
            "print('Qwen3-ASR up to date.')",
        ),
    }

    if active_engine in engine_fetch:
        label, cmd = engine_fetch[active_engine]
        result = subprocess.run([python, "-c", cmd], env=model_env)
        if result.returncode != 0:
            print(f"{C_YELLOW}  {label} model check failed - skipping{C_RESET}")
    else:
        print(f"{C_DIM}  Active engine '{active_engine}' manages its own model.{C_RESET}")

    try:
        from whisper_voice.config import load_config
        tts_enabled = load_config().tts.enabled
    except Exception:
        tts_enabled = False

    if tts_enabled:
        result = subprocess.run(
            [
                python, "-c",
                "from kokoro_mlx import KokoroTTS; "
                "KokoroTTS.from_pretrained('mlx-community/Kokoro-82M-bf16'); "
                "print('Kokoro TTS up to date.')",
            ],
            env=model_env,
        )
        if result.returncode != 0:
            print(f"{C_YELLOW}  Kokoro TTS model check failed - skipping{C_RESET}")
    else:
        print(f"{C_DIM}  Kokoro TTS skipped (TTS disabled).{C_RESET}")

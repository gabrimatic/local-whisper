# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
CLI service controller for Local Whisper.

Usage:
    wh                  Status + help (default)
    wh status           Running? PID, backend, engine, config path
    wh start            Launch the service
    wh stop             Graceful kill (SIGTERM -> SIGKILL)
    wh restart          Stop + start
    wh whisper "text"   Speak text aloud via Kokoro TTS
    wh listen [secs]    Record from mic, output transcription
    wh transcribe file  Transcribe an audio file
    wh backend          Show current + list available
    wh backend <name>   Switch backend in config, restart service
    wh engine           Show current engine + list available
    wh engine <name>    Switch transcription engine, restart service
    wh config           Interactive config editor
    wh config edit      Open config.toml in $EDITOR
    wh config path      Print path to config file
    wh doctor           Check system health
    wh doctor --fix     Check and auto-repair issues
    wh uninstall        Remove LaunchAgent
    wh log              Tail ~/.whisper/service.log
    wh version          Show version
"""

import fcntl
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# Import TOML helpers from config (avoids duplication)
try:
    from whisper_voice.config import _find_in_section, _replace_in_section
except ImportError:
    # Fallback stubs used if config import fails (e.g., during install before venv)
    def _find_in_section(content, section, key):  # type: ignore[misc]
        return None

    def _replace_in_section(content, section, key, new_value):  # type: ignore[misc]
        return content

# Color constants
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"

LOCK_FILE = str(Path.home() / ".whisper" / "service.lock")
LAUNCHAGENT_LABEL = "com.local-whisper"
LAUNCHAGENT_PLIST = Path.home() / "Library" / "LaunchAgents" / "com.local-whisper.plist"
LOG_FILE = Path.home() / ".whisper" / "service.log"
MODEL_DIR = Path.home() / ".whisper" / "models"


def _is_running() -> tuple:
    """Check if the service is running. Returns (is_running, pid_or_None)."""
    if not os.path.exists(LOCK_FILE):
        return False, None
    try:
        lf = open(LOCK_FILE, "r+")
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Got lock - service is not running (stale lock)
        fcntl.flock(lf, fcntl.LOCK_UN)
        lf.close()
        return False, None
    except FileNotFoundError:
        return False, None
    except OSError:
        # Lock held - service is running, find PID
        pid = _find_pid()
        return True, pid


def _find_pid() -> Optional[int]:
    """Find the service PID."""
    my_pid = os.getpid()
    for pattern in ["wh _run", "whisper_voice", "/bin/wh"]:
        try:
            result = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                for p in result.stdout.strip().split():
                    pid = int(p)
                    if pid != my_pid:
                        return pid
        except Exception:
            pass
    return None


def _cleanup_lock():
    """Remove stale lock file after service stops."""
    try:
        os.unlink(LOCK_FILE)
    except OSError:
        pass


def _get_config_path() -> Path:
    """Return the config file path."""
    return Path.home() / ".whisper" / "config.toml"


def _read_config_backend() -> Optional[str]:
    """Read the current backend from config.toml."""
    config_file = _get_config_path()
    if not config_file.exists():
        return None
    try:
        content = config_file.read_text()
        return _find_in_section(content, "grammar", "backend")
    except Exception:
        pass
    return None


def _write_config_backend(new_backend: str) -> bool:
    """Write a new backend value to config.toml. Returns True on success."""
    config_file = _get_config_path()
    if not config_file.exists():
        print(f"{C_RED}Config file not found: {config_file}{C_RESET}", file=sys.stderr)
        return False
    try:
        fd = os.open(str(config_file), os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            content = config_file.read_text()
            new_content = _replace_in_section(content, "grammar", "backend", f'"{new_backend}"')
            if new_content == content:
                # Key not found - add it
                if "[grammar]" in new_content:
                    new_content = new_content.replace(
                        "[grammar]",
                        f'[grammar]\nbackend = "{new_backend}"',
                        1
                    )
                else:
                    new_content += f'\n[grammar]\nbackend = "{new_backend}"\n'
            # Update enabled flag in [grammar] section only
            enabled_val = "false" if new_backend == "none" else "true"
            new_content = _replace_in_section(new_content, "grammar", "enabled", enabled_val)
            config_file.write_text(new_content)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return True
    except Exception as e:
        print(f"{C_RED}Failed to write config: {e}{C_RESET}", file=sys.stderr)
        return False


def _list_backends() -> dict:
    """Return BACKEND_REGISTRY without importing heavy modules."""
    try:
        from whisper_voice.backends import BACKEND_REGISTRY
        return BACKEND_REGISTRY
    except Exception:
        return {}


def _read_config_engine() -> Optional[str]:
    """Read the current transcription engine from config.toml."""
    config_file = _get_config_path()
    if not config_file.exists():
        return None
    try:
        content = config_file.read_text()
        return _find_in_section(content, "transcription", "engine")
    except Exception:
        pass
    return None


def _write_config_engine(engine_id: str) -> bool:
    """Write a new engine value to config.toml. Returns True on success."""
    config_file = _get_config_path()
    if not config_file.exists():
        print(f"{C_RED}Config file not found: {config_file}{C_RESET}", file=sys.stderr)
        return False
    try:
        fd = os.open(str(config_file), os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            content = config_file.read_text()
            new_content = _replace_in_section(content, "transcription", "engine", f'"{engine_id}"')
            if new_content == content:
                # Key not found - add it
                if "[transcription]" in new_content:
                    new_content = new_content.replace(
                        "[transcription]",
                        f'[transcription]\nengine = "{engine_id}"',
                        1
                    )
                else:
                    new_content += f'\n[transcription]\nengine = "{engine_id}"\n'
            config_file.write_text(new_content)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return True
    except Exception as e:
        print(f"{C_RED}Failed to write config: {e}{C_RESET}", file=sys.stderr)
        return False


def _list_engines() -> dict:
    """Return ENGINE_REGISTRY without importing heavy modules."""
    try:
        from whisper_voice.engines import ENGINE_REGISTRY
        return ENGINE_REGISTRY
    except Exception:
        return {}


def cmd_status():
    """Show service status."""
    running, pid = _is_running()
    backend = _read_config_backend() or "unknown"
    engine = _read_config_engine() or "unknown"
    config_path = _get_config_path()

    if running:
        pid_str = str(pid) if pid else "unknown"
        print(f"  {C_GREEN}{C_BOLD}Running{C_RESET}  pid {C_DIM}{pid_str}{C_RESET}")
    else:
        print(f"  {C_DIM}Stopped{C_RESET}")

    print(f"  {C_DIM}engine: {C_RESET} {engine}")
    print(f"  {C_DIM}backend:{C_RESET} {backend}")
    print(f"  {C_DIM}config: {C_RESET} {config_path}")


def cmd_start():
    """Launch the service."""
    running, pid = _is_running()
    if running:
        pid_str = str(pid) if pid else "unknown"
        print(f"{C_YELLOW}Already running (pid {pid_str}){C_RESET}")
        return

    if LAUNCHAGENT_PLIST.exists():
        result = subprocess.run(["launchctl", "start", LAUNCHAGENT_LABEL], capture_output=True)
        if result.returncode == 0:
            print(f"{C_GREEN}Started{C_RESET} (via LaunchAgent)")
        else:
            # launchctl start can fail if already loaded but stopped; try kickstart
            uid = os.getuid()
            subprocess.Popen(
                ["launchctl", "kickstart", f"gui/{uid}/{LAUNCHAGENT_LABEL}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            print(f"{C_GREEN}Started{C_RESET} (via LaunchAgent)")
    else:
        # No LaunchAgent installed - spawn directly
        wh_path = str(Path(sys.argv[0]).resolve())
        subprocess.Popen(
            [wh_path, "_run"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(f"{C_GREEN}Started{C_RESET}")


def cmd_stop():
    """Graceful kill with SIGTERM -> SIGKILL fallback."""
    running, pid = _is_running()
    if not running:
        print(f"{C_DIM}Not running{C_RESET}")
        return

    if pid is None:
        print(f"{C_YELLOW}Running but PID not found - check Activity Monitor{C_RESET}", file=sys.stderr)
        return

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"{C_DIM}Stopping (pid {pid})...{C_RESET}")

        # Wait up to 5s for graceful exit
        for _ in range(50):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                _cleanup_lock()
                print(f"{C_GREEN}Stopped{C_RESET}")
                return

        # Force kill
        try:
            os.kill(pid, signal.SIGKILL)
            _cleanup_lock()
            print(f"{C_YELLOW}Force-killed{C_RESET}")
        except ProcessLookupError:
            _cleanup_lock()
            print(f"{C_GREEN}Stopped{C_RESET}")

    except ProcessLookupError:
        _cleanup_lock()
        print(f"{C_GREEN}Stopped{C_RESET}")
    except PermissionError:
        print(f"{C_RED}Permission denied to kill pid {pid}{C_RESET}", file=sys.stderr)
        sys.exit(1)


def _local_whisper_ui_dir() -> Path:
    """Return the LocalWhisperUI Swift package source directory (repo root)."""
    return Path(__file__).parent.parent.parent / "LocalWhisperUI"


def _local_whisper_ui_binary() -> Path:
    """Return the expected path of the installed LocalWhisperUI binary."""
    return Path.home() / ".whisper" / "LocalWhisperUI.app" / "Contents" / "MacOS" / "LocalWhisperUI"


def _local_whisper_ui_sources_newer_than_binary() -> bool:
    """Return True if any LocalWhisperUI Swift source is newer than the installed binary."""
    binary = _local_whisper_ui_binary()
    if not binary.exists():
        return True
    binary_mtime = binary.stat().st_mtime
    sources_dir = _local_whisper_ui_dir() / "Sources"
    if not sources_dir.exists():
        return False
    for src in sources_dir.rglob("*.swift"):
        if src.stat().st_mtime > binary_mtime:
            return True
    return False


_LOCAL_WHISPER_UI_INFO_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>LocalWhisperUI</string>
    <key>CFBundleIdentifier</key>
    <string>com.local-whisper.ui</string>
    <key>CFBundleName</key>
    <string>Local Whisper</string>
    <key>CFBundleVersion</key>
    <string>1.3.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.3.0</string>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
</dict>
</plist>
"""


def _build_local_whisper_ui(swift: str) -> bool:
    """Build the LocalWhisperUI Swift package and assemble the .app bundle.

    Returns True on success, False on failure.
    """
    ui_dir = _local_whisper_ui_dir()
    if not ui_dir.exists():
        print(f"{C_RED}LocalWhisperUI directory not found: {ui_dir}{C_RESET}", file=sys.stderr)
        return False

    print(f"{C_DIM}Building LocalWhisperUI...{C_RESET}")
    result = subprocess.run(
        [swift, "build", "-c", "release"],
        cwd=str(ui_dir),
    )
    if result.returncode != 0:
        print(f"{C_RED}LocalWhisperUI build failed{C_RESET}", file=sys.stderr)
        return False

    # Assemble .app bundle
    built_binary = ui_dir / ".build" / "release" / "LocalWhisperUI"
    if not built_binary.exists():
        print(f"{C_RED}Built binary not found: {built_binary}{C_RESET}", file=sys.stderr)
        return False

    macos_dir = Path.home() / ".whisper" / "LocalWhisperUI.app" / "Contents" / "MacOS"
    macos_dir.mkdir(parents=True, exist_ok=True)

    dest_binary = macos_dir / "LocalWhisperUI"
    shutil.copy2(str(built_binary), str(dest_binary))
    dest_binary.chmod(0o755)

    info_plist_path = macos_dir.parent / "Info.plist"
    info_plist_path.write_text(_LOCAL_WHISPER_UI_INFO_PLIST)

    print(f"{C_GREEN}LocalWhisperUI built:{C_RESET} {macos_dir.parent.parent}")
    return True


def cmd_build():
    """Build the LocalWhisperUI Swift package."""
    swift = shutil.which("swift")
    if not swift:
        print(f"{C_RED}swift not found - install Xcode or Xcode Command Line Tools{C_RESET}", file=sys.stderr)
        sys.exit(1)

    if not _build_local_whisper_ui(swift):
        sys.exit(1)


def cmd_restart(rebuild: bool = False):
    """Stop then start, optionally rebuilding LocalWhisperUI first."""
    needs_ui_rebuild = rebuild or _local_whisper_ui_sources_newer_than_binary()

    swift = None
    if needs_ui_rebuild:
        swift = shutil.which("swift")
        if not swift:
            print(f"{C_RED}swift not found - install Xcode or Xcode Command Line Tools{C_RESET}", file=sys.stderr)
            sys.exit(1)

    if needs_ui_rebuild:
        if not rebuild:
            print(f"{C_YELLOW}LocalWhisperUI sources changed - rebuilding...{C_RESET}")
        if not _build_local_whisper_ui(swift):
            sys.exit(1)

    cmd_stop()
    # Wait for lock to actually release (up to 3s)
    for _ in range(30):
        time.sleep(0.1)
        running, _ = _is_running()
        if not running:
            break
    cmd_start()


def cmd_backend(args: list):
    """Show or switch backend."""
    backends = _list_backends()

    if not args:
        # Show current + list available
        current = _read_config_backend() or "none"
        print(f"  {C_DIM}current:{C_RESET} {C_CYAN}{current}{C_RESET}")
        print()
        if backends:
            print(f"  {C_BOLD}Available:{C_RESET}")
            for bid, info in backends.items():
                marker = f" {C_GREEN}(active){C_RESET}" if bid == current else ""
                print(f"    {C_CYAN}{bid}{C_RESET}  {C_DIM}{info.description}{C_RESET}{marker}")
            print(f"    {C_CYAN}none{C_RESET}  {C_DIM}transcription only, no grammar{C_RESET}")
        else:
            print(f"  {C_DIM}Could not load backend list{C_RESET}")
        return

    new_backend = args[0]
    valid_ids = set(backends.keys()) | {"none"}
    if new_backend not in valid_ids:
        available = ", ".join(sorted(valid_ids))
        print(f"{C_RED}Unknown backend: {new_backend}{C_RESET}", file=sys.stderr)
        print(f"{C_DIM}Available: {available}{C_RESET}", file=sys.stderr)
        sys.exit(1)

    if not _write_config_backend(new_backend):
        sys.exit(1)

    print(f"{C_GREEN}Backend set to:{C_RESET} {new_backend}")

    running, _ = _is_running()
    if running:
        print(f"{C_DIM}Restarting service...{C_RESET}")
        cmd_restart()
    else:
        print(f"{C_DIM}Service not running - start with: wh start{C_RESET}")


def cmd_engine(args: list):
    """Show or switch transcription engine."""
    engines = _list_engines()

    if not args:
        # Show current + list available
        current = _read_config_engine() or "unknown"
        print(f"  {C_DIM}current:{C_RESET} {C_CYAN}{current}{C_RESET}")
        print()
        if engines:
            print(f"  {C_BOLD}Available:{C_RESET}")
            for eid, info in engines.items():
                marker = f" {C_GREEN}(active){C_RESET}" if eid == current else ""
                print(f"    {C_CYAN}{eid}{C_RESET}  {C_DIM}{info.description}{C_RESET}{marker}")
        else:
            print(f"  {C_DIM}Could not load engine list{C_RESET}")
        return

    new_engine = args[0]
    valid_ids = set(engines.keys())
    if new_engine not in valid_ids:
        available = ", ".join(sorted(valid_ids))
        print(f"{C_RED}Unknown engine: {new_engine}{C_RESET}", file=sys.stderr)
        print(f"{C_DIM}Available: {available}{C_RESET}", file=sys.stderr)
        sys.exit(1)

    if not _write_config_engine(new_engine):
        sys.exit(1)

    print(f"{C_GREEN}Engine set to:{C_RESET} {new_engine}")

    running, _ = _is_running()
    if running:
        print(f"{C_DIM}Restarting service...{C_RESET}")
        cmd_restart()
    else:
        print(f"{C_DIM}Service not running - start with: wh start{C_RESET}")


def cmd_replace(args: list):
    """Show, add, or remove text replacement rules."""
    config_file = _get_config_path()

    def _read_replacements() -> tuple:
        """Read replacements config. Returns (enabled, rules_dict)."""
        if not config_file.exists():
            return False, {}
        try:
            import tomllib
            with open(config_file, 'rb') as f:
                data = tomllib.load(f)
            repl = data.get('replacements', {})
            enabled = repl.get('enabled', False)
            rules = repl.get('rules', {})
            return enabled, {str(k): str(v) for k, v in rules.items()} if isinstance(rules, dict) else {}
        except Exception:
            return False, {}

    if not args:
        # wh replace — show current rules
        enabled, rules = _read_replacements()
        status = f"{C_GREEN}enabled{C_RESET}" if enabled else f"{C_DIM}disabled{C_RESET}"
        print(f"  {C_DIM}status:{C_RESET} {status}")
        print()
        if rules:
            print(f"  {C_BOLD}Rules:{C_RESET}")
            max_key = max(len(k) for k in rules)
            for spoken, replacement in sorted(rules.items()):
                print(f'    {C_CYAN}"{spoken}"{C_RESET}{" " * (max_key - len(spoken))}  →  {replacement}')
        else:
            print(f"  {C_DIM}No replacement rules defined.{C_RESET}")
            print(f"  {C_DIM}Add one: wh replace add \"spoken form\" \"replacement\"{C_RESET}")
        return

    subcmd = args[0]

    if subcmd == "add":
        if len(args) != 3:
            print(f"{C_RED}Usage: wh replace add \"spoken form\" \"replacement\"{C_RESET}", file=sys.stderr)
            sys.exit(1)
        spoken, replacement = args[1], args[2]
        try:
            from whisper_voice.config import add_replacement
            if add_replacement(spoken, replacement):
                print(f'{C_GREEN}Added:{C_RESET} "{spoken}" → {replacement}')
            else:
                print(f"{C_RED}Failed to write config{C_RESET}", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"{C_RED}Error: {e}{C_RESET}", file=sys.stderr)
            sys.exit(1)

    elif subcmd == "remove":
        if len(args) != 2:
            print(f"{C_RED}Usage: wh replace remove \"spoken form\"{C_RESET}", file=sys.stderr)
            sys.exit(1)
        spoken = args[1]
        try:
            from whisper_voice.config import remove_replacement
            if remove_replacement(spoken):
                print(f'{C_GREEN}Removed:{C_RESET} "{spoken}"')
            else:
                print(f'{C_YELLOW}Not found:{C_RESET} "{spoken}"')
                sys.exit(1)
        except Exception as e:
            print(f"{C_RED}Error: {e}{C_RESET}", file=sys.stderr)
            sys.exit(1)

    elif subcmd in ("on", "enable"):
        try:
            from whisper_voice.config import update_config_field
            update_config_field("replacements", "enabled", True)
            print(f"{C_GREEN}Replacements enabled{C_RESET}")
        except Exception as e:
            print(f"{C_RED}Error: {e}{C_RESET}", file=sys.stderr)
            sys.exit(1)

    elif subcmd in ("off", "disable"):
        try:
            from whisper_voice.config import update_config_field
            update_config_field("replacements", "enabled", False)
            print(f"{C_DIM}Replacements disabled{C_RESET}")
        except Exception as e:
            print(f"{C_RED}Error: {e}{C_RESET}", file=sys.stderr)
            sys.exit(1)

    else:
        print(f"{C_RED}Unknown subcommand: {subcmd}{C_RESET}", file=sys.stderr)
        print(f"{C_DIM}Usage: wh replace [add|remove|on|off]{C_RESET}", file=sys.stderr)
        sys.exit(1)


def _interactive_config() -> None:
    """Compact inline interactive config editor. No full-screen takeover."""
    import select as _select
    import termios
    import tty

    config_path = _get_config_path()
    if not config_path.exists():
        print(f"{C_YELLOW}Config not found: {config_path}{C_RESET}")
        return

    try:
        import tomllib
        with open(config_path, 'rb') as f:
            data = tomllib.load(f)
    except Exception as e:
        print(f"{C_RED}Error reading config: {e}{C_RESET}")
        return

    def _get(section, key, default):
        return data.get(section, {}).get(key, default)

    ITEMS = [
        {"type": "header",  "label": "Recording"},
        {"type": "choice",  "label": "Hotkey",          "section": "hotkey",        "key": "key",                    "value": _get("hotkey", "key", "alt_r"),                         "options": ["alt_r","alt_l","ctrl_r","ctrl_l","cmd_r","cmd_l","shift_r","shift_l","caps_lock"]},
        {"type": "float",   "label": "Double-tap",       "section": "hotkey",        "key": "double_tap_threshold",   "value": _get("hotkey", "double_tap_threshold", 0.4),            "hint": "sec"},
        {"type": "header",  "label": "Transcription"},
        {"type": "choice",  "label": "Engine",           "section": "transcription", "key": "engine",                 "value": _get("transcription", "engine", "qwen3_asr"),           "options": ["qwen3_asr", "whisperkit"]},
        {"type": "string",  "label": "Language",         "section": "qwen3_asr",     "key": "language",               "value": _get("qwen3_asr", "language", "auto"),                  "hint": "en  fa  auto"},
        {"type": "header",  "label": "Grammar"},
        {"type": "bool",    "label": "Enabled",          "section": "grammar",       "key": "enabled",                "value": _get("grammar", "enabled", False)},
        {"type": "choice",  "label": "Backend",          "section": "grammar",       "key": "backend",                "value": _get("grammar", "backend", "apple_intelligence"),       "options": ["apple_intelligence", "ollama", "lm_studio"]},
        {"type": "header",  "label": "Text to Speech"},
        {"type": "bool",    "label": "Enabled",          "section": "tts",           "key": "enabled",                "value": _get("tts", "enabled", True)},
        {"type": "string",  "label": "Voice",            "section": "kokoro_tts",    "key": "voice",                  "value": _get("kokoro_tts", "voice", "af_sky"),                  "hint": "af_sky  bf_emma  am_adam"},
        {"type": "string",  "label": "Shortcut",         "section": "tts",           "key": "speak_shortcut",         "value": _get("tts", "speak_shortcut", "alt+t")},
        {"type": "header",  "label": "UI"},
        {"type": "bool",    "label": "Auto-paste",       "section": "ui",            "key": "auto_paste",             "value": _get("ui", "auto_paste", False)},
        {"type": "bool",    "label": "Overlay",          "section": "ui",            "key": "show_overlay",           "value": _get("ui", "show_overlay", True)},
        {"type": "bool",    "label": "Sounds",           "section": "ui",            "key": "sounds_enabled",         "value": _get("ui", "sounds_enabled", True)},
        {"type": "bool",    "label": "Notifications",    "section": "ui",            "key": "notifications_enabled",  "value": _get("ui", "notifications_enabled", False)},
        {"type": "header",  "label": "Shortcuts"},
        {"type": "bool",    "label": "Enabled",          "section": "shortcuts",     "key": "enabled",                "value": _get("shortcuts", "enabled", True)},
        {"type": "header",  "label": "Replacements"},
        {"type": "bool",    "label": "Enabled",          "section": "replacements",  "key": "enabled",                "value": _get("replacements", "enabled", False)},
        {"type": "header",  "label": "Audio"},
        {"type": "bool",    "label": "VAD",              "section": "audio",         "key": "vad_enabled",            "value": _get("audio", "vad_enabled", True)},
        {"type": "bool",    "label": "Noise reduction",  "section": "audio",         "key": "noise_reduction",        "value": _get("audio", "noise_reduction", True)},
        {"type": "bool",    "label": "Normalize",        "section": "audio",         "key": "normalize_audio",        "value": _get("audio", "normalize_audio", True)},
        {"type": "float",   "label": "Pre-buffer",       "section": "audio",         "key": "pre_buffer",             "value": _get("audio", "pre_buffer", 0.0),                       "hint": "sec  0=off"},
    ]

    selectable = [i for i, it in enumerate(ITEMS) if it["type"] != "header"]
    cursor  = [0]   # index into selectable
    vtop    = [0]   # first ITEMS index shown in viewport
    last_n  = [0]   # lines printed in last render
    extra   = [0]   # extra lines below block left by inline edit prompt
    VLINES  = 14    # content rows visible in viewport
    LW      = 18    # label column width

    BD = "\033[1m"
    DM = "\033[2m"
    GN = "\033[92m"
    CY = "\033[96m"
    YL = "\033[93m"
    RD = "\033[91m"
    RS = "\033[0m"
    HIDE = "\033[?25l"
    SHOW = "\033[?25h"

    stdin_fd = sys.stdin.fileno()
    old_tty  = termios.tcgetattr(stdin_fd)

    def _fmt(item):
        v, t = item["value"], item["type"]
        if t == "bool":
            return f"{GN}● on{RS}" if v else f"{DM}○ off{RS}"
        hint = item.get("hint", "")
        s = f"{CY}{v}{RS}"
        return f"{s}  {DM}{hint}{RS}" if hint else s

    def _adjust_vtop():
        sel_abs = selectable[cursor[0]]
        if sel_abs < vtop[0]:
            vtop[0] = sel_abs
        elif sel_abs >= vtop[0] + VLINES:
            vtop[0] = max(0, sel_abs - VLINES + 1)

    def _render(msg="", msg_color=DM):
        _adjust_vtop()
        lines = []
        lines.append(f"  {BD}Config{RS}  {DM}{config_path}{RS}")

        visible   = ITEMS[vtop[0]: vtop[0] + VLINES]
        has_above = vtop[0] > 0
        has_below = vtop[0] + VLINES < len(ITEMS)

        for row_i, item in enumerate(visible):
            abs_i = vtop[0] + row_i
            if item["type"] == "header":
                lines.append(f"  {DM}{item['label']}{RS}")
                continue
            is_sel = (abs_i == selectable[cursor[0]])
            val_s  = _fmt(item)
            if is_sel:
                lines.append(f"  {GN}▶{RS}  {BD}{item['label']:<{LW}}{RS}  {val_s}")
            else:
                lines.append(f"     {DM}{item['label']:<{LW}}{RS}  {val_s}")

        # Scroll indicator — doubles as status message when one is present
        if msg:
            lines.append(f"  {msg_color}{msg}{RS}")
        elif has_above and has_below:
            lines.append(f"  {DM}↑ above   ↓ below{RS}")
        elif has_above:
            lines.append(f"  {DM}↑ above{RS}")
        elif has_below:
            lines.append(f"  {DM}↓ below{RS}")
        else:
            lines.append("")

        lines.append(f"  {DM}↑↓ navigate   space toggle   enter edit   q quit{RS}")

        n_up = last_n[0] + extra[0]
        if n_up:
            sys.stdout.write(f"\033[{n_up}A")
        extra[0] = 0
        sys.stdout.write("".join(f"\r\033[2K{ln}\n" for ln in lines))
        sys.stdout.flush()
        last_n[0] = len(lines)

    def _read_key():
        b = os.read(stdin_fd, 1)
        if not b:
            # EOF (stdin closed / terminal disconnected) — treat as quit
            return "\x04"
        if b == b"\x1b":
            r, _, _ = _select.select([stdin_fd], [], [], 0.15)
            if r:
                # Arrow keys are 3-byte CSI sequences: ESC [ X
                # Read exactly 2 more bytes to avoid consuming the next keypress.
                rest = os.read(stdin_fd, 2)
                if rest == b"[A":
                    return "up"
                if rest == b"[B":
                    return "down"
                return ""   # unrecognised escape sequence — ignore
            return "esc"
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            return ""

    def _save(item) -> bool:
        try:
            import fcntl as _fl

            from whisper_voice.config import _replace_in_section, _serialize_toml_value
            fd2 = os.open(str(config_path), os.O_RDWR | os.O_CREAT, 0o644)
            try:
                _fl.flock(fd2, _fl.LOCK_EX)
                content = config_path.read_text()
                content = _replace_in_section(
                    content, item["section"], item["key"],
                    _serialize_toml_value(item["value"])
                )
                config_path.write_text(content)
            finally:
                _fl.flock(fd2, _fl.LOCK_UN)
                os.close(fd2)
            return True
        except Exception:
            return False

    def _toggle() -> tuple:
        item = ITEMS[selectable[cursor[0]]]
        if item["type"] == "bool":
            item["value"] = not item["value"]
        elif item["type"] == "choice":
            opts = item["options"]
            idx = opts.index(item["value"]) if item["value"] in opts else -1
            item["value"] = opts[(idx + 1) % len(opts)]
        else:
            return ("", DM)
        ok = _save(item)
        return ("", DM) if ok else ("not saved", RD)

    def _edit() -> tuple:
        item = ITEMS[selectable[cursor[0]]]
        if item["type"] in ("bool", "choice"):
            return _toggle()

        prompt_text = f"  {item['label']} [{item['value']}]: "
        sys.stdout.write(f"{SHOW}\r\033[2K{BD}{prompt_text}{RS}")
        sys.stdout.flush()

        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_tty)
        try:
            new_raw = input()
        except (EOFError, KeyboardInterrupt):
            new_raw = ""
        finally:
            tty.setraw(stdin_fd)
            sys.stdout.write(HIDE)

        # Compute how many terminal lines the prompt + typed input occupied
        # so _render can move the cursor back to the right position.
        try:
            cols = os.get_terminal_size(stdin_fd).columns
        except OSError:
            cols = 80
        visible_len = len(prompt_text) + len(new_raw)
        extra[0] = max(1, (visible_len + cols - 1) // cols)

        v = new_raw.strip()
        if not v:
            return ("", DM)
        try:
            item["value"] = int(v)   if item["type"] == "int"   else \
                            float(v) if item["type"] == "float" else v
        except ValueError:
            return ("invalid value", YL)
        ok = _save(item)
        return ("saved", GN) if ok else ("not saved", RD)

    msg, msg_color = "", DM
    try:
        sys.stdout.write(HIDE)
        tty.setraw(stdin_fd)
        while True:
            _render(msg, msg_color)
            msg, msg_color = "", DM
            key = _read_key()
            if key in ("q", "Q", "\x03", "\x04", "esc"):
                break
            elif key == "up":
                cursor[0] = max(0, cursor[0] - 1)
            elif key == "down":
                cursor[0] = min(len(selectable) - 1, cursor[0] + 1)
            elif key == " ":
                msg, msg_color = _toggle()
            elif key in ("\r", "\n"):
                msg, msg_color = _edit()
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_tty)
        sys.stdout.write(f"{SHOW}\n")
        sys.stdout.flush()


def cmd_config(args: list):
    """Show, edit, or print path to config."""
    config_path = _get_config_path()

    if not args or args[0] == "show":
        if not sys.stdin.isatty():
            # Non-interactive: print static summary
            if not config_path.exists():
                print(f"{C_YELLOW}Config not found: {config_path}{C_RESET}")
                return
            try:
                import tomllib
                with open(config_path, 'rb') as f:
                    data = tomllib.load(f)
            except Exception as e:
                print(f"{C_RED}Error reading config: {e}{C_RESET}", file=sys.stderr)
                return
            engine = data.get("transcription", {}).get("engine", "qwen3_asr")
            language = data.get(engine, {}).get("language", "auto")
            def _on_off(v): return f"{C_GREEN}on{C_RESET}" if v else f"{C_DIM}off{C_RESET}"
            print()
            print(f"  {C_DIM}Engine{C_RESET}      {C_CYAN}{engine}{C_RESET}  {C_DIM}({language}){C_RESET}")
            print(f"  {C_DIM}Grammar{C_RESET}     {_on_off(data.get('grammar',{}).get('enabled',False))}  {C_DIM}{data.get('grammar',{}).get('backend','')}{C_RESET}")
            print(f"  {C_DIM}TTS{C_RESET}         {_on_off(data.get('tts',{}).get('enabled',True))}  {C_DIM}{data.get('kokoro_tts',{}).get('voice','af_sky')}{C_RESET}")
            print(f"  {C_DIM}Hotkey{C_RESET}      {data.get('hotkey',{}).get('key','alt_r').replace('_',' ')}")
            print()
            print(f"  {C_DIM}{config_path}{C_RESET}")
            print()
            return
        _interactive_config()
        return

    if args[0] == "edit":
        editor = os.environ.get("EDITOR", "open")
        if editor == "open":
            subprocess.run(["open", str(config_path)])
        else:
            os.execvp(editor, [editor, str(config_path)])
        return

    if args[0] == "path":
        print(config_path)
        return

    print(f"{C_RED}Unknown config subcommand: {args[0]}{C_RESET}", file=sys.stderr)
    print(f"{C_DIM}Usage: wh config [edit|path]{C_RESET}", file=sys.stderr)
    sys.exit(1)


def cmd_install():
    """Write LaunchAgent plist and load it."""
    wh_path = str(Path(sys.argv[0]).resolve())
    log_path = str(LOG_FILE)
    LAUNCHAGENT_PLIST.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Include Homebrew and common tool paths since launchd has a minimal PATH
    path_value = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHAGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{wh_path}</string>
        <string>_run</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{path_value}</string>
        <key>HF_HUB_CACHE</key>
        <string>{MODEL_DIR}</string>
        <key>HF_HUB_OFFLINE</key>
        <string>1</string>
        <key>HF_HUB_DISABLE_TELEMETRY</key>
        <string>1</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>
"""
    LAUNCHAGENT_PLIST.write_text(plist_content)
    print(f"{C_GREEN}Installed:{C_RESET} {LAUNCHAGENT_PLIST}")

    # Unload stale entry if any
    subprocess.run(["launchctl", "unload", str(LAUNCHAGENT_PLIST)], capture_output=True)

    # Stop any running instance first
    running, pid = _is_running()
    if running and pid:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
        except ProcessLookupError:
            pass
        _cleanup_lock()

    result = subprocess.run(
        ["launchctl", "load", str(LAUNCHAGENT_PLIST)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"{C_GREEN}LaunchAgent loaded{C_RESET} - service will start at login automatically")
        print(f"{C_GREEN}Starting now...{C_RESET}")
        time.sleep(1)
        running, pid = _is_running()
        if running:
            print(f"{C_GREEN}Running{C_RESET} (pid {pid})")
        else:
            print(f"{C_DIM}Service starting in background{C_RESET}")
    else:
        print(f"{C_YELLOW}LaunchAgent load warning: {result.stderr.strip()}{C_RESET}")
        print(f"{C_DIM}Try: launchctl load {LAUNCHAGENT_PLIST}{C_RESET}")

    print()
    print(f"{C_DIM}Accessibility permission will be requested automatically on first run.{C_RESET}")


def cmd_uninstall():
    """Completely remove Local Whisper: stop service, LaunchAgent, config, logs, zshrc alias."""
    print(f"  {C_BOLD}Uninstalling Local Whisper...{C_RESET}")
    print()

    # Stop running service
    running, pid = _is_running()
    if running and pid:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except ProcessLookupError:
            pass
    _cleanup_lock()
    subprocess.run(["pkill", "-9", "-f", "whisperkit-cli serve"], capture_output=True)
    print(f"  {C_GREEN}✓{C_RESET}  Service stopped")

    # Remove LaunchAgent (current + legacy)
    for plist in [
        LAUNCHAGENT_PLIST,
        Path.home() / "Library" / "LaunchAgents" / "info.gabrimatic.local-whisper.plist",
    ]:
        if plist.exists():
            subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
            plist.unlink()
    print(f"  {C_GREEN}✓{C_RESET}  LaunchAgent removed")

    # Remove old .app Login Item
    subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to delete (login items whose name is "Local Whisper")'],
        capture_output=True,
    )
    print(f"  {C_GREEN}✓{C_RESET}  Login Item removed")

    # Remove ~/.whisper (config, logs, backups, and models)
    whisper_dir = Path.home() / ".whisper"
    if whisper_dir.exists():
        shutil.rmtree(whisper_dir)
        print(f"  {C_GREEN}✓{C_RESET}  Removed ~/.whisper (including cached models)")

    # Remove wh alias from shell configs
    alias_pattern = re.compile(r"^\s*#\s*Local Whisper CLI\s*$|^\s*alias wh=.*local-whisper.*$")
    for rc in [Path.home() / ".zshrc", Path.home() / ".bashrc"]:
        if not rc.exists():
            continue
        lines = rc.read_text().splitlines(keepends=True)
        cleaned = [line for line in lines if not alias_pattern.match(line)]
        if len(cleaned) != len(lines):
            rc.write_text("".join(cleaned))
            print(f"  {C_GREEN}✓{C_RESET}  Removed wh alias from {rc.name}")

    print()
    print(f"  {C_BOLD}Done.{C_RESET} Local Whisper fully removed.")
    print(f"  {C_DIM}Project folder and venv not deleted - remove manually if needed.{C_RESET}")
    print(f"  {C_DIM}Open a new shell for alias removal to take effect.{C_RESET}")


def cmd_log():
    """Tail the service log."""
    if not LOG_FILE.exists():
        print(f"{C_YELLOW}Log not found: {LOG_FILE}{C_RESET}")
        print(f"{C_DIM}Start the service first: wh start{C_RESET}")
        return
    print(f"{C_DIM}Tailing {LOG_FILE} (Ctrl+C to stop){C_RESET}")
    print()
    try:
        subprocess.run(["tail", "-f", str(LOG_FILE)])
    except KeyboardInterrupt:
        print()


def cmd_version():
    """Show version."""
    try:
        from whisper_voice import __version__
        print(f"Local Whisper {__version__}")
    except Exception:
        print("Local Whisper (version unknown)")


# ---------------------------------------------------------------------------
# Command socket client (wh whisper / listen / transcribe)
# ---------------------------------------------------------------------------

CMD_SOCKET_PATH = str(Path.home() / ".whisper" / "cmd.sock")


def _cmd_connect():
    """Connect to the command socket. Raises on failure."""
    import socket as _socket
    sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    sock.connect(CMD_SOCKET_PATH)
    return sock


def _cmd_send_recv(request: dict) -> dict:
    """Send a command and wait for the final response. Returns the last message."""
    import json
    import socket as _socket

    running, _ = _is_running()
    if not running:
        print(f"{C_RED}Service not running.{C_RESET} Start with: wh start", file=sys.stderr)
        sys.exit(1)

    try:
        sock = _cmd_connect()
    except (FileNotFoundError, ConnectionRefusedError):
        print(f"{C_RED}Cannot connect to service.{C_RESET} Try: wh restart", file=sys.stderr)
        sys.exit(1)

    # Handle Ctrl+C: send stop and exit cleanly
    stop_sent = False

    def _on_interrupt(*_):
        nonlocal stop_sent
        if not stop_sent:
            stop_sent = True
            try:
                sock.sendall((json.dumps({"type": "stop"}) + "\n").encode())
            except Exception:
                pass

    original_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, _on_interrupt)

    try:
        data = (json.dumps(request) + "\n").encode()
        sock.sendall(data)

        # Read responses until we get a terminal one (done/error)
        buf = b""
        last_response = None
        sock.settimeout(300)  # 5 min max for long operations
        while True:
            try:
                chunk = sock.recv(4096)
            except _socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except Exception:
                    continue
                last_response = msg
                msg_type = msg.get("type")
                if msg_type in ("done", "error"):
                    return msg
                # "started" messages: continue waiting
                if msg_type == "started":
                    action = msg.get("action", "")
                    if action == "listen":
                        print("Recording... (Ctrl+C to stop)", file=sys.stderr)

        return last_response or {"type": "error", "message": "Connection closed unexpectedly"}
    finally:
        signal.signal(signal.SIGINT, original_sigint)
        try:
            sock.close()
        except Exception:
            pass


def cmd_whisper(args: list):
    """Speak text aloud via TTS."""
    voice = None
    text_parts = []
    i = 0
    while i < len(args):
        if args[i] == "--voice" and i + 1 < len(args):
            voice = args[i + 1]
            i += 2
        else:
            text_parts.append(args[i])
            i += 1

    text = " ".join(text_parts)

    # Read from stdin if no text provided and stdin is piped
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()

    if not text:
        print(f"{C_RED}No text provided.{C_RESET}", file=sys.stderr)
        print(f"{C_DIM}Usage: wh whisper \"text\" [--voice NAME]{C_RESET}", file=sys.stderr)
        sys.exit(1)

    request = {"type": "whisper", "text": text}
    if voice:
        request["voice"] = voice

    result = _cmd_send_recv(request)
    if result.get("type") == "error":
        print(f"{C_RED}{result.get('message', 'Unknown error')}{C_RESET}", file=sys.stderr)
        sys.exit(1)


def cmd_listen(args: list):
    """Record from microphone and output transcription."""
    max_duration = 0
    raw = False
    for arg in args:
        if arg == "--raw":
            raw = True
        else:
            try:
                max_duration = int(arg)
            except ValueError:
                print(f"{C_RED}Invalid argument: {arg}{C_RESET}", file=sys.stderr)
                print(f"{C_DIM}Usage: wh listen [seconds] [--raw]{C_RESET}", file=sys.stderr)
                sys.exit(1)

    request = {"type": "listen", "max_duration": max_duration, "raw": raw}
    result = _cmd_send_recv(request)

    if result.get("type") == "error":
        print(f"{C_RED}{result.get('message', 'Unknown error')}{C_RESET}", file=sys.stderr)
        sys.exit(1)
    elif result.get("type") == "done":
        text = result.get("text", "")
        if text:
            print(text)


def cmd_transcribe(args: list):
    """Transcribe an audio file."""
    raw = False
    file_path = None
    for arg in args:
        if arg == "--raw":
            raw = True
        elif file_path is None:
            file_path = arg
        else:
            print(f"{C_RED}Unexpected argument: {arg}{C_RESET}", file=sys.stderr)
            sys.exit(1)

    if not file_path:
        print(f"{C_RED}No file provided.{C_RESET}", file=sys.stderr)
        print(f"{C_DIM}Usage: wh transcribe <file> [--raw]{C_RESET}", file=sys.stderr)
        sys.exit(1)

    # Resolve to absolute path
    file_path = str(Path(file_path).resolve())

    request = {"type": "transcribe", "path": file_path, "raw": raw}
    result = _cmd_send_recv(request)

    if result.get("type") == "error":
        print(f"{C_RED}{result.get('message', 'Unknown error')}{C_RESET}", file=sys.stderr)
        sys.exit(1)
    elif result.get("type") == "done":
        text = result.get("text", "")
        if text:
            print(text)


def _print_help():
    """Print grouped help listing."""
    groups = [
        ("Service", [
            ("wh start",           "Launch the service"),
            ("wh stop",            "Stop the service"),
            ("wh restart",         "Restart (rebuilds UI if sources changed)"),
            ("wh log",             "Tail service log"),
        ]),
        ("Voice", [
            ("wh whisper \"text\"",  "Speak text aloud via Kokoro TTS"),
            ("wh listen [secs]",   "Record from mic, output transcription"),
            ("wh transcribe <file>", "Transcribe an audio file"),
        ]),
        ("Settings", [
            ("wh engine [name]",   "Show or switch transcription engine"),
            ("wh backend [name]",  "Show or switch grammar backend"),
            ("wh replace",         "Manage text replacement rules"),
            ("wh config [edit]",   "Interactive config editor, or open in $EDITOR"),
        ]),
        ("Maintenance", [
            ("wh update",          "Pull, update deps, rebuild, restart"),
            ("wh doctor [--fix]",  "Check system health, auto-repair"),
            ("wh build",           "Rebuild Swift UI"),
            ("wh uninstall",       "Completely remove Local Whisper"),
        ]),
    ]
    width = max(len(c) for _, cmds in groups for c, _ in cmds)
    for group_name, cmds in groups:
        print(f"  {C_BOLD}{group_name}{C_RESET}")
        for cmd, desc in cmds:
            print(f"    {C_CYAN}{cmd:<{width}}{C_RESET}  {C_DIM}{desc}{C_RESET}")
        print()


def _get_venv_python() -> Optional[str]:
    """Return the venv python path, same approach used across cli.py."""
    project_root = Path(__file__).resolve().parents[2]
    for candidate in [
        project_root / ".venv" / "bin" / "python",
        project_root / "venv" / "bin" / "python",
    ]:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def cmd_update():
    """Pull latest code, update dependencies, check model, rebuild Swift, and restart."""
    project_root = Path(__file__).resolve().parents[2]
    python = _get_venv_python()

    # Step 1: git pull
    print(f"\n  {C_BOLD}1/5  Pulling latest code...{C_RESET}")
    git = shutil.which("git")
    if git:
        result = subprocess.run(
            [git, "-C", str(project_root), "pull"],
        )
        if result.returncode != 0:
            print(f"{C_YELLOW}  git pull failed or not a git repo - continuing{C_RESET}")
        else:
            print(f"  {C_GREEN}Done{C_RESET}")
    else:
        print(f"  {C_YELLOW}git not found - skipping{C_RESET}")

    # Step 2: pip install -e . --upgrade
    print(f"\n  {C_BOLD}2/5  Updating Python dependencies...{C_RESET}")
    result = subprocess.run(
        [python, "-m", "pip", "install", "-e", str(project_root), "--upgrade", "--upgrade-strategy", "eager"],
    )
    if result.returncode != 0:
        print(f"{C_RED}  pip install failed{C_RESET}", file=sys.stderr)
    else:
        print(f"  {C_GREEN}Done{C_RESET}")

    # Step 3: check for model updates (HF_HUB_OFFLINE=0 so HF can be reached)
    print(f"\n  {C_BOLD}3/5  Checking models...{C_RESET}")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_env = os.environ.copy()
    model_env["HF_HUB_OFFLINE"] = "0"
    model_env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    model_env["HF_HUB_CACHE"] = str(MODEL_DIR)
    result = subprocess.run(
        [
            python, "-c",
            "from qwen3_asr_mlx import Qwen3ASR; "
            "Qwen3ASR.from_pretrained('mlx-community/Qwen3-ASR-1.7B-bf16'); "
            "print('Qwen3-ASR up to date.')",
        ],
        env=model_env,
    )
    if result.returncode != 0:
        print(f"{C_YELLOW}  Qwen3-ASR model check failed - skipping{C_RESET}")

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

    # Step 4: rebuild LocalWhisperUI if sources newer than binary
    print(f"\n  {C_BOLD}4/5  Rebuilding LocalWhisperUI if needed...{C_RESET}")
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
    cmd_restart()
    print(f"\n  {C_GREEN}{C_BOLD}Update complete.{C_RESET}")


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

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


def cmd_doctor(args: list):
    """Check system health and optionally fix issues."""
    fix = "--fix" in args
    core_ok = True
    project_root = Path(__file__).resolve().parents[2]
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

    # 2. Virtual environment
    venv_dir = project_root / ".venv"
    if venv_dir.is_dir():
        _doctor_pass("Virtual environment")
    else:
        _doctor_fail("Virtual environment not found", f"Run: python3 -m venv {venv_dir}")
        core_ok = False

    # 3. Core Python packages
    missing_pkgs = []
    for pkg in ["sounddevice", "numpy", "pynput", "qwen3_asr_mlx", "kokoro_mlx",
                "requests", "soundfile", "misaki"]:
        try:
            __import__(pkg)
        except ImportError:
            missing_pkgs.append(pkg)
    if not missing_pkgs:
        _doctor_pass("Core Python packages")
    else:
        hint = "Run: wh doctor --fix" if not fix else ""
        _doctor_fail(f"Missing packages: {', '.join(missing_pkgs)}", hint)
        if fix:
            macos_major = _get_macos_major()
            extras = "[apple-intelligence]" if macos_major and macos_major >= 26 else ""
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
        else:
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

    # 5. spaCy model
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

    # 6. Qwen3-ASR model
    qwen_model_dir = MODEL_DIR / "models--mlx-community--Qwen3-ASR-1.7B-bf16"
    if qwen_model_dir.is_dir():
        _doctor_pass("Qwen3-ASR model")
    else:
        hint = "Run: wh doctor --fix" if not fix else ""
        _doctor_fail("Qwen3-ASR model not found", hint)
        if fix:
            _doctor_fixing("Downloading Qwen3-ASR model...")
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            model_env = os.environ.copy()
            model_env["HF_HUB_CACHE"] = str(MODEL_DIR)
            model_env["HF_HUB_DISABLE_TELEMETRY"] = "1"
            model_env["HF_HUB_OFFLINE"] = "0"
            result = subprocess.run(
                [python, "-c",
                 "from qwen3_asr_mlx import Qwen3ASR; "
                 "Qwen3ASR.from_pretrained('mlx-community/Qwen3-ASR-1.7B-bf16')"],
                env=model_env, capture_output=True, timeout=300,
            )
            if result.returncode == 0:
                _doctor_pass("Qwen3-ASR model downloaded")
            else:
                _doctor_fail("Qwen3-ASR model download failed")
                core_ok = False
        else:
            core_ok = False

    # 7. Kokoro TTS model
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
    ui_app = Path.home() / ".whisper" / "LocalWhisperUI.app"
    if ui_app.is_dir():
        _doctor_pass("LocalWhisperUI.app")
    else:
        _doctor_warn("LocalWhisperUI.app not found", "Service will run headless without it")
        if fix:
            _doctor_fixing("Building Swift UI...")
            cmd_build()
            if ui_app.is_dir():
                _doctor_pass("LocalWhisperUI.app built")
            else:
                _doctor_warn("Swift UI build failed (service works without it)")

    # 10. LaunchAgent
    if LAUNCHAGENT_PLIST.exists():
        result = subprocess.run(
            ["launchctl", "list", LAUNCHAGENT_LABEL],
            capture_output=True,
        )
        if result.returncode == 0:
            _doctor_pass("LaunchAgent installed and loaded")
        else:
            hint = f"Run: launchctl load {LAUNCHAGENT_PLIST}" if not fix else ""
            _doctor_warn("LaunchAgent plist exists but not loaded", hint)
            if fix:
                _doctor_fixing("launchctl load")
                subprocess.run(["launchctl", "load", str(LAUNCHAGENT_PLIST)], capture_output=True)
                _doctor_pass("LaunchAgent loaded")
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
            cmd_restart()
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
        _doctor_info("Apple Intelligence SDK not installed (optional, macOS 26+)")

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


def cmd_default():
    """Default: status + help."""
    running, pid = _is_running()
    backend = _read_config_backend() or "unknown"
    engine = _read_config_engine() or "unknown"
    config_path = _get_config_path()

    print()
    print(f"  {C_BOLD}╭────────────────────────────────────────╮{C_RESET}")
    print(f"  {C_BOLD}│{C_RESET}  {C_CYAN}Local Whisper{C_RESET} · CLI Controller        {C_BOLD}│{C_RESET}")
    print(f"  {C_BOLD}╰────────────────────────────────────────╯{C_RESET}")
    print()

    if running:
        pid_str = str(pid) if pid else "unknown"
        print(f"  Status:  {C_GREEN}{C_BOLD}Running{C_RESET}  {C_DIM}pid {pid_str}{C_RESET}")
    else:
        print(f"  Status:  {C_DIM}Stopped{C_RESET}")

    print(f"  Engine:  {C_CYAN}{engine}{C_RESET}")
    print(f"  Backend: {C_CYAN}{backend}{C_RESET}")
    print(f"  Config:  {C_DIM}{config_path}{C_RESET}")
    print()

    _print_help()


def cli_main():
    """Entry point for the wh CLI."""
    args = sys.argv[1:]

    if not args:
        cmd_default()
        return

    cmd = args[0]
    rest = args[1:]

    if cmd == "status":
        cmd_status()
    elif cmd == "start":
        cmd_start()
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "restart":
        cmd_restart()
    elif cmd == "build":
        cmd_build()
    elif cmd == "whisper":
        cmd_whisper(rest)
    elif cmd == "listen":
        cmd_listen(rest)
    elif cmd == "transcribe":
        cmd_transcribe(rest)
    elif cmd == "backend":
        cmd_backend(rest)
    elif cmd == "engine":
        cmd_engine(rest)
    elif cmd == "replace":
        cmd_replace(rest)
    elif cmd == "config":
        cmd_config(rest)
    elif cmd == "update":
        cmd_update()
    elif cmd == "doctor":
        cmd_doctor(rest)
    elif cmd == "uninstall":
        cmd_uninstall()
    elif cmd == "log":
        cmd_log()
    elif cmd == "version":
        cmd_version()
    elif cmd == "_run":
        from whisper_voice.app import service_main
        service_main()
    elif cmd in ("-h", "--help", "help"):
        _print_help()
    else:
        print(f"{C_RED}Unknown command: {cmd}{C_RESET}", file=sys.stderr)
        print(f"{C_DIM}Run 'wh' for usage.{C_RESET}", file=sys.stderr)
        sys.exit(1)

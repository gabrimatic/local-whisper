# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Main dispatcher and top-level commands."""

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from .build import cmd_build, cmd_restart
from .client import cmd_listen, cmd_transcribe, cmd_whisper
from .constants import (
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_GREEN,
    C_RED,
    C_RESET,
    C_YELLOW,
    INSTALL_BREW,
    LAUNCHAGENT_PLIST,
    LOG_FILE,
    get_install_method,
)
from .doctor import _update_models, cmd_doctor, cmd_update
from .editor import cmd_config
from .history import cmd_export, cmd_stats
from .lifecycle import (
    _cleanup_lock,
    _get_config_path,
    _is_running,
    _read_config_backend_status,
    _read_config_engine,
    cmd_start,
    cmd_status,
    cmd_stop,
)
from .settings import cmd_backend, cmd_engine, cmd_replace


def _print_help():
    """Print grouped help listing."""
    groups = [
        ("Service", [
            ("wh status",          "Running? PID, engine, backend, config path"),
            ("wh start",           "Launch the service"),
            ("wh stop",            "Stop the service"),
            ("wh restart",         "Restart (rebuilds UI if sources changed)"),
            ("wh log",             "Tail service log"),
        ]),
        ("Voice", [
            ("wh whisper \"text\" [--voice N]", "Speak text aloud via Kokoro TTS (accepts stdin)"),
            ("wh listen [secs] [--raw]", "Record from mic, output transcription (0 = until Ctrl+C)"),
            ("wh transcribe <file> [--raw]", "Transcribe an audio file"),
        ]),
        ("Settings", [
            ("wh engine [name]",   "Show or switch transcription engine"),
            ("wh backend [name]",  "Show or switch grammar backend"),
            ("wh replace [add|remove|on|off|import FILE]", "Manage replacement rules"),
            ("wh config [show|edit|path]", "Interactive config editor, open in $EDITOR, or print path"),
        ]),
        ("History", [
            ("wh stats",           "Show usage statistics"),
            ("wh export [opts]",   "Export transcription history (md/txt/json)"),
        ]),
        ("Maintenance", [
            ("wh setup",           "Finish first-time setup (models, permissions, service)"),
            ("wh install",         "Alias for wh setup"),
            ("wh version",         "Show version and install method"),
            ("wh update",          "Update code, deps, models, and restart"),
            ("wh doctor [--fix|--report [PATH]]", "Check system health, auto-repair, or write report"),
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


def cmd_version():
    """Show version and install method."""
    try:
        from whisper_voice import __version__
        method = get_install_method()
        print(f"Local Whisper {__version__} ({method})")
    except Exception:
        print("Local Whisper (version unknown)")


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


def cmd_install():
    """Run the full setup script (deps, venv, models, service, permissions)."""
    if get_install_method() == INSTALL_BREW:
        _run_homebrew_setup()
        return

    project_root = Path(__file__).resolve().parents[3]
    setup_script = project_root / "setup.sh"

    if not setup_script.exists():
        print(f"{C_RED}This install does not include setup.sh.{C_RESET}")
        print(f"{C_DIM}Install with Homebrew for the guided setup path:{C_RESET}")
        print(f"{C_BOLD}  brew install gabrimatic/local-whisper/local-whisper{C_RESET}")
        print(f"{C_BOLD}  wh setup{C_RESET}")
        sys.exit(1)

    os.execvp("bash", ["bash", str(setup_script)])


def _run_homebrew_setup():
    """Guided first-time setup for Homebrew installs."""
    print()
    print(f"  {C_BOLD}╭────────────────────────────────────────╮{C_RESET}")
    print(f"  {C_BOLD}│{C_RESET}  {C_CYAN}Local Whisper{C_RESET} · First-time setup     {C_BOLD}│{C_RESET}")
    print(f"  {C_BOLD}╰────────────────────────────────────────╯{C_RESET}")
    print()
    print(f"  {C_DIM}This downloads the default local model, checks permissions,")
    print(f"  and starts Local Whisper in the background.{C_RESET}")
    print()

    print(f"  {C_BOLD}1/4  Preparing config{C_RESET}")
    _ensure_config()

    print()
    print(f"  {C_BOLD}2/4  Getting the local speech model ready{C_RESET}")
    _update_models()

    print()
    print(f"  {C_BOLD}3/4  Checking macOS permissions{C_RESET}")
    permissions_ok = _request_permissions()

    print()
    print(f"  {C_BOLD}4/4  Starting Local Whisper{C_RESET}")
    cmd_start()

    print()
    if permissions_ok:
        print(f"  {C_GREEN}{C_BOLD}Setup complete.{C_RESET}")
    else:
        print(f"  {C_YELLOW}{C_BOLD}Setup complete, permissions still need attention.{C_RESET}")
        print(f"  {C_DIM}Grant the missing permission in System Settings, then run: wh restart{C_RESET}")
    print()
    print(f"  Try it: {C_BOLD}double-tap Right Option, speak, tap again to stop.{C_RESET}")
    print(f"  Check health anytime: {C_BOLD}wh doctor{C_RESET}")
    print()


def _ensure_config():
    config_dir = Path.home() / ".whisper"
    config_path = config_dir / "config.toml"
    config_dir.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        print(f"  {C_GREEN}✓{C_RESET}  Config already exists")
        return

    from whisper_voice.config import DEFAULT_CONFIG
    config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    print(f"  {C_GREEN}✓{C_RESET}  Config created at ~/.whisper/config.toml")


def _request_permissions() -> bool:
    try:
        from whisper_voice.utils import (
            check_accessibility_trusted,
            check_microphone_permission,
            request_accessibility_permission,
        )
    except Exception as exc:
        print(f"  {C_YELLOW}⚠{C_RESET}  Could not load permission checks: {exc}")
        return False

    ax_ok = check_accessibility_trusted()
    if not ax_ok:
        request_accessibility_permission()

    mic_ok, _ = check_microphone_permission()

    if ax_ok:
        print(f"  {C_GREEN}✓{C_RESET}  Accessibility")
    else:
        print(f"  {C_YELLOW}⚠{C_RESET}  Accessibility is not granted yet")

    if mic_ok:
        print(f"  {C_GREEN}✓{C_RESET}  Microphone")
    else:
        print(f"  {C_YELLOW}⚠{C_RESET}  Microphone is not granted yet")

    if ax_ok and mic_ok:
        return True

    print()
    print(f"  {C_DIM}macOS may list Local Whisper as \"Python\" because the background")
    print(f"  service runs through the packaged Python runtime.{C_RESET}")
    if not ax_ok:
        print(f"  {C_DIM}Accessibility: System Settings -> Privacy & Security -> Accessibility{C_RESET}")
    if not mic_ok:
        print(f"  {C_DIM}Microphone: System Settings -> Privacy & Security -> Microphone{C_RESET}")

    if not sys.stdin.isatty():
        return False

    for _ in range(3):
        print()
        try:
            input("  Press Enter after granting permissions, or Ctrl+C to continue later... ")
        except KeyboardInterrupt:
            print()
            return False

        ax_ok = check_accessibility_trusted()
        mic_ok, _ = check_microphone_permission()
        if ax_ok and mic_ok:
            print(f"  {C_GREEN}✓{C_RESET}  All permissions granted")
            return True
        if not ax_ok:
            print(f"  {C_YELLOW}⚠{C_RESET}  Accessibility still needs to be enabled")
        if not mic_ok:
            print(f"  {C_YELLOW}⚠{C_RESET}  Microphone still needs to be enabled")

    return ax_ok and mic_ok


def cmd_uninstall():
    """Completely remove Local Whisper: stop service, LaunchAgent, config, logs, zshrc alias."""
    is_brew = get_install_method() == INSTALL_BREW

    if is_brew:
        print(f"  {C_BOLD}Uninstalling Local Whisper (Homebrew)...{C_RESET}")
        print()
        subprocess.run(["brew", "services", "stop", "local-whisper"], capture_output=True)
        print(f"  {C_GREEN}✓{C_RESET}  Service stopped")

        whisper_dir = Path.home() / ".whisper"
        if whisper_dir.exists():
            shutil.rmtree(whisper_dir)
            print(f"  {C_GREEN}✓{C_RESET}  Removed ~/.whisper (config, models, logs)")

        print()
        print(f"  Now run: {C_BOLD}brew uninstall local-whisper{C_RESET}")
        print(f"  {C_DIM}Optionally: brew untap gabrimatic/local-whisper{C_RESET}")
        return

    print(f"  {C_BOLD}Uninstalling Local Whisper...{C_RESET}")
    print()

    # Stop running service. Wait briefly for graceful exit before escalating.
    running, pid = _is_running()
    if running and pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        for _ in range(20):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        else:
            try:
                os.kill(pid, signal.SIGKILL)
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
    # Surface the source-install venv path explicitly so users know what to clean up.
    project_root = Path(__file__).resolve().parents[3]
    venv_dir = project_root / ".venv"
    if venv_dir.exists():
        print(f"  {C_DIM}Source-install venv preserved at {venv_dir}.{C_RESET}")
        print(f"  {C_DIM}To remove it: rm -rf {venv_dir}{C_RESET}")
    print(f"  {C_DIM}Open a new shell for alias removal to take effect.{C_RESET}")


def cmd_default():
    """Default: status + help."""
    running, pid = _is_running()
    backend = _read_config_backend_status() or "unknown"
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
    elif cmd == "export":
        cmd_export(rest)
    elif cmd == "stats":
        cmd_stats(rest)
    elif cmd in ("setup", "install"):
        cmd_install()
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

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
    LAUNCHAGENT_LABEL,
    LAUNCHAGENT_PLIST,
    LOG_FILE,
    MODEL_DIR,
)
from .doctor import cmd_doctor, cmd_update
from .editor import cmd_config
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
            ("wh whisper \"text\"",  "Speak text aloud via Kokoro TTS"),
            ("wh listen [secs]",   "Record from mic, output transcription"),
            ("wh transcribe <file>", "Transcribe an audio file"),
        ]),
        ("Settings", [
            ("wh engine [name]",   "Show or switch transcription engine"),
            ("wh backend [name]",  "Show or switch grammar backend"),
            ("wh replace",         "Manage text replacement rules"),
            ("wh config [edit|path]", "Interactive config editor, open in $EDITOR, or print path"),
        ]),
        ("Maintenance", [
            ("wh version",         "Show version"),
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


def cmd_version():
    """Show version."""
    try:
        from whisper_voice import __version__
        print(f"Local Whisper {__version__}")
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

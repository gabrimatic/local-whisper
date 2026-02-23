# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
CLI service controller for Local Whisper.

Usage:
    wh                  Status + help (default)
    wh status           Running? PID, backend, config path
    wh start            Launch the service
    wh stop             Graceful kill (SIGTERM -> SIGKILL)
    wh restart          Stop + start
    wh backend          Show current + list available
    wh backend <name>   Switch backend in config, restart service
    wh config           Print key config values
    wh config edit      Open config.toml in $EDITOR
    wh config path      Print path to config file
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
        content = config_file.read_text()
        new_content = _replace_in_section(content, "grammar", "backend", new_backend)
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


def cmd_status():
    """Show service status."""
    running, pid = _is_running()
    backend = _read_config_backend() or "unknown"
    config_path = _get_config_path()

    if running:
        pid_str = str(pid) if pid else "unknown"
        print(f"  {C_GREEN}{C_BOLD}Running{C_RESET}  pid {C_DIM}{pid_str}{C_RESET}")
    else:
        print(f"  {C_DIM}Stopped{C_RESET}")

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


def _swift_cli_dir() -> Path:
    """Return the Apple Intelligence Swift CLI source directory."""
    return Path(__file__).parent / "backends" / "apple_intelligence" / "cli"


def _swift_cli_binary() -> Path:
    """Return the expected path of the compiled apple-ai-cli binary."""
    return _swift_cli_dir() / ".build" / "release" / "apple-ai-cli"


def _swift_sources_newer_than_binary() -> bool:
    """Return True if any Swift source is newer than the compiled binary."""
    binary = _swift_cli_binary()
    if not binary.exists():
        return True
    binary_mtime = binary.stat().st_mtime
    sources_dir = _swift_cli_dir() / "Sources"
    if not sources_dir.exists():
        return False
    for src in sources_dir.rglob("*.swift"):
        if src.stat().st_mtime > binary_mtime:
            return True
    return False


def cmd_build():
    """Build the Apple Intelligence Swift CLI."""
    cli_dir = _swift_cli_dir()
    if not cli_dir.exists():
        print(f"{C_RED}Swift CLI directory not found: {cli_dir}{C_RESET}", file=sys.stderr)
        sys.exit(1)

    swift = shutil.which("swift")
    if not swift:
        print(f"{C_RED}swift not found - install Xcode or Xcode Command Line Tools{C_RESET}", file=sys.stderr)
        sys.exit(1)

    print(f"{C_DIM}Building Apple Intelligence CLI...{C_RESET}")
    result = subprocess.run(
        [swift, "build", "-c", "release"],
        cwd=str(cli_dir),
    )
    if result.returncode != 0:
        print(f"{C_RED}Build failed{C_RESET}", file=sys.stderr)
        sys.exit(result.returncode)
    print(f"{C_GREEN}Build successful{C_RESET}")


def cmd_restart(rebuild: bool = False):
    """Stop then start, optionally rebuilding the Swift CLI first."""
    if rebuild or _swift_sources_newer_than_binary():
        if not rebuild:
            print(f"{C_YELLOW}Swift sources changed - rebuilding...{C_RESET}")
        cmd_build()
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


def cmd_config(args: list):
    """Show, edit, or print path to config."""
    config_path = _get_config_path()

    if not args or args[0] == "show":
        # Print key values
        if not config_path.exists():
            print(f"{C_YELLOW}Config not found: {config_path}{C_RESET}")
            return

        try:
            content = config_path.read_text()
            print(f"  {C_DIM}path:{C_RESET}    {config_path}")
            print()
            # Show relevant lines
            in_section = None
            show_sections = {"grammar", "whisper", "audio", "hotkey", "shortcuts"}
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("[") and stripped.endswith("]"):
                    section = stripped[1:-1]
                    in_section = section if section in show_sections else None
                    if in_section:
                        print(f"  {C_BOLD}{line}{C_RESET}")
                    continue
                if in_section and stripped and not stripped.startswith("#"):
                    print(f"  {line}")
        except Exception as e:
            print(f"{C_RED}Error reading config: {e}{C_RESET}", file=sys.stderr)
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
    subprocess.run(["pkill", "-9", "-f", "apple-ai-cli serve"], capture_output=True)
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

    # Remove ~/.whisper (config, logs, backups)
    whisper_dir = Path.home() / ".whisper"
    if whisper_dir.exists():
        shutil.rmtree(whisper_dir)
        print(f"  {C_GREEN}✓{C_RESET}  Removed ~/.whisper")

    # Remove wh alias from shell configs
    alias_pattern = re.compile(r"^\s*#\s*Local Whisper CLI\s*$|^\s*alias wh=.*local-whisper.*$")
    for rc in [Path.home() / ".zshrc", Path.home() / ".bashrc"]:
        if not rc.exists():
            continue
        lines = rc.read_text().splitlines(keepends=True)
        cleaned = [l for l in lines if not alias_pattern.match(l)]
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


def _print_help():
    """Print help listing."""
    print(f"  {C_BOLD}Commands:{C_RESET}")
    print()
    cmds = [
        ("wh",               "Status + help (this output)"),
        ("wh status",        "Service status, PID, backend"),
        ("wh start",         "Launch the service"),
        ("wh stop",          "Stop the service"),
        ("wh restart",       "Restart (auto-rebuilds Swift CLI if sources changed)"),
        ("wh build",         "Rebuild the Apple Intelligence Swift CLI"),
        ("wh backend",       "Show current backend + list available"),
        ("wh backend <name>","Switch grammar backend (restarts if running)"),
        ("wh config",        "Show key config values"),
        ("wh config edit",   "Open config in $EDITOR"),
        ("wh config path",   "Print path to config file"),
        ("wh uninstall",     "Completely remove Local Whisper (service, config, alias)"),
        ("wh log",           "Tail service log"),
        ("wh version",       "Show version"),
    ]
    width = max(len(c) for c, _ in cmds)
    for cmd, desc in cmds:
        print(f"    {C_CYAN}{cmd:<{width}}{C_RESET}  {C_DIM}{desc}{C_RESET}")
    print()


def cmd_default():
    """Default: status + help."""
    running, pid = _is_running()
    backend = _read_config_backend() or "unknown"
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
    elif cmd == "backend":
        cmd_backend(rest)
    elif cmd == "config":
        cmd_config(rest)
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

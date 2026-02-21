"""
CLI service controller for Local Whisper.

Usage:
    wh                  Status + help (default)
    wh status           Running? PID, backend, config path
    wh start            Launch the .app bundle
    wh stop             Graceful kill (SIGTERM -> SIGKILL)
    wh restart          Stop + start
    wh backend          Show current + list available
    wh backend <name>   Switch backend in config, restart service
    wh config           Print key config values
    wh config edit      Open config.toml in $EDITOR
    wh config path      Print path to config file
    wh install          Install .app to /Applications + Login Item
    wh uninstall        Remove Login Item
    wh log              Tail ~/.whisper/service.log
    wh version          Show version
"""

import fcntl
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# Color constants
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"

LOCK_FILE = "/tmp/local-whisper.lock"
APP_BUNDLE = "/Applications/Local Whisper.app"
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
    for pattern in ["Local Whisper", "whisper_voice", "/bin/wh"]:
        try:
            flag = "-x" if pattern == "Local Whisper" else "-f"
            result = subprocess.run(
                ["pgrep", flag, pattern],
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


def _find_in_section(content: str, section: str, key: str) -> Optional[str]:
    """Find a key's value within a specific TOML section. Returns the value or None."""
    in_section = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == f"[{section}]"
            continue
        if in_section:
            m = re.match(rf'{key}\s*=\s*"([^"]*)"', stripped)
            if m:
                return m.group(1)
            # Also match unquoted booleans
            m = re.match(rf'{key}\s*=\s*(true|false)', stripped)
            if m:
                return m.group(1)
    return None


def _replace_in_section(content: str, section: str, key: str, new_value: str) -> str:
    """Replace a key's value within a specific TOML section."""
    lines = content.splitlines(keepends=True)
    in_section = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == f"[{section}]"
            continue
        if in_section:
            # Match quoted value
            new_line = re.sub(
                rf'({key}\s*=\s*)"[^"]*"',
                f'\\1"{new_value}"',
                line
            )
            if new_line != line:
                lines[i] = new_line
                return "".join(lines)
            # Match unquoted boolean
            new_line = re.sub(
                rf'({key}\s*=\s*)(true|false)',
                f'\\1{new_value}',
                line
            )
            if new_line != line:
                lines[i] = new_line
                return "".join(lines)
    return content


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
    """Launch the .app bundle."""
    running, pid = _is_running()
    if running:
        pid_str = str(pid) if pid else "unknown"
        print(f"{C_YELLOW}Already running (pid {pid_str}){C_RESET}")
        return

    if not os.path.exists(APP_BUNDLE):
        print(f"{C_RED}App bundle not found: {APP_BUNDLE}{C_RESET}", file=sys.stderr)
        print(f"{C_DIM}Run ./scripts/build_app.sh && ./scripts/install_app.sh first.{C_RESET}", file=sys.stderr)
        sys.exit(1)

    subprocess.Popen(["open", APP_BUNDLE])
    print(f"{C_GREEN}Started{C_RESET} {APP_BUNDLE}")


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


def cmd_restart():
    """Stop then start."""
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
    """Install .app to /Applications and set as Login Item."""
    dist_app = Path(__file__).parents[3] / "dist" / "Local Whisper.app"

    if not dist_app.exists():
        print(f"{C_RED}Built app not found: {dist_app}{C_RESET}", file=sys.stderr)
        print(f"{C_DIM}Run ./scripts/build_app.sh first.{C_RESET}", file=sys.stderr)
        sys.exit(1)

    # Remove existing bundle before copying to avoid merging
    if os.path.exists(APP_BUNDLE):
        subprocess.run(["rm", "-rf", APP_BUNDLE], capture_output=True)

    print(f"{C_DIM}Copying to /Applications...{C_RESET}")
    result = subprocess.run(
        ["cp", "-R", str(dist_app), "/Applications/"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"{C_RED}Copy failed: {result.stderr}{C_RESET}", file=sys.stderr)
        sys.exit(1)

    print(f"{C_GREEN}Installed:{C_RESET} {APP_BUNDLE}")

    # Set Login Item via osascript
    script = '''
    tell application "System Events"
        make new login item at end with properties {path:"/Applications/Local Whisper.app", hidden:true}
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"{C_GREEN}Login Item set{C_RESET} - app will start at login")
    else:
        print(f"{C_YELLOW}Login Item not set: {result.stderr.strip()}{C_RESET}")
        print(f"{C_DIM}Add manually: System Settings → General → Login Items{C_RESET}")


def cmd_uninstall():
    """Remove Login Item."""
    script = '''
    tell application "System Events"
        set theItems to every login item whose path is "/Applications/Local Whisper.app"
        repeat with theItem in theItems
            delete theItem
        end repeat
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"{C_GREEN}Login Item removed{C_RESET}")
    else:
        print(f"{C_YELLOW}Could not remove Login Item: {result.stderr.strip()}{C_RESET}", file=sys.stderr)


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
        ("wh restart",       "Restart the service"),
        ("wh backend",       "Show current backend + list available"),
        ("wh backend <name>","Switch grammar backend (restarts if running)"),
        ("wh config",        "Show key config values"),
        ("wh config edit",   "Open config in $EDITOR"),
        ("wh config path",   "Print path to config file"),
        ("wh install",       "Install .app to /Applications + Login Item"),
        ("wh uninstall",     "Remove Login Item"),
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
    elif cmd == "backend":
        cmd_backend(rest)
    elif cmd == "config":
        cmd_config(rest)
    elif cmd == "install":
        cmd_install()
    elif cmd == "uninstall":
        cmd_uninstall()
    elif cmd == "log":
        cmd_log()
    elif cmd == "version":
        cmd_version()
    elif cmd in ("-h", "--help", "help"):
        _print_help()
    else:
        print(f"{C_RED}Unknown command: {cmd}{C_RESET}", file=sys.stderr)
        print(f"{C_DIM}Run 'wh' for usage.{C_RESET}", file=sys.stderr)
        sys.exit(1)

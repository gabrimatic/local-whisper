# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Backend, engine, and replacement management commands."""

import sys

from .constants import C_BOLD, C_CYAN, C_DIM, C_GREEN, C_RED, C_RESET, C_YELLOW
from .lifecycle import (
    _get_config_path,
    _is_running,
    _list_backends,
    _list_engines,
    _read_config_backend,
    _read_config_engine,
    _write_config_backend,
    _write_config_engine,
)


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
        from .build import cmd_restart
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
        from .build import cmd_restart
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

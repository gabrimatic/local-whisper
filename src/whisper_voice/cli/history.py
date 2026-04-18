# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""CLI commands that read or export transcription history."""

import sys
from pathlib import Path

from .constants import C_BOLD, C_CYAN, C_DIM, C_GREEN, C_RED, C_RESET, C_YELLOW


def cmd_export(args: list) -> None:
    """``wh export [--format md|txt|json] [--out PATH] [--limit N]``.

    Exports the on-disk transcription history to the requested format.
    Defaults: markdown, ``~/Desktop/local-whisper-history.md``, no limit.
    """
    fmt = "md"
    out_path: Path | None = None
    limit: int | None = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--format", "-f") and i + 1 < len(args):
            fmt = args[i + 1].lower()
            i += 2
        elif arg in ("--out", "-o") and i + 1 < len(args):
            out_path = Path(args[i + 1]).expanduser()
            i += 2
        elif arg == "--limit" and i + 1 < len(args):
            try:
                limit = max(1, int(args[i + 1]))
            except ValueError:
                print(f"{C_RED}Invalid --limit value: {args[i + 1]}{C_RESET}", file=sys.stderr)
                sys.exit(1)
            i += 2
        elif arg in ("-h", "--help"):
            _print_export_help()
            return
        else:
            print(f"{C_RED}Unexpected argument: {arg}{C_RESET}", file=sys.stderr)
            _print_export_help()
            sys.exit(1)

    if out_path is None:
        out_path = Path.home() / "Desktop" / f"local-whisper-history.{_ext_for_format(fmt)}"

    try:
        from whisper_voice.history_export import export_history
        count = export_history(out_path, fmt=fmt, limit=limit)
    except ValueError as e:
        print(f"{C_RED}{e}{C_RESET}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"{C_RED}Export failed: {e}{C_RESET}", file=sys.stderr)
        sys.exit(1)

    if count == 0:
        print(f"  {C_YELLOW}No transcriptions yet.{C_RESET} Wrote an empty file to {out_path}.")
        return

    print(f"  {C_GREEN}{C_BOLD}Exported {count} entries{C_RESET}  {C_DIM}→{C_RESET}  {C_CYAN}{out_path}{C_RESET}")


def cmd_stats(args: list) -> None:
    """``wh stats`` prints usage statistics computed from the history files."""
    if args and args[0] in ("-h", "--help"):
        print(f"  {C_BOLD}wh stats{C_RESET}  Show transcription usage statistics.")
        return
    try:
        from whisper_voice.stats import compute_usage_stats, format_stats_text
        stats = compute_usage_stats(top_n=10)
    except Exception as e:
        print(f"{C_RED}Could not compute stats: {e}{C_RESET}", file=sys.stderr)
        sys.exit(1)
    print()
    print(f"  {C_BOLD}Local Whisper usage{C_RESET}")
    print()
    for line in format_stats_text(stats).splitlines():
        print(f"  {line}")
    print()


def _print_export_help() -> None:
    print(f"  {C_BOLD}wh export{C_RESET}  [--format md|txt|json] [--out PATH] [--limit N]")
    print()
    print(f"  {C_DIM}Export transcription history. Defaults: markdown on your Desktop.{C_RESET}")
    print()
    print(f"    {C_CYAN}--format{C_RESET}  md | txt | json   (default: md)")
    print(f"    {C_CYAN}--out{C_RESET}     output path          (default: ~/Desktop/local-whisper-history.<ext>)")
    print(f"    {C_CYAN}--limit{C_RESET}   max entries          (default: all)")


def _ext_for_format(fmt: str) -> str:
    return {"md": "md", "txt": "txt", "json": "json"}.get(fmt, "md")

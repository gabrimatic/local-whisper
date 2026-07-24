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


def _read_qwen_model() -> str:
    """Read the configured Qwen3-ASR model without initializing the runtime."""
    try:
        import tomllib

        with _get_config_path().open("rb") as config_file:
            data = tomllib.load(config_file)
        return str(
            data.get("qwen3_asr", {}).get(
                "model", "mlx-community/Qwen3-ASR-1.7B-bf16"
            )
        )
    except Exception:
        return "mlx-community/Qwen3-ASR-1.7B-bf16"


def _write_qwen_model(model: str) -> bool:
    from whisper_voice.config import update_config_field

    return update_config_field("qwen3_asr", "model", model)


def _ensure_engine_ready_for_cli(engine_id: str, model_id: str | None = None) -> None:
    """Prepare managed engine weights before writing config/restarting."""
    if engine_id == "apple_speech":
        from whisper_voice.engines.apple_speech import AppleSpeechEngine

        engine = AppleSpeechEngine()
        try:
            if not engine.start():
                raise RuntimeError(engine.last_error or "Apple speech model installation failed.")
        finally:
            engine.close()
        return

    if engine_id == "whisperkit":
        from whisper_voice.engines.whisperkit_runtime import require_whisperkit_cli

        require_whisperkit_cli()
        return

    from whisper_voice.engines.status import engine_model_status, ensure_engine_model_cached

    status = engine_model_status(engine_id, hf_repo=model_id)
    if status.get("cache_dir") is None:
        return
    if status.get("downloaded", False):
        return
    repo = status.get("hf_repo") or engine_id
    download_status = status.get("download_status") or "missing"
    verb = "Resuming" if download_status == "partial" else "Downloading"
    print(f"{C_DIM}{verb} model:{C_RESET} {repo}")
    ensure_engine_model_cached(engine_id, hf_repo=model_id)


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

    requested_qwen_model = None
    if len(args) > 1:
        if len(args) != 2 or new_engine != "qwen3_asr":
            print(
                f"{C_RED}Usage: wh engine qwen3_asr [1.7b|0.6b]{C_RESET}",
                file=sys.stderr,
            )
            sys.exit(1)
        from whisper_voice.engines.qwen3_models import resolve_qwen3_asr_model

        try:
            requested_qwen_model = resolve_qwen3_asr_model(args[1])
        except ValueError as exc:
            print(f"{C_RED}{exc}{C_RESET}", file=sys.stderr)
            sys.exit(1)

    previous_engine = _read_config_engine()
    previous_qwen_model = _read_qwen_model()

    try:
        if requested_qwen_model is None:
            _ensure_engine_ready_for_cli(new_engine)
        else:
            _ensure_engine_ready_for_cli(new_engine, requested_qwen_model)
    except Exception as exc:
        print(f"{C_RED}Could not prepare engine model:{C_RESET} {exc}", file=sys.stderr)
        sys.exit(1)

    qwen_model_changed = bool(
        requested_qwen_model and requested_qwen_model != previous_qwen_model
    )
    if qwen_model_changed and not _write_qwen_model(requested_qwen_model):
        sys.exit(1)

    if not _write_config_engine(new_engine):
        if qwen_model_changed:
            _write_qwen_model(previous_qwen_model)
        sys.exit(1)

    print(f"{C_GREEN}Engine set to:{C_RESET} {new_engine}")
    if requested_qwen_model:
        print(f"{C_GREEN}Qwen3-ASR model:{C_RESET} {requested_qwen_model}")

    running, _ = _is_running()
    if running:
        print(f"{C_DIM}Restarting service...{C_RESET}")
        from .build import cmd_restart
        from .doctor import _wait_for_service_ready

        cmd_restart()
        if not _wait_for_service_ready():
            if previous_engine and previous_engine != new_engine:
                print(
                    f"{C_YELLOW}Service did not become ready; rolling back to {previous_engine}...{C_RESET}",
                    file=sys.stderr,
                )
                if _write_config_engine(previous_engine):
                    if qwen_model_changed:
                        _write_qwen_model(previous_qwen_model)
                    cmd_restart()
                    _wait_for_service_ready(timeout=60.0)
            elif qwen_model_changed:
                print(
                    f"{C_YELLOW}Service did not become ready; rolling back Qwen3-ASR model...{C_RESET}",
                    file=sys.stderr,
                )
                if _write_qwen_model(previous_qwen_model):
                    cmd_restart()
                    _wait_for_service_ready(timeout=60.0)
            sys.exit(1)
    else:
        print(f"{C_DIM}Service not running - start with: wh start{C_RESET}")


def _notify_service_reload() -> None:
    """Hot-reload the running service after a CLI config write.

    Without this, `wh replace add` printed success while the running
    service kept using its cached rules until the next restart.
    """
    from .client import send_service_request

    running, _ = _is_running()
    if not running:
        return
    result = send_service_request({"action": "reload_config"})
    if result and result.get("success"):
        print(f"{C_DIM}Applied to the running service.{C_RESET}")
    else:
        print(f"{C_YELLOW}Could not hot-reload the running service — run: wh restart{C_RESET}")


def cmd_replace(args: list):
    """Show, add, remove, import, export, or test text replacement rules."""
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
                _notify_service_reload()
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
                _notify_service_reload()
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
            _notify_service_reload()
        except Exception as e:
            print(f"{C_RED}Error: {e}{C_RESET}", file=sys.stderr)
            sys.exit(1)

    elif subcmd in ("off", "disable"):
        try:
            from whisper_voice.config import update_config_field
            update_config_field("replacements", "enabled", False)
            print(f"{C_DIM}Replacements disabled{C_RESET}")
            _notify_service_reload()
        except Exception as e:
            print(f"{C_RED}Error: {e}{C_RESET}", file=sys.stderr)
            sys.exit(1)

    elif subcmd == "import":
        if len(args) != 2:
            print(
                f"{C_RED}Usage: wh replace import <file>{C_RESET}\n"
                f"{C_DIM}CSV (spoken,replacement), TSV, or \"a\"=\"b\" lines.{C_RESET}",
                file=sys.stderr,
            )
            sys.exit(1)
        _import_replacements(args[1])
        _notify_service_reload()

    elif subcmd == "export":
        if len(args) != 2:
            print(f"{C_RED}Usage: wh replace export <file.csv>{C_RESET}", file=sys.stderr)
            sys.exit(1)
        _export_replacements(args[1], _read_replacements()[1])

    elif subcmd == "test":
        if len(args) < 2:
            print(f"{C_RED}Usage: wh replace test \"sample sentence\"{C_RESET}", file=sys.stderr)
            sys.exit(1)
        _test_replacements(" ".join(args[1:]), _read_replacements())

    else:
        print(f"{C_RED}Unknown subcommand: {subcmd}{C_RESET}", file=sys.stderr)
        print(f"{C_DIM}Usage: wh replace [add|remove|on|off|import <file>|export <file>|test \"text\"]{C_RESET}", file=sys.stderr)
        sys.exit(1)


def _export_replacements(path_str: str, rules: dict) -> None:
    """Write the rules as quoted CSV, round-trippable by `wh replace import`."""
    import csv
    from pathlib import Path

    if not rules:
        print(f"{C_YELLOW}No rules to export.{C_RESET}")
        return
    path = Path(path_str).expanduser()
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            for spoken, replacement in sorted(rules.items()):
                writer.writerow([spoken, replacement])
    except Exception as e:
        print(f"{C_RED}Export failed: {e}{C_RESET}", file=sys.stderr)
        sys.exit(1)
    print(f"  {C_GREEN}Exported {len(rules)} rules{C_RESET} to {path}")


def _test_replacements(text: str, state: tuple) -> None:
    """Dry-run: show what the replacement pass would produce for a sample."""
    from whisper_voice.replacements import apply_replacements, compile_rule_pattern

    enabled, rules = state
    result = apply_replacements(text, rules)
    fired = sorted(
        spoken for spoken in rules if compile_rule_pattern(spoken).search(text)
    )
    print(f"  {C_DIM}in:{C_RESET}  {text}")
    print(f"  {C_DIM}out:{C_RESET} {result}")
    if fired:
        print(f"  {C_DIM}rules matched:{C_RESET} " + ", ".join(f'"{k}"' for k in fired))
    else:
        print(f"  {C_DIM}rules matched:{C_RESET} none")
    if not enabled:
        print(f"  {C_YELLOW}Note: replacements are currently disabled (wh replace on){C_RESET}")


def _import_replacements(path_str: str) -> None:
    """Bulk-import replacement rules from a CSV, TSV, or TOML-ish file.

    Accepted per-line formats (leading/trailing whitespace tolerated):
      - ``spoken, replacement``
      - ``spoken\treplacement``
      - ``"spoken" = "replacement"``   (matches the TOML style users already see)
      - ``spoken -> replacement``
    Blank lines and lines starting with ``#`` are ignored. Conflicts with
    existing rules are overwritten and surfaced in the summary.
    """
    import csv
    import io
    import re
    from pathlib import Path

    path = Path(path_str).expanduser()
    if not path.exists():
        print(f"{C_RED}File not found: {path}{C_RESET}", file=sys.stderr)
        sys.exit(1)

    try:
        # utf-8-sig strips a BOM that would otherwise glue itself onto the
        # first key (common in Excel exports).
        raw = path.read_text(encoding="utf-8-sig")
    except Exception as e:
        print(f"{C_RED}Could not read file: {e}{C_RESET}", file=sys.stderr)
        sys.exit(1)

    rules: list = []
    duplicates_in_file: set = set()
    seen_keys: set = set()
    toml_line = re.compile(r'^\s*"(?:[^"\\]|\\.)+"\s*=\s*"(?:[^"\\]|\\.)*"\s*$')

    def _parse_toml_line(line: str):
        """Parse one `"k" = "v"` line with real TOML semantics.

        tomllib handles the escape sequences the config writer itself
        produces (\\" \\n \\t \\\\) — the old regex silently dropped or
        garbled such lines on round-trip.
        """
        import tomllib
        try:
            parsed = tomllib.loads(line)
        except Exception:
            return None
        if len(parsed) != 1:
            return None
        key, value = next(iter(parsed.items()))
        if not isinstance(value, str):
            return None
        return key, value

    def _record(spoken: str, replacement: str) -> None:
        spoken = spoken.strip()
        if not spoken:
            return
        if spoken in seen_keys:
            duplicates_in_file.add(spoken)
        seen_keys.add(spoken)
        rules.append((spoken, replacement))

    # Decide the file's format ONCE (from the first data line) instead of
    # per line — per-line guessing misparsed CSV rows whose replacement
    # happened to contain "->".
    data_lines = [ln for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not data_lines:
        print(f"{C_YELLOW}No rules found in {path}{C_RESET}")
        return
    first = data_lines[0]
    if toml_line.match(first) and _parse_toml_line(first):
        file_format = "toml"
    elif "\t" in first:
        file_format = "tsv"
    elif "->" in first and "," not in first:
        file_format = "arrow"
    else:
        file_format = "csv"

    if file_format in ("csv", "tsv"):
        # csv.reader over the whole file handles quoted fields, embedded
        # commas/newlines, and doubled-quote escapes properly.
        delimiter = "\t" if file_format == "tsv" else ","
        try:
            for row in csv.reader(io.StringIO(raw), delimiter=delimiter):
                if not row or (row[0].strip().startswith("#")):
                    continue
                if len(row) >= 2:
                    _record(row[0], row[1])
        except Exception as e:
            print(f"{C_RED}Could not parse {file_format.upper()}: {e}{C_RESET}", file=sys.stderr)
            sys.exit(1)
    else:
        for line in data_lines:
            line = line.strip()
            if file_format == "toml":
                pair = _parse_toml_line(line)
                if pair:
                    _record(pair[0], pair[1])
            else:  # arrow
                left, sep, right = line.partition("->")
                if sep:
                    _record(left, right.strip())

    if not rules:
        print(f"{C_YELLOW}No rules found in {path}{C_RESET}")
        return

    from whisper_voice.config import _read_replacements_rules, add_replacements
    existing = set(_read_replacements_rules().keys())
    merged = dict(rules)  # last occurrence wins, matching config semantics
    overwrote = sorted(k for k in merged if k in existing)

    try:
        ok = add_replacements(merged)
    except Exception as e:
        print(f"{C_RED}Import failed: {e}{C_RESET}", file=sys.stderr)
        sys.exit(1)
    if not ok:
        print(f"{C_RED}Import failed to write config{C_RESET}", file=sys.stderr)
        sys.exit(1)

    print(f"  {C_GREEN}Imported {len(merged)} rules{C_RESET} from {path} "
          f"{C_DIM}({len(merged) - len(overwrote)} new, {len(overwrote)} updated){C_RESET}")
    if duplicates_in_file:
        print(f"  {C_YELLOW}{len(duplicates_in_file)} duplicate keys in file (last wins){C_RESET}")

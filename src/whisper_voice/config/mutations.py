# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Config mutation functions: replacements, backend switching, field updates.
"""

import fcntl
import os
import re
import sys
import tomllib

from . import schema as _schema
from .toml_helpers import _escape_toml_string, _replace_in_section, _serialize_toml_value


class ConfigUnparseableError(Exception):
    """Raised inside a rewrite transform when config.toml does not parse.

    Mutating a broken file would amplify the damage (e.g. rewriting the
    rules block from a defaults-parsed view wipes the user's real rules),
    so writers refuse instead.
    """


def _parse_or_refuse(content: str) -> dict:
    """Parse TOML content, raising ConfigUnparseableError on failure."""
    if not content.strip():
        return {}
    try:
        return tomllib.loads(content)
    except Exception as e:
        raise ConfigUnparseableError(
            f"config.toml does not parse ({e}); refusing to rewrite it. "
            "Fix the file (or delete it to regenerate defaults) and retry."
        )

# TOML sections whose name differs from the Config attribute that backs them.
_SECTION_ATTRS = {"parakeet_v3": "parakeet"}


def config_section_attr(section: str) -> str:
    """Map a TOML section name to the Config attribute that holds it."""
    return _SECTION_ATTRS.get(section, section)


def _read_replacements_rules() -> dict:
    """Read replacement rules from config.toml via tomllib."""
    if not _schema.CONFIG_FILE.exists():
        return {}
    try:
        with open(_schema.CONFIG_FILE, 'rb') as f:
            data = tomllib.load(f)
        rules = data.get('replacements', {}).get('rules', {})
        return {str(k): str(v) for k, v in rules.items()} if isinstance(rules, dict) else {}
    except Exception:
        return {}


def _locked_config_rewrite(transform) -> bool:
    """Serialize config.toml rewrites and land them atomically.

    Holds an exclusive flock on a sidecar lock file (never replaced, so the
    lock inode stays stable across writers), then writes the transformed
    content to a temp file and os.replace()s it over config.toml — a crash
    mid-write can no longer truncate the user's config.
    """
    lock_path = _schema.CONFIG_FILE.with_suffix(".toml.lock")
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            content = _schema.CONFIG_FILE.read_text() if _schema.CONFIG_FILE.exists() else ""
            new_content = transform(content)
            tmp_path = _schema.CONFIG_FILE.with_suffix(".toml.tmp")
            tmp_fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(new_content)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(tmp_path, _schema.CONFIG_FILE)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return True
    except Exception as e:
        print(f"Config write failed: {e}", file=sys.stderr)
        return False


def _write_replacements_rules(rules: dict) -> bool:
    """Write replacement rules to config.toml, preserving all other content.

    Replaces the entire [replacements.rules] sub-table with the given dict.
    Creates the section if it doesn't exist. Prefer _mutate_replacements_rules
    for read-modify-write operations — it derives the base set from the file
    inside the lock instead of trusting the caller's snapshot.
    """
    def transform(content: str) -> str:
        # Refuse to rewrite a file that doesn't parse — a snapshot-based
        # rewrite against a broken file destroys the user's real rules.
        _parse_or_refuse(content)
        return _splice_table_block(content, "replacements", "rules", rules, "enabled = true\n")

    return _locked_config_rewrite(transform)


def _splice_table_block(content: str, parent: str, child: str, rules: dict, parent_seed: str) -> str:
    """Replace the [parent.child] string-table block in TOML text with ``rules``."""
    # The body regexes below only consume newline-terminated lines; without
    # this, a file lacking a trailing newline gets its final key relocated
    # into the spliced table (e.g. [replacements] enabled silently becoming
    # a bogus dictionary rule).
    if content and not content.endswith("\n"):
        content += "\n"
    rules_lines = []
    for spoken, replacement in sorted(rules.items()):
        rules_lines.append(
            f'"{_escape_toml_string(spoken)}" = "{_escape_toml_string(replacement)}"'
        )
    rules_block = "\n".join(rules_lines)
    table = f"{parent}.{child}"

    # Find and replace the [parent.child] section.
    # The body runs from the header to the next [section] header or EOF.
    # Matching the whole body (not just quoted-key lines) matters: a
    # hand-edited bare-key rule (gonna = "going to") must be consumed
    # too, or the rewrite would leave it behind and produce a duplicate
    # key that breaks the next config parse.
    pattern = re.compile(
        r'(\[' + re.escape(table) + r'\]\s*\n)'  # header
        r'((?:(?!\[)[^\n]*\n?)*)',              # body: every line up to the next [section]
        re.MULTILINE
    )
    match = pattern.search(content)
    if match:
        new_body = rules_block + "\n" if rules_block else ""
        content = content[:match.start(2)] + new_body + content[match.end(2):]
    else:
        # Section doesn't exist yet
        if f"[{parent}]" in content:
            # Append [parent.child] after any existing [parent] content
            parent_pattern = re.compile(
                r'\[' + re.escape(parent) + r'\]\s*\n((?:[^[\n][^\n]*\n|\s*\n)*)',
                re.MULTILINE,
            )
            parent_match = parent_pattern.search(content)
            if parent_match:
                insert_pos = parent_match.end()
                content = content[:insert_pos] + f"\n[{table}]\n{rules_block}\n" + content[insert_pos:]
            else:
                content += f"\n[{table}]\n{rules_block}\n"
        else:
            content += f"\n[{parent}]\n{parent_seed}\n[{table}]\n{rules_block}\n"
    return content


def _mutate_string_table(parent: str, child: str, mutate, parent_seed: str, sync) -> tuple[bool, dict]:
    """Apply a delta to an on-disk {str: str} table under the config lock.

    ``mutate`` receives the table parsed from the CURRENT file content
    (not the caller's in-memory view) and returns the new dict. This makes
    concurrent writers (Swift IPC in the service, `wh replace` in another
    process) merge instead of clobbering each other. After a successful
    write, ``sync(final_table)`` runs under the config lock to update the
    in-memory config.

    Returns (ok, final_table).
    """
    from .loader import _config_lock, get_config
    final_table: dict = {}

    def transform(content: str) -> str:
        data = _parse_or_refuse(content)
        current = data.get(parent, {}).get(child, {})
        if not isinstance(current, dict):
            current = {}
        # Strip keys exactly like the loader does, so a hand-edited padded
        # key (" gonna ") matches removal/updates addressed as "gonna".
        current = {
            str(k).strip(): str(v) for k, v in current.items() if str(k).strip()
        }
        new_table = mutate(current)
        final_table.clear()
        final_table.update(new_table)
        return _splice_table_block(content, parent, child, new_table, parent_seed)

    ok = _locked_config_rewrite(transform)
    if ok:
        config = get_config()
        with _config_lock:
            sync(config, final_table)
    return ok, final_table


def _mutate_replacements_rules(mutate) -> tuple[bool, dict]:
    def sync(config, table):
        config.replacements.rules.clear()
        config.replacements.rules.update(table)

    return _mutate_string_table(
        "replacements", "rules", mutate, "enabled = true\n", sync
    )


def _mutate_dictation_commands(mutate) -> tuple[bool, dict]:
    def sync(config, table):
        config.dictation.commands.clear()
        config.dictation.commands.update(table)

    return _mutate_string_table(
        "dictation", "commands", mutate, "enabled = true\n", sync
    )


def add_replacement(spoken: str, replacement: str) -> bool:
    """Add or update a single replacement rule. Persists to TOML and updates in-memory config."""
    return add_replacements({spoken: replacement})


def add_replacements(rules: dict) -> bool:
    """Merge many replacement rules in one locked config rewrite.

    Bulk imports must use this instead of looping add_replacement: one
    rewrite instead of one per rule, and one snapshot for the UI.
    """
    if not rules:
        return True
    cleaned = {str(k): str(v) for k, v in rules.items() if str(k).strip()}

    def mutate(current: dict) -> dict:
        current.update(cleaned)
        return current

    ok, _ = _mutate_replacements_rules(mutate)
    return ok


def remove_replacement(spoken: str) -> bool:
    """Remove a replacement rule. Returns False if the key doesn't exist."""
    existed = [False]

    def mutate(current: dict) -> dict:
        if spoken in current:
            existed[0] = True
            del current[spoken]
        return current

    ok, _ = _mutate_replacements_rules(mutate)
    return ok and existed[0]


def add_dictation_command(spoken: str, replacement: str) -> bool:
    """Add or override a dictation command. Persists and updates in-memory config.

    Keys are lowercased to match the engine's case-insensitive semantics —
    an override spelled "Period" must replace "period", not coexist with it.
    lower() (not casefold()) mirrors re.IGNORECASE: casefold would rewrite
    "straße" to "strasse", a form the matcher could never match.
    """
    key = str(spoken).strip().lower()
    if not key:
        return False

    def mutate(current: dict) -> dict:
        normalized = {str(k).strip().lower(): v for k, v in current.items()}
        normalized[key] = str(replacement)
        return normalized

    ok, _ = _mutate_dictation_commands(mutate)
    return ok


def remove_dictation_command(spoken: str) -> bool:
    """Remove a user dictation command. Returns False if the key doesn't exist."""
    key = str(spoken).strip().lower()
    existed = [False]

    def mutate(current: dict) -> dict:
        normalized = {str(k).strip().lower(): v for k, v in current.items()}
        if key in normalized:
            existed[0] = True
            del normalized[key]
        return normalized

    ok, _ = _mutate_dictation_commands(mutate)
    return ok and existed[0]


def update_config_backend(new_backend: str) -> bool:
    """Update grammar backend in-memory AND persist to TOML file."""
    from .loader import _config_lock, get_config
    config = get_config()
    with _config_lock:
        config.grammar.backend = new_backend
        config.grammar.enabled = (new_backend != "none")

    def transform(content: str) -> str:
        _parse_or_refuse(content)
        content = _replace_in_section(content, "grammar", "backend", _serialize_toml_value(new_backend))
        enabled_val = "false" if new_backend == "none" else "true"
        return _replace_in_section(content, "grammar", "enabled", enabled_val)

    return _locked_config_rewrite(transform)


def update_config_field(section: str, key: str, value) -> bool:
    """Update a single config field in-memory AND persist to TOML.

    value may be a bool, int, float, or str. Serialization is handled
    automatically so callers pass Python-native values directly.

    Unknown section/key pairs are rejected (no write): persisting junk keys
    would let a stale or buggy client permanently pollute the user's config.
    """
    from .loader import _config_lock, get_config
    config = get_config()
    section_obj = getattr(config, config_section_attr(section), None)
    if section_obj is None or not hasattr(section_obj, key):
        print(f"Config update rejected: unknown field {section}.{key}", file=sys.stderr)
        return False
    with _config_lock:
        old_value = getattr(section_obj, key)
        setattr(section_obj, key, value)

    def transform(content: str) -> str:
        _parse_or_refuse(content)
        return _replace_in_section(content, section, key, _serialize_toml_value(value))

    ok = _locked_config_rewrite(transform)
    if not ok:
        # Roll the in-memory mutation back: a snapshot must never show a
        # value the file write refused (e.g. broken config.toml) — the UI
        # would confirm an edit that silently vanishes on restart.
        with _config_lock:
            setattr(section_obj, key, old_value)
    return ok

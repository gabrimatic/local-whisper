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
from .toml_helpers import _replace_in_section, _serialize_toml_value


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


def _write_replacements_rules(rules: dict) -> bool:
    """Write replacement rules to config.toml, preserving all other content.

    Replaces the entire [replacements.rules] sub-table with the given dict.
    Creates the section if it doesn't exist.
    """
    try:
        fd = os.open(str(_schema.CONFIG_FILE), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            content = _schema.CONFIG_FILE.read_text()

            # Build the new rules block
            rules_lines = []
            for spoken, replacement in sorted(rules.items()):
                escaped_k = spoken.replace('\\', '\\\\').replace('"', '\\"')
                escaped_v = replacement.replace('\\', '\\\\').replace('"', '\\"')
                rules_lines.append(f'"{escaped_k}" = "{escaped_v}"')
            rules_block = "\n".join(rules_lines)

            # Find and replace [replacements.rules] section
            # The section runs from its header to the next [section] header or EOF
            pattern = re.compile(
                r'(\[replacements\.rules\]\s*\n)'  # header
                r'((?:#[^\n]*\n|"(?:[^"\\]|\\.)*"\s*=\s*"(?:[^"\\]|\\.)*"\s*\n|\s*\n)*)',  # body lines
                re.MULTILINE
            )
            match = pattern.search(content)
            if match:
                new_body = rules_block + "\n" if rules_block else ""
                content = content[:match.start(2)] + new_body + content[match.end(2):]
            else:
                # Section doesn't exist yet
                if "[replacements]" in content:
                    # Append [replacements.rules] after any existing [replacements] content
                    # Find the end of the [replacements] section
                    repl_pattern = re.compile(r'\[replacements\]\s*\n((?:[^[\n][^\n]*\n|\s*\n)*)', re.MULTILINE)
                    repl_match = repl_pattern.search(content)
                    if repl_match:
                        insert_pos = repl_match.end()
                        content = content[:insert_pos] + f"\n[replacements.rules]\n{rules_block}\n" + content[insert_pos:]
                    else:
                        content += f"\n[replacements.rules]\n{rules_block}\n"
                else:
                    content += f"\n[replacements]\nenabled = true\n\n[replacements.rules]\n{rules_block}\n"

            _schema.CONFIG_FILE.write_text(content)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return True
    except Exception as e:
        print(f"Config write failed: {e}", file=sys.stderr)
        return False


def add_replacement(spoken: str, replacement: str) -> bool:
    """Add or update a single replacement rule. Persists to TOML and updates in-memory config."""
    from .loader import _config_lock, get_config
    config = get_config()
    with _config_lock:
        config.replacements.rules[spoken] = replacement
        snapshot = dict(config.replacements.rules)
    return _write_replacements_rules(snapshot)


def remove_replacement(spoken: str) -> bool:
    """Remove a replacement rule. Returns False if the key doesn't exist."""
    from .loader import _config_lock, get_config
    config = get_config()
    with _config_lock:
        if spoken not in config.replacements.rules:
            return False
        del config.replacements.rules[spoken]
        snapshot = dict(config.replacements.rules)
    return _write_replacements_rules(snapshot)


def update_config_backend(new_backend: str) -> bool:
    """Update grammar backend in-memory AND persist to TOML file."""
    from .loader import _config_lock, get_config
    config = get_config()
    with _config_lock:
        config.grammar.backend = new_backend
        config.grammar.enabled = (new_backend != "none")
    try:
        fd = os.open(str(_schema.CONFIG_FILE), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            content = _schema.CONFIG_FILE.read_text()
            content = _replace_in_section(content, "grammar", "backend", _serialize_toml_value(new_backend))
            enabled_val = "false" if new_backend == "none" else "true"
            content = _replace_in_section(content, "grammar", "enabled", enabled_val)
            _schema.CONFIG_FILE.write_text(content)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return True
    except Exception as e:
        print(f"Config write failed: {e}", file=sys.stderr)
        return False


def update_config_field(section: str, key: str, value) -> bool:
    """Update a single config field in-memory AND persist to TOML.

    value may be a bool, int, float, or str. Serialization is handled
    automatically so callers pass Python-native values directly.
    """
    from .loader import _config_lock, get_config
    config = get_config()
    section_obj = getattr(config, section, None)
    if section_obj is not None and hasattr(section_obj, key):
        with _config_lock:
            setattr(section_obj, key, value)
    try:
        fd = os.open(str(_schema.CONFIG_FILE), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            content = _schema.CONFIG_FILE.read_text()
            toml_value = _serialize_toml_value(value)
            content = _replace_in_section(content, section, key, toml_value)
            _schema.CONFIG_FILE.write_text(content)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return True
    except Exception as e:
        print(f"Config write failed: {e}", file=sys.stderr)
        return False

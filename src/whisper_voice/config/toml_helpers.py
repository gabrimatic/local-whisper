# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
TOML section helpers shared by config management and cli.
"""

import re
from typing import Optional


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
            # Also match unquoted numeric values (integer or float)
            m = re.match(rf'{key}\s*=\s*([-+]?[0-9]*\.?[0-9]+)', stripped)
            if m:
                return m.group(1)
    return None


def _replace_in_section(content: str, section: str, key: str, new_value: str) -> str:
    """Replace a key's value within a specific TOML section.

    new_value must already be serialized to its TOML string representation
    (e.g. '"quoted"' for strings, 'true'/'false' for bools, '42' for ints).

    If the key appears multiple times in the section, the first occurrence is updated
    and later duplicates are removed. If the key doesn't exist in the section, it is
    appended under the header.
    """
    lines = content.splitlines(keepends=True)
    section_header_idx = None
    replaced = False
    result: list[str] = []
    in_section = False
    key_pattern = re.compile(rf'^(\s*{re.escape(key)}\s*=\s*).*$')

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == f"[{section}]"
            if in_section:
                section_header_idx = len(result)
            result.append(line)
            continue
        if in_section and stripped and not stripped.startswith("#"):
            match = key_pattern.match(line)
            if match:
                if not replaced:
                    result.append(f"{match.group(1)}{new_value}\n")
                    replaced = True
                continue
        result.append(line)

    # Key not found in section - append it after the section header
    if replaced:
        return "".join(result)
    if section_header_idx is not None:
        result.insert(section_header_idx + 1, f"{key} = {new_value}\n")
        return "".join(result)

    # Section not found at all - append a new section at the end of the file
    result.append(f"\n[{section}]\n")
    result.append(f"{key} = {new_value}\n")
    return "".join(result)


def _serialize_toml_value(value) -> str:
    """Serialize a Python value to its TOML string representation."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    # String: escape backslashes and quotes, wrap in double quotes
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'

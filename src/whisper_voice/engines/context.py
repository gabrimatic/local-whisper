# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Build bounded, local-only ASR context from Vocabulary replacement rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

MAX_CONTEXT_CHARS = 4096
_PREFIX = "Vocabulary and preferred spellings: "


@dataclass(frozen=True)
class VocabularyContext:
    """A model prompt plus transparent inclusion/truncation metadata."""

    text: Optional[str]
    included_rules: int
    eligible_rules: int
    truncated: bool


def _single_line(value: object) -> str:
    return " ".join(str(value).replace("\x00", "").split())


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_vocabulary_context(
    rules: Mapping[object, object],
    *,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> VocabularyContext:
    """Convert enabled replacement rules into Qwen-compatible context.

    Empty replacements represent deletion rules and are intentionally omitted:
    asking an ASR model to recognize a word that the text pipeline deletes
    would work against the user's rule. The full spoken-to-preferred mapping is
    retained for every included rule.
    """
    if max_chars < len(_PREFIX) + 1:
        raise ValueError(f"max_chars must be at least {len(_PREFIX) + 1}")

    entries: list[str] = []
    seen: set[tuple[str, str]] = set()
    for raw_spoken, raw_replacement in sorted(
        rules.items(),
        key=lambda item: _single_line(item[0]).casefold(),
    ):
        spoken = _single_line(raw_spoken)
        preferred = _single_line(raw_replacement)
        if not spoken or not preferred:
            continue
        identity = (spoken.casefold(), preferred.casefold())
        if identity in seen:
            continue
        seen.add(identity)
        if spoken.casefold() == preferred.casefold():
            entries.append(_quote(preferred))
        else:
            entries.append(f"{_quote(preferred)} (spoken as {_quote(spoken)})")

    eligible = len(entries)
    included: list[str] = []
    for entry in entries:
        candidate = _PREFIX + "; ".join([*included, entry]) + "."
        if len(candidate) <= max_chars:
            included.append(entry)

    if not included:
        return VocabularyContext(None, 0, eligible, eligible > 0)
    return VocabularyContext(
        _PREFIX + "; ".join(included) + ".",
        len(included),
        eligible,
        len(included) < eligible,
    )


__all__ = ["MAX_CONTEXT_CHARS", "VocabularyContext", "build_vocabulary_context"]

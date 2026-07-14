# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Vocabulary replacement engine.

Applies user-defined ``{spoken form: replacement}`` rules to transcribed
text. This is the personal-dictionary layer: it fixes words the ASR model
consistently gets wrong ("open ai" -> "OpenAI"), expands abbreviations, and
enforces the spelling of names and jargon.

Semantics:

- Matching is case-insensitive and boundary-aware. Boundaries are the
  lookarounds ``(?<!\\w)`` / ``(?!\\w)`` rather than ``\\b`` so rules whose
  spoken form starts or ends with a non-word character ("c++", ".net",
  "e-mail!") still anchor to word edges instead of silently never matching.
- Longer spoken forms are applied first so "chat gpt four" wins over
  "chat gpt" instead of being clobbered by the shorter rule's output.
- Runs of spaces in the spoken form match any horizontal whitespace, so a
  double space in the transcript doesn't defeat a multi-word rule.
- Casing: a replacement that contains any uppercase is taken literally
  (the user chose the exact casing, e.g. "ChatGPT"). An all-lowercase
  replacement mirrors the matched text: "Gonna" -> "Going to",
  "GONNA" -> "GOING TO". This keeps sentence-initial capitalization intact
  after grammar correction.
"""

from __future__ import annotations

import re
from typing import Dict

__all__ = ["apply_replacements", "compile_rule_pattern"]


def compile_rule_pattern(spoken: str) -> re.Pattern:
    """Compile the match pattern for a spoken form.

    Word-edge lookarounds instead of ``\\b`` (see module docstring), and
    space runs generalized to ``[ \\t]+`` so extra spaces between words
    still match. Newlines intentionally do not match: a phrase split
    across lines was almost certainly not the dictated term.
    """
    parts = [re.escape(word) for word in spoken.split(" ") if word]
    body = r"[ \t]+".join(parts) if parts else re.escape(spoken)
    return re.compile(r"(?<!\w)" + body + r"(?!\w)", re.IGNORECASE)


def _adapt_case(replacement: str, matched: str) -> str:
    """Mirror the matched text's casing when the replacement is all-lowercase."""
    if not replacement or replacement != replacement.lower():
        return replacement
    letters = [c for c in matched if c.isalpha()]
    if len(letters) > 1 and matched.isupper():
        return replacement.upper()
    if matched[:1].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([,.!?;:])(?=\s|$)")
_DOUBLED_SEPARATOR = re.compile(r"([,;:])\s*([,;:])")


def _cleanup_after_removal(text: str) -> str:
    """Tidy the holes an empty ("delete this word") rule leaves behind."""
    text = _DOUBLED_SEPARATOR.sub(r"\2", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _MULTI_SPACE.sub(" ", text)
    return text.strip()


def apply_replacements(text: str, rules: Dict[str, str]) -> str:
    """Apply vocabulary replacement rules to ``text``.

    ``rules`` maps spoken forms to replacements. Rules apply longest spoken
    form first; each rule replaces every boundary-anchored, case-insensitive
    occurrence. Empty spoken forms are ignored. An empty replacement deletes
    the spoken form, and the surrounding whitespace/punctuation debris is
    tidied afterwards.
    """
    if not text or not rules:
        return text
    removal_fired = False
    ordered = sorted(rules.items(), key=lambda kv: (-len(kv[0]), kv[0]))
    for spoken, replacement in ordered:
        spoken = spoken.strip()
        if not spoken:
            continue
        pattern = compile_rule_pattern(spoken)
        if not replacement.strip():
            new_text = pattern.sub(replacement, text)
            if new_text != text:
                removal_fired = True
            text = new_text
        else:
            text = pattern.sub(lambda m: _adapt_case(replacement, m.group(0)), text)
    if removal_fired:
        text = _cleanup_after_removal(text)
    return text

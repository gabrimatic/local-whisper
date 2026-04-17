# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Voice dictation commands.

Applied to raw transcriptions *before* grammar correction so grammar sees
well-punctuated sentences. Users speak short command phrases in place of
punctuation or actions that are awkward to type:

    "Please come home new line dinner is ready"
    -> "Please come home\ndinner is ready"

    "It's open comma come on in"
    -> "It's open, come on in"

Matching is case-insensitive and word-boundary-aware. Rules are expressed
as ``{spoken phrase: replacement}`` where the replacement may be empty (to
remove a filler word) or contain punctuation, spaces, or newlines. Some
rules intentionally omit surrounding spaces (e.g. punctuation attaches to
the preceding word).
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

from .config import get_config


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Default command set. Keys are spoken phrases users will actually say;
# values are literal substitutions. The order matters: multi-word keys are
# sorted before single-word keys at runtime so "new paragraph" doesn't
# collide with "new" + "paragraph".
#
# Punctuation commands eat the preceding space and tack the punctuation onto
# the previous word. Structural commands (new line, new paragraph) insert
# whitespace and let the grammar pass normalize capitalization.
DEFAULT_COMMANDS: Dict[str, str] = {
    # Structural
    "new line": "\n",
    "new paragraph": "\n\n",
    "new section": "\n\n",
    # Punctuation (leading space stripped by post-processing)
    "period": ".",
    "full stop": ".",
    "comma": ",",
    "question mark": "?",
    "exclamation mark": "!",
    "exclamation point": "!",
    "colon": ":",
    "semicolon": ";",
    "dash": " - ",
    "hyphen": "-",
    "ellipsis": "...",
    # Grouping
    "open paren": "(",
    "close paren": ")",
    "open quote": "\"",
    "close quote": "\"",
    # Editing
    "scratch that": "__SCRATCH__",
    "strike that": "__SCRATCH__",
}


# Commands whose replacement should attach to the preceding word with no
# intervening whitespace (punctuation). Everything else leaves spaces alone.
_TIGHT_PUNCTUATION = {".", ",", "?", "!", ":", ";", "...", ")"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_dictation_commands(
    text: str,
    commands: Optional[Dict[str, str]] = None,
) -> str:
    """Apply dictation commands to raw transcription text.

    Returns the transformed text. If ``commands`` is ``None`` the active
    config is consulted (``[dictation] enabled`` + ``[dictation.commands]``).
    Passing an explicit dict bypasses config completely and is the supported
    test entry point.
    """
    if not text:
        return text
    if commands is None:
        cfg = get_config()
        if not getattr(cfg, "dictation", None) or not cfg.dictation.enabled:
            return text
        commands = dict(DEFAULT_COMMANDS)
        commands.update(cfg.dictation.commands or {})
    if not commands:
        return text
    return _apply(text, commands)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _apply(text: str, commands: Dict[str, str]) -> str:
    # Sort longer phrases first so "new paragraph" wins over "new".
    ordered = sorted(commands.items(), key=lambda kv: (-len(kv[0].split()), -len(kv[0])))
    for phrase, replacement in ordered:
        phrase = phrase.strip()
        if not phrase:
            continue
        text = _substitute_one(text, phrase, replacement)
    text = _collapse_whitespace(text)
    text = _apply_scratch(text)
    return text


def _substitute_one(text: str, phrase: str, replacement: str) -> str:
    pattern = r"\b" + re.escape(phrase) + r"\b"
    if replacement in _TIGHT_PUNCTUATION:
        # Eat the space(s) before the phrase so "hello period" -> "hello."
        return re.sub(r"\s*" + pattern, replacement, text, flags=re.IGNORECASE)
    return re.sub(pattern, replacement, text, flags=re.IGNORECASE)


# Only strip whitespace before punctuation when the punctuation is followed
# by whitespace or end-of-string. This keeps user-crafted replacements that
# embed a leading space (e.g. a " :)" smiley) intact.
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.!?;:])(?=\s|$)")
_MULTIPLE_SPACES = re.compile(r"[ \t]{2,}")
_SPACE_AROUND_NEWLINE = re.compile(r"[ \t]*\n[ \t]*")
_TRIPLE_NEWLINE = re.compile(r"\n{3,}")


def _collapse_whitespace(text: str) -> str:
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _MULTIPLE_SPACES.sub(" ", text)
    text = _SPACE_AROUND_NEWLINE.sub("\n", text)
    text = _TRIPLE_NEWLINE.sub("\n\n", text)
    return text.strip()


_SENTENCE_TERMINATORS = (".", "!", "?", "\n")


def _apply_scratch(text: str) -> str:
    """Delete the preceding sentence fragment when the user says "scratch that".

    The deletion stops at the last sentence boundary (., !, ?, or newline),
    which is preserved. Multiple occurrences compose: each scratch applies to
    whatever text is currently in front of it.
    """
    token = "__SCRATCH__"
    while token in text:
        idx = text.find(token)
        start = 0
        for terminator in _SENTENCE_TERMINATORS:
            pos = text.rfind(terminator, 0, idx)
            if pos != -1 and pos + 1 > start:
                start = pos + 1
        while start < idx and text[start] in " \t":
            start += 1
        end = idx + len(token)
        while end < len(text) and text[end] in " \t":
            end += 1
        text = text[:start] + text[end:]
    return text.strip()


# ---------------------------------------------------------------------------
# Introspection (exposed to the Swift UI via config_snapshot)
# ---------------------------------------------------------------------------

def effective_commands() -> Dict[str, str]:
    """Return the merged default + user-override command set."""
    cfg = get_config()
    commands = dict(DEFAULT_COMMANDS)
    user = getattr(cfg.dictation, "commands", None) if getattr(cfg, "dictation", None) else None
    if user:
        commands.update(user)
    return commands


def describe_rule(spoken: str, replacement: str) -> Tuple[str, str]:
    """Render a rule for display. Newlines and tabs become visible glyphs."""
    rendered = (
        replacement.replace("\n\n", "¶¶")
        .replace("\n", "¶")
        .replace("\t", "→")
    )
    if not rendered:
        rendered = "<removed>"
    return spoken, rendered

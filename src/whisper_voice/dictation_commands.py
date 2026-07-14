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
# intervening whitespace (sentence terminators, closing brackets).
_RIGHT_ATTACHING = {".", ",", "?", "!", ":", ";", "...", ")"}
# Commands whose replacement should attach to the following word with no
# intervening whitespace (opening brackets).
_LEFT_ATTACHING = {"("}

# Substituted spans are protected with private-use-area markers until every
# rule has run, so one rule's output can never be re-matched by a later rule
# ('sign off' = 'Best regards period' must not have its literal "period"
# converted to "."). Markers consist ONLY of private-use characters — even
# their index digits — so no user rule (e.g. a digit phrase) can ever match
# inside one.
_MARK_L = "\ue000"
_MARK_R = "\ue001"
_KEEP_L = "\ue002"
_KEEP_R = "\ue003"
_DIGIT_BASE = 0xE010


def _encode_index(i: int) -> str:
    return "".join(chr(_DIGIT_BASE + int(d)) for d in str(i))


def _decode_index(s: str) -> int:
    return int("".join(str(ord(c) - _DIGIT_BASE) for c in s))


# The public config value stays "__SCRATCH__"; it maps to this internal
# token at apply time so in-band text can never trigger a scratch.
_SCRATCH_VALUE = "__SCRATCH__"
_SCRATCH_TOKEN = "\ue000\ue004\ue001"


def _attach_direction(phrase: str, replacement: str) -> Optional[str]:
    """Which side a command's output glues to.

    "open ..." commands are left-attaching and "close ..." commands
    right-attaching when their value is punctuation — this is what lets
    both quote commands share the '"' character yet still produce "hi"
    instead of " hi ". The punctuation guard matters: a text macro like
    "close the loop" = "circle back" must keep normal spacing. Everything
    else falls back to the value-based sets.
    """
    stripped = replacement.strip()
    is_punctuationish = bool(stripped) and len(stripped) <= 3 and not any(
        ch.isalnum() or ch.isspace() for ch in stripped
    )
    if is_punctuationish:
        lowered = phrase.lower()
        if lowered.startswith("open "):
            return "left"
        if lowered.startswith("close "):
            return "right"
    if replacement in _RIGHT_ATTACHING:
        return "right"
    if replacement in _LEFT_ATTACHING:
        return "left"
    return None


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
    explicit_commands = commands is not None
    strip_fillers = True
    if commands is None:
        cfg = get_config()
        if not getattr(cfg, "dictation", None) or not cfg.dictation.enabled:
            return text
        strip_fillers = getattr(cfg.dictation, "strip_fillers", True)
        commands = merge_commands(cfg.dictation.commands)
    if explicit_commands and not commands:
        return text
    if strip_fillers:
        text = strip_speech_fillers(text)
    if not commands:
        return _collapse_whitespace(text)
    return _apply(text, commands)


def merge_commands(user_commands: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Merge user overrides onto the defaults.

    Keys are lowercased: matching is case-insensitive, so a user override
    spelled "Period" must replace the default "period" rule instead of
    silently coexisting with (and losing to) it. lower() (not casefold())
    mirrors re.IGNORECASE semantics — casefold would turn "straße" into
    "strasse", which the matcher could never match.
    """
    merged = {k.lower(): v for k, v in DEFAULT_COMMANDS.items()}
    for spoken, replacement in (user_commands or {}).items():
        key = str(spoken).strip().lower()
        if key:
            merged[key] = str(replacement)
    return merged


def strip_speech_fillers(text: str) -> str:
    """Remove high-confidence spoken fillers from dictation text.

    This is intentionally deterministic and conservative. It removes isolated
    disfluencies such as "um", "uh", "ah", "er", and pause-like "oh" while
    preserving common meaningful phrases such as "uh oh" and "oh no".
    """
    if not text:
        return text

    text, protected = _protect_meaningful_oh_phrases(text)
    text = _remove_contextual_oh(text)
    text = _remove_filler_words(text, _FILLER_WORD_FRAGMENT)
    text = _cleanup_filler_spacing(text)
    for marker, value in protected:
        text = text.replace(marker, value)
    return _collapse_whitespace(text)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _apply(text: str, commands: Dict[str, str]) -> str:
    # Sort longer phrases first so "new paragraph" wins over "new".
    ordered = sorted(commands.items(), key=lambda kv: (-len(kv[0].split()), -len(kv[0])))
    protected: list = []
    for phrase, replacement in ordered:
        phrase = phrase.strip()
        if not phrase:
            continue
        text = _substitute_one(text, phrase, replacement, protected)
    text = _restore_protected(text, protected)
    text = _collapse_whitespace(text)
    text = _apply_scratch(text)
    return text


def _restore_protected(text: str, protected: list) -> str:
    """Swap protection markers back for their literal replacement values."""
    if not protected:
        return text
    return re.sub(
        _MARK_L + r"([\ue010-\ue019]+)" + _MARK_R,
        lambda m: protected[_decode_index(m.group(1))],
        text,
    )


_FILLER_WORD_FRAGMENT = (
    r"(?:u+h+|u+h+m+|u+m+|a+h+|e+r+|e+r+m+|h+m+|m+h*m+|m+m+)"
)
_WORD_LEFT = r"(?<![\w'-])"
_WORD_RIGHT = r"(?![\w'-])"
_OH_RE = re.compile(r"(?i)(?<![\w'-])oh+(?![\w'-])")
_KEEP_OH_NEXT_WORDS = {
    "dear",
    "god",
    "goodness",
    "my",
    "no",
    "wow",
    "well",
    "yeah",
    "yes",
}
_MEANINGFUL_OH_PHRASE_RE = re.compile(
    r"(?i)(?<![\w'-])(?:uh[\s-]+oh|oh\s*,?\s*(?:"
    + "|".join(sorted(_KEEP_OH_NEXT_WORDS))
    + r"))(?![\w'-])"
)


def _protect_meaningful_oh_phrases(text: str) -> tuple[str, list[tuple[str, str]]]:
    protected: list[tuple[str, str]] = []

    def replace(match: re.Match) -> str:
        marker = f"{_KEEP_L}{_encode_index(len(protected))}{_KEEP_R}"
        protected.append((marker, match.group(0)))
        return marker

    return _MEANINGFUL_OH_PHRASE_RE.sub(replace, text), protected


def _remove_contextual_oh(text: str) -> str:
    def replace(match: re.Match) -> str:
        tail = text[match.end():]
        next_word = re.match(r"\s*,?\s*([A-Za-z']+)", tail)
        if next_word and next_word.group(1).lower() in _KEEP_OH_NEXT_WORDS:
            return match.group(0)
        return ""

    return _OH_RE.sub(replace, text)


def _remove_filler_words(text: str, word_fragment: str) -> str:
    word = _WORD_LEFT + word_fragment + _WORD_RIGHT
    # Remove comma-wrapped fillers as a clause: "I think, um, we go" -> "I think we go".
    text = re.sub(rf"(?i)(?<=\w)\s*,\s*{word}\s*,\s*(?=\w)", " ", text)
    # Remove leading fillers and their pause punctuation.
    text = re.sub(rf"(?i)^\s*{word}\s*[,;:.!?-]*\s*", "", text)
    # Remove remaining standalone fillers, plus lightweight trailing pause punctuation.
    text = re.sub(rf"(?i){word}\s*[,;:]*", "", text)
    return text


def _cleanup_filler_spacing(text: str) -> str:
    # Deleting a filler can leave orphaned comma/colon separators.
    text = re.sub(r"^\s*[,;:]\s*", "", text)
    text = re.sub(r"\s+([.!?])", r"\1", text)
    text = re.sub(r"\s*,\s*([.!?])", r"\1", text)
    text = re.sub(r"([,;:])\s*([,;:])", r"\2", text)
    return text


def _substitute_one(text: str, phrase: str, replacement: str, protected: list) -> str:
    """Replace one spoken phrase, leaving a protection marker behind.

    Boundaries are word-edge lookarounds (not ``\\b``) so phrases with
    non-word edge characters ("e.g.", "c++") still anchor correctly, and
    runs of spaces inside a phrase tolerate doubled spaces in transcripts.
    Whitespace-eating for attachment uses ``[ \\t]*`` — never ``\\s*`` —
    so a newline inserted by an earlier command survives a following
    punctuation command.
    """
    words = [re.escape(w) for w in phrase.split(" ") if w]
    body = r"[ \t]+".join(words) if words else re.escape(phrase)
    pattern = r"(?<!\w)" + body + r"(?!\w)"

    if replacement == _SCRATCH_VALUE:
        token = _SCRATCH_TOKEN
        return re.sub(r"[ \t]*" + pattern, token, text, flags=re.IGNORECASE)

    def _marker(_m: re.Match) -> str:
        protected.append(replacement)
        return f"{_MARK_L}{_encode_index(len(protected) - 1)}{_MARK_R}"

    direction = _attach_direction(phrase, replacement)
    if direction == "right":
        # Eat the space(s) before the phrase so "hello period" -> "hello."
        return re.sub(r"[ \t]*" + pattern, _marker, text, flags=re.IGNORECASE)
    if direction == "left":
        # Eat the space(s) after the phrase so "open paren hello" -> "(hello"
        return re.sub(pattern + r"[ \t]*", _marker, text, flags=re.IGNORECASE)
    return re.sub(pattern, _marker, text, flags=re.IGNORECASE)


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
    which is preserved. A terminator the user dictated IMMEDIATELY before
    the scratch ("hello period scratch that") belongs to the scratched
    utterance and is deleted with it. Multiple occurrences compose: each
    scratch applies to whatever text is currently in front of it.
    """
    token = _SCRATCH_TOKEN
    while token in text:
        idx = text.find(token)
        end = idx + len(token)
        while end < len(text) and text[end] in " \t":
            end += 1

        # The fragment ends just before the token; a sentence terminator
        # directly adjacent (dictated punctuation) is part of the fragment.
        fragment_end = idx
        while fragment_end > 0 and text[fragment_end - 1] in " \t":
            fragment_end -= 1
        while fragment_end > 0 and text[fragment_end - 1] in ".!?":
            fragment_end -= 1

        start = 0
        for terminator in _SENTENCE_TERMINATORS:
            pos = text.rfind(terminator, 0, fragment_end)
            if pos != -1 and pos + 1 > start:
                start = pos + 1
        while start < idx and text[start] in " \t":
            start += 1
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

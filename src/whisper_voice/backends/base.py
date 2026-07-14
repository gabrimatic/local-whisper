# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Base grammar backend interface for Local Whisper.

All grammar correction backends must inherit from GrammarBackend
and implement the required methods.
"""

import re
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Union

# Shared constants
ERROR_TRUNCATE_LENGTH = 50  # Consistent error message truncation
DEFAULT_CONNECT_TIMEOUT = 10  # Default connection timeout in seconds


class GrammarBackend(ABC):
    """
    Abstract base class for grammar correction backends.

    Provides common text processing utilities and defines the interface
    that all grammar backends must implement.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the backend."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Clean up resources when shutting down."""
        pass

    @abstractmethod
    def running(self) -> bool:
        """Check if the backend service is available."""
        pass

    @abstractmethod
    def start(self) -> bool:
        """
        Initialize and verify backend availability.

        Returns True if backend is ready, False otherwise.
        """
        pass

    @abstractmethod
    def fix(self, text: str) -> Tuple[str, Optional[str]]:
        """
        Fix grammar in the given text.

        Args:
            text: The text to correct.

        Returns:
            Tuple of (corrected_text, error_message).
            On success, error_message is None.
            On error, returns original text with error description.
        """
        pass

    @abstractmethod
    def fix_with_mode(self, text: str, mode_id: str) -> Tuple[str, Optional[str]]:
        """
        Fix text using a specific transformation mode.

        Args:
            text: The text to transform
            mode_id: The mode ID from MODE_REGISTRY

        Returns:
            Tuple of (transformed_text, error_message).
            On success, error_message is None.
            On error, returns original text with error description.
        """
        pass

    # ─────────────────────────────────────────────────────────────────
    # Shared utilities
    # ─────────────────────────────────────────────────────────────────

    def _get_timeout(self, timeout_config: int) -> Union[int, Tuple[int, None]]:
        """
        Get timeout value for requests.

        Args:
            timeout_config: Timeout from config (0 = unlimited read)

        Returns:
            Timeout value: int if configured, or (connect_timeout, None) for unlimited read
        """
        if timeout_config > 0:
            return timeout_config
        return (DEFAULT_CONNECT_TIMEOUT, None)  # (connect, read=unlimited)

    def _truncate_error(self, error: str) -> str:
        """Truncate error message to consistent length."""
        return str(error)[:ERROR_TRUNCATE_LENGTH]

    # ─────────────────────────────────────────────────────────────────
    # Shared text processing utilities
    # ─────────────────────────────────────────────────────────────────

    def _split_lossless(self, text: str, max_chars: int) -> List[Tuple[str, str]]:
        """Split text into (chunk, trailing_separator) pairs.

        Joining every chunk + separator reproduces the input EXACTLY. The
        old splitter collapsed all newlines and rejoined with a hardcoded
        "\\n\\n", so chunked proofreading mangled bullet lists and line
        breaks the prompt explicitly promises to preserve.

        Chunks break preferentially at newline runs, then at sentence
        boundaries, then hard-split. Each chunk is at most max_chars except
        when a single unbreakable atom exceeds it.
        """
        if max_chars <= 0 or len(text) <= max_chars:
            return [(text, "")]

        # Atoms are (piece, following_separator) where separators are the
        # exact whitespace runs removed from between pieces.
        atoms: List[Tuple[str, str]] = []
        parts = re.split(r'(\n[ \t]*(?:\n[ \t]*)*)', text)
        for i in range(0, len(parts), 2):
            piece = parts[i]
            sep = parts[i + 1] if i + 1 < len(parts) else ""
            if len(piece) <= max_chars:
                atoms.append((piece, sep))
                continue
            sub = re.split(r'((?<=[.!?])[ \t]+)', piece)
            sub_atoms: List[Tuple[str, str]] = []
            for j in range(0, len(sub), 2):
                sp = sub[j]
                ssep = sub[j + 1] if j + 1 < len(sub) else ""
                if len(sp) <= max_chars:
                    sub_atoms.append((sp, ssep))
                    continue
                for k in range(0, len(sp), max_chars):
                    seg = sp[k:k + max_chars]
                    seg_sep = ssep if k + max_chars >= len(sp) else ""
                    sub_atoms.append((seg, seg_sep))
            if sub_atoms:
                last_piece, last_sep = sub_atoms[-1]
                sub_atoms[-1] = (last_piece, last_sep + sep)
            atoms.extend(sub_atoms)

        # Greedy packing that keeps intra-chunk separators verbatim.
        chunks: List[Tuple[str, str]] = []
        current = ""
        current_sep = ""
        for piece, sep in atoms:
            if not current and not current_sep:
                current, current_sep = piece, sep
                continue
            candidate = current + current_sep + piece
            if len(candidate) > max_chars:
                chunks.append((current, current_sep))
                current, current_sep = piece, sep
            else:
                current, current_sep = candidate, sep
        chunks.append((current, current_sep))
        return chunks

    def _fix_in_chunks(self, text: str, max_chars: int, mode_id: str) -> Tuple[str, Optional[str]]:
        """Run fix_with_mode over lossless chunks, preserving separators."""
        pieces = self._split_lossless(text, max_chars)
        log_name = self.name
        from ..utils import log
        log(f"{log_name}: splitting {len(text)} chars into {len(pieces)} chunks", "INFO")
        results: List[str] = []
        for i, (chunk, sep) in enumerate(pieces):
            if chunk.strip():
                log(f"{log_name}: processing chunk {i + 1}/{len(pieces)} ({len(chunk)} chars)", "INFO")
                fixed, err = self.fix_with_mode(chunk, mode_id)
                if err:
                    return text, err
            else:
                fixed = chunk
            results.append(fixed + sep)
        return "".join(results), None

    def _normalize_leading_spaces(self, text: str) -> str:
        """
        Normalize leading spaces in output.

        Some models add a single leading space to each line.
        This removes that artifact while preserving intentional indentation.
        """
        lines = text.splitlines()
        non_empty = [line for line in lines if line.strip()]

        if not non_empty:
            return text

        # Don't modify if tabs are used (intentional formatting)
        if any(line.startswith("\t") for line in non_empty):
            return text

        # If all non-empty lines start with exactly one space, remove it
        if all(line.startswith(" ") and not line.startswith("  ") for line in non_empty):
            return "\n".join(
                line[1:] if line.startswith(" ") else line
                for line in lines
            )

        return text

    # Label prefixes, e.g. "Corrected:", "Here is the corrected text:"
    _LABEL_PATTERNS = [
        r'^corrected(?:\s+text)?:\s*',
        r'^output:\s*',
        r'^fixed(?:\s+text)?:\s*',
        r'^edited(?:\s+text)?:\s*',
        r'^result:\s*',
        r'^here(?:\s+is|\s+are|\'s)\s+(?:the\s+)?(?:corrected|fixed|edited)(?:\s+text)?:\s*',
        r'^the\s+corrected(?:\s+text)?\s+is:\s*',
    ]

    # Conversational openers, e.g. "Sure, I'll fix this."
    _OPENER_PATTERNS = [
        # "Sure" variants - only match when followed by conversational patterns
        r'^sure[,!.]\s+(?:i\'ll|i will|let me|here\'s|here is)[^.!?\n]*[.!?]?\s*',
        r'^sure[,!]\s*$',  # Just "Sure!" or "Sure,"
        r'^sure[,!]\s+',   # "Sure, " followed by anything (remove just the prefix)

        # "I'll/I will/I've" variants - only match specific helper phrases
        r'^i\'ll\s+(?:fix|correct|edit|help|clean)[^.!?\n]*[.!?]\s*',
        r'^i will\s+(?:fix|correct|edit|help|clean)[^.!?\n]*[.!?]\s*',
        r'^i\'ve\s+(?:corrected|fixed|edited|cleaned)[^.!?\n]*[.!?]\s*',
        r'^i have\s+(?:corrected|fixed|edited|cleaned)[^.!?\n]*[.!?]\s*',

        # "Here" variants
        r'^here\'s\s+(?:the\s+)?(?:corrected|fixed|edited|cleaned)[^:]*:\s*',
        r'^here is\s+(?:the\s+)?(?:corrected|fixed|edited|cleaned|text)[^:]*:\s*',
        r'^here you go[,!.]?\s*',

        # "Let me" variants - only match specific helper phrases
        r'^let me\s+(?:fix|correct|edit|help|clean)[^.!?\n]*[.!?]\s*',

        # "Of course" / "Certainly" variants
        r'^of course[,!.]?\s*',
        r'^certainly[,!.]?\s*',
        r'^absolutely[,!.]?\s*',

        # "Share" typo (ASR artifact for "Sure")
        r'^share,?\s+(?:i\'ll|i will|let me)[^.!?\n]*[.!?]?\s*',

        # Generic acknowledgment patterns
        r'^(?:okay|ok)[,!.]\s+(?:here\'s|here is|i\'ll|let me)[^.!?\n]*[.!?]?\s*',
        r'^(?:alright|all right)[,!.]?\s+(?:here|i\'ll|let me)[^.!?\n]*[.!?]?\s*',
    ]

    # Trailing meta-commentary, e.g. "Let me know if you need more changes."
    _TRAILER_PATTERNS = [
        r'\s*let me know if[^.!?\n]*[.!?]?\s*$',
        r'\s*i hope this helps[.!?]?\s*$',
        r'\s*feel free to[^.!?\n]*[.!?]?\s*$',
        r'\s*is there anything else[^.!?\n]*[.!?]?\s*$',
        r'\s*please let me know[^.!?\n]*[.!?]?\s*$',
    ]

    @staticmethod
    def _echoes_input_prefix(matched: str, original: Optional[str]) -> bool:
        """True when the matched artifact is really the user's own text.

        A proofread result closely echoes its input, so any prefix the model
        'added' that ALSO starts the input text (e.g. a sentence that begins
        with "Sure, ..." or "Result: ...") is legitimate content — stripping
        it would corrupt the user's text before it gets pasted back over
        their selection.
        """
        if original is None:
            return False
        fragment = matched.strip().lower()
        if not fragment:
            return False
        return original.strip().lower().startswith(fragment)

    @staticmethod
    def _echoes_input_suffix(matched: str, original: Optional[str]) -> bool:
        """Suffix twin of _echoes_input_prefix."""
        if original is None:
            return False
        fragment = matched.strip().lower()
        if not fragment:
            return False
        return original.strip().lower().endswith(fragment)

    def _clean_result(self, result: str, original: Optional[str] = None) -> str:
        """
        Clean common artifacts from model output.

        Removes conversational prefixes, meta-commentary, and formatting
        artifacts that models sometimes add despite instructions. When
        ``original`` (the input text) is provided, nothing that echoes the
        input is ever stripped — the model faithfully returning the user's
        own "Sure, sounds good." must survive cleaning intact.
        """
        result = result.strip()

        # Strip symmetric wrapping quotes only when the input wasn't quoted.
        for quote in ('"', "'"):
            if (
                len(result) >= 2
                and result.startswith(quote)
                and result.endswith(quote)
                and not (original or "").strip().startswith(quote)
                and not (original or "").strip().endswith(quote)
            ):
                result = result[1:-1].strip()

        # Iterate to a fixpoint (an opener can hide a label prefix behind
        # it), and never let a single strip erase the whole result — if an
        # "artifact" IS the entire text, it's the content.
        for _ in range(3):
            before = result
            for pattern in self._LABEL_PATTERNS + self._OPENER_PATTERNS:
                m = re.match(pattern, result, flags=re.IGNORECASE)
                if not m or not m.group(0):
                    continue
                if self._echoes_input_prefix(m.group(0), original):
                    continue
                candidate = result[m.end():]
                if candidate.strip():
                    result = candidate
            for pattern in self._TRAILER_PATTERNS:
                m = re.search(pattern, result, flags=re.IGNORECASE)
                if not m or not m.group(0):
                    continue
                if self._echoes_input_suffix(m.group(0), original):
                    continue
                candidate = result[:m.start()]
                if candidate.strip():
                    result = candidate
            if result == before:
                break

        # Unwrap a markdown code fence the model added — but never one the
        # user's own text started with.
        if not (original or "").lstrip().startswith("```"):
            code_block_match = re.match(
                r'^```[a-zA-Z]*\s*\n?(.*?)\n?```\s*$',
                result,
                re.DOTALL,
            )
            if code_block_match:
                result = code_block_match.group(1).strip()

        return result.strip()

"""
Base grammar backend interface for Local Whisper.

All grammar correction backends must inherit from GrammarBackend
and implement the required methods.
"""

import re
from abc import ABC, abstractmethod
from typing import Tuple, List, Optional, Union

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

    def _split_paragraph(self, text: str, max_chars: int) -> List[str]:
        """Split a paragraph into chunks respecting sentence boundaries."""
        if len(text) <= max_chars:
            return [text]

        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks: List[str] = []
        current = ""

        for sentence in sentences:
            if not sentence:
                continue

            # Handle sentences longer than max_chars
            if len(sentence) > max_chars:
                if current:
                    chunks.append(current)
                    current = ""
                # Split long sentence into fixed-size parts
                for i in range(0, len(sentence), max_chars):
                    chunks.append(sentence[i:i + max_chars])
                continue

            # Try to add sentence to current chunk
            if not current:
                current = sentence
            elif len(current) + 1 + len(sentence) <= max_chars:
                current = f"{current} {sentence}"
            else:
                chunks.append(current)
                current = sentence

        if current:
            chunks.append(current)

        return chunks

    def _split_text(self, text: str, max_chars: int) -> List[str]:
        """Split text into chunks respecting paragraph and sentence boundaries."""
        if len(text) <= max_chars:
            return [text]

        chunks: List[str] = []
        current = ""

        for para in text.split("\n\n"):
            para = para.strip()
            if not para:
                continue

            parts = self._split_paragraph(para, max_chars)
            for part in parts:
                if not current:
                    current = part
                elif len(current) + 2 + len(part) <= max_chars:
                    current = f"{current}\n\n{part}"
                else:
                    chunks.append(current)
                    current = part

        if current:
            chunks.append(current)

        return chunks

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

    def _clean_result(self, result: str) -> str:
        """
        Clean common artifacts from model output.

        Removes conversational prefixes, meta-commentary, and formatting
        artifacts that models sometimes add despite instructions.
        """
        result = result.strip()
        result = result.strip('"\'')

        # ─────────────────────────────────────────────────────────────────
        # Pattern 1: Remove label prefixes (case-insensitive)
        # Examples: "Corrected:", "Output:", "Fixed text:", "Here is the corrected text:"
        # ─────────────────────────────────────────────────────────────────
        label_patterns = [
            r'^corrected(?:\s+text)?:\s*',
            r'^output:\s*',
            r'^fixed(?:\s+text)?:\s*',
            r'^edited(?:\s+text)?:\s*',
            r'^result:\s*',
            r'^here(?:\s+is|\s+are|\'s)\s+(?:the\s+)?(?:corrected|fixed|edited)(?:\s+text)?:\s*',
            r'^the\s+corrected(?:\s+text)?\s+is:\s*',
        ]

        for pattern in label_patterns:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

        # ─────────────────────────────────────────────────────────────────
        # Pattern 2: Remove conversational openers at the start
        # Examples: "Sure!", "Sure, I'll fix this.", "I've corrected...", "Share, I will fix..."
        # ─────────────────────────────────────────────────────────────────
        conversational_openers = [
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

        for pattern in conversational_openers:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

        # ─────────────────────────────────────────────────────────────────
        # Pattern 3: Remove trailing meta-commentary
        # Examples: "Let me know if you need more changes.", "I hope this helps!"
        # ─────────────────────────────────────────────────────────────────
        trailing_patterns = [
            r'\s*let me know if[^.!?\n]*[.!?]?\s*$',
            r'\s*i hope this helps[.!?]?\s*$',
            r'\s*feel free to[^.!?\n]*[.!?]?\s*$',
            r'\s*is there anything else[^.!?\n]*[.!?]?\s*$',
            r'\s*please let me know[^.!?\n]*[.!?]?\s*$',
        ]

        for pattern in trailing_patterns:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

        # ─────────────────────────────────────────────────────────────────
        # Pattern 4: Handle markdown code block wrapper
        # Sometimes models wrap output in ```text ... ``` or similar
        # ─────────────────────────────────────────────────────────────────
        code_block_match = re.match(
            r'^```(?:text|plain|markdown)?\s*\n?(.*?)\n?```\s*$',
            result,
            re.DOTALL | re.IGNORECASE
        )
        if code_block_match:
            result = code_block_match.group(1).strip()

        # Final cleanup
        result = result.strip()
        result = result.strip('"\'')

        return result

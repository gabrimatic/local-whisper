"""
Apple Intelligence backend implementation for grammar correction.

Uses Apple's on-device Foundation Models via a Swift CLI helper.
The Swift CLI has grammar instructions built-in using LanguageModelSession.
"""

import subprocess
from pathlib import Path
from typing import Tuple, Optional

from ..base import GrammarBackend, ERROR_TRUNCATE_LENGTH
from ...config import get_config
from ...utils import log, SERVICE_CHECK_TIMEOUT


# Path to the Swift CLI helper
CLI_DIR = Path(__file__).parent / "cli"
CLI_BUILD_DIR = CLI_DIR / ".build" / "release"
CLI_BINARY = CLI_BUILD_DIR / "apple-ai-cli"


class AppleIntelligenceBackend(GrammarBackend):
    """Grammar correction backend using Apple Intelligence."""

    def __init__(self):
        self._available: Optional[bool] = None

    @property
    def name(self) -> str:
        return "Apple Intelligence"

    def close(self) -> None:
        """Clean up resources (no-op for Apple Intelligence)."""
        pass

    def running(self) -> bool:
        """Check if Apple Intelligence is available."""
        # Use SERVICE_CHECK_TIMEOUT to prevent hanging
        stdout, stderr, code = self._run_cli(["check"], timeout=SERVICE_CHECK_TIMEOUT)

        if code == 0 and stdout and "available" in stdout.lower():
            self._available = True
            return True

        self._available = False

        if stderr:
            reason = stderr.strip()
            if "apple_intelligence_not_enabled" in reason:
                log("Apple Intelligence not enabled. Enable in System Settings.", "WARN")
            elif "device_not_eligible" in reason:
                log("Device not eligible for Apple Intelligence.", "WARN")
            elif "model_not_ready" in reason:
                log("Apple Intelligence model not ready yet.", "WARN")

        return False

    def start(self) -> bool:
        """Check Apple Intelligence availability."""
        if not CLI_BINARY.exists():
            log(f"CLI not built. Run: cd {CLI_DIR} && swift build -c release", "ERR")
            return False

        if self.running():
            log("Apple Intelligence ready", "OK")
            return True

        log("Apple Intelligence not available", "WARN")
        return False

    def fix(self, text: str) -> Tuple[str, Optional[str]]:
        """Fix grammar using Apple Intelligence."""
        config = get_config()

        if not text or len(text.strip()) < 3:
            return text, None

        # If max_chars is 0 or negative, don't chunk (unlimited)
        if config.apple_intelligence.max_chars <= 0:
            return self._fix_chunk(text)

        max_chars = max(500, config.apple_intelligence.max_chars)
        chunks = self._split_text(text, max_chars)

        if len(chunks) == 1:
            return self._fix_chunk(text)

        # Process chunks
        results = []
        for idx, chunk in enumerate(chunks, start=1):
            fixed, err = self._fix_chunk(chunk)
            if err:
                log(f"Grammar chunk {idx}/{len(chunks)} skipped: {err}", "WARN")
                results.append(chunk)
            else:
                results.append(fixed)

        return "\n\n".join(results), None

    # ─────────────────────────────────────────────────────────────────
    # Private methods
    # ─────────────────────────────────────────────────────────────────

    def _run_cli(
        self,
        args: list,
        input_text: str = None,
        timeout: int = None
    ) -> Tuple[Optional[str], Optional[str], int]:
        """
        Run the Apple AI CLI with given arguments.

        Returns: (stdout, stderr, returncode)
        """
        if not CLI_BINARY.exists():
            return None, "CLI not built. Run: swift build -c release", 1

        try:
            result = subprocess.run(
                [str(CLI_BINARY)] + args,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=timeout if timeout and timeout > 0 else None
            )
            return result.stdout, result.stderr, result.returncode

        except subprocess.TimeoutExpired:
            return None, "Timeout", 1
        except Exception as e:
            return None, str(e), 1

    def _fix_chunk(self, text: str) -> Tuple[str, Optional[str]]:
        """Fix grammar for a single chunk of text."""
        config = get_config()
        # Use consistent timeout handling (0 = unlimited)
        timeout = config.apple_intelligence.timeout if config.apple_intelligence.timeout > 0 else None

        # Send just the raw text - Swift CLI has instructions built-in
        stdout, stderr, code = self._run_cli(["fix"], input_text=text, timeout=timeout)

        if code != 0:
            error_msg = stderr.strip() if stderr else "Unknown error"
            if "unavailable" in error_msg.lower() or "not available" in error_msg.lower():
                return text, "Apple Intelligence not available"
            return text, error_msg[:ERROR_TRUNCATE_LENGTH]

        result = stdout.strip() if stdout else ""
        result = self._clean_result(result)
        result = self._normalize_leading_spaces(result)

        return (result if result else text), None

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Apple Intelligence backend implementation for grammar correction.

Uses Apple's Foundation Models Python SDK for on-device text generation.
"""

import asyncio
import concurrent.futures
import threading
from typing import Optional, Tuple

from ...config import get_config
from ...utils import log
from ..base import ERROR_TRUNCATE_LENGTH, GrammarBackend
from ..modes import get_mode

try:
    import apple_fm_sdk as fm
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False


class AppleIntelligenceBackend(GrammarBackend):
    """
    Grammar correction backend using Apple Intelligence Foundation Models.

    Uses the official Python SDK for direct on-device text generation,
    with a persistent event loop in a background thread so sessions
    stay warm across calls.
    """

    def __init__(self):
        self._session: Optional[object] = None
        self._last_system_prompt: Optional[str] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._session_lock = threading.Lock()

    @property
    def name(self) -> str:
        return "Apple Intelligence"

    def close(self) -> None:
        """Clean up session and stop the background event loop."""
        with self._session_lock:
            self._session = None
            self._last_system_prompt = None
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._loop = None
        self._loop_thread = None

    def running(self) -> bool:
        """Check if Apple Intelligence is available on this device."""
        if not _SDK_AVAILABLE:
            log("apple-fm-sdk not installed. Run: pip install -e .", "ERR")
            return False

        try:
            model = fm.SystemLanguageModel()
            available, reason = model.is_available()
        except Exception as e:
            log(f"Apple Intelligence availability check failed: {e}", "ERR")
            return False

        if available:
            return True

        if reason is not None:
            reason_name = reason.name if hasattr(reason, "name") else str(reason)
            if "not_enabled" in reason_name.lower() or "not_enabled" in str(reason).lower():
                log("Apple Intelligence not enabled. Enable in System Settings.", "WARN")
            elif "not_eligible" in reason_name.lower() or "not_eligible" in str(reason).lower():
                log("Device not eligible for Apple Intelligence.", "WARN")
            elif "not_ready" in reason_name.lower() or "not_ready" in str(reason).lower():
                log("Apple Intelligence model not ready yet.", "WARN")
            else:
                log(f"Apple Intelligence unavailable: {reason_name}", "WARN")

        return False

    def start(self) -> bool:
        """Verify Apple Intelligence is available."""
        if not self.running():
            log("Apple Intelligence not available", "WARN")
            return False
        log("Apple Intelligence ready", "OK")
        return True

    def fix(self, text: str) -> Tuple[str, Optional[str]]:
        """Fix grammar using Apple Intelligence. Delegates to transcription mode."""
        return self.fix_with_mode(text, "transcription")

    def fix_with_mode(self, text: str, mode_id: str) -> Tuple[str, Optional[str]]:
        """Fix text using a specific transformation mode."""
        if not text or len(text.strip()) < 3:
            log("Text too short for mode processing, returning as-is", "INFO")
            return text, None

        mode = get_mode(mode_id)
        if not mode:
            log(f"Unknown mode requested: {mode_id}", "ERR")
            return text, f"Unknown mode: {mode_id}"

        config = get_config()
        max_chars = config.apple_intelligence.max_chars
        if max_chars > 0 and len(text) > max_chars:
            log(f"Apple Intelligence: splitting {len(text)} chars into chunks of {max_chars}", "INFO")
            chunks = self._split_text(text, max_chars)
            results = []
            for i, chunk in enumerate(chunks):
                log(f"Apple Intelligence: processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)", "INFO")
                result, err = self.fix_with_mode(chunk, mode_id)
                if err:
                    return text, err
                results.append(result)
            return "\n\n".join(results), None

        log(f"Apple Intelligence fix_with_mode: {mode.name} ({len(text)} chars)", "INFO")

        timeout = config.apple_intelligence.timeout if config.apple_intelligence.timeout > 0 else None
        full_prompt = mode.user_prompt_template.replace("{text}", text)

        try:
            result = self._run_async(
                self._generate(mode.system_prompt, full_prompt),
                timeout=timeout,
            )
        except (TimeoutError, concurrent.futures.TimeoutError):
            log(f"Apple Intelligence timed out for {mode.name}", "ERR")
            return text, "Timeout"
        except Exception as e:
            err_msg = self._classify_error(e)
            log(f"Apple Intelligence error for {mode.name}: {err_msg}", "ERR")
            return text, err_msg[:ERROR_TRUNCATE_LENGTH]

        if not result:
            log("Apple Intelligence returned empty result", "WARN")
            return text, "Empty response"

        result = self._clean_result(result)
        result = self._normalize_leading_spaces(result)

        log(f"Apple Intelligence {mode.name} complete: {len(text)} -> {len(result)} chars", "OK")
        return (result if result else text), None

    # ─────────────────────────────────────────────────────────────────
    # Async helpers
    # ─────────────────────────────────────────────────────────────────

    def _ensure_loop(self) -> None:
        """Start a persistent background event loop if one isn't running."""
        if self._loop is not None and not self._loop.is_closed():
            return
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever,
            daemon=True,
            name="apple-intelligence-loop",
        )
        self._loop_thread.start()

    def _run_async(self, coro, timeout: Optional[float] = None) -> str:
        """Submit a coroutine to the background loop and wait for the result."""
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    async def _generate(self, system_prompt: str, user_prompt: str) -> str:
        """Create or reuse a session and call respond()."""
        with self._session_lock:
            if self._session is None or self._last_system_prompt != system_prompt:
                model = fm.SystemLanguageModel(
                    use_case=fm.SystemLanguageModelUseCase.GENERAL,
                    guardrails=fm.SystemLanguageModelGuardrails.PERMISSIVE_CONTENT_TRANSFORMATIONS,
                )
                self._session = fm.LanguageModelSession(
                    instructions=system_prompt,
                    model=model,
                )
                self._last_system_prompt = system_prompt
            session = self._session

        return await session.respond(user_prompt)

    # ─────────────────────────────────────────────────────────────────
    # Error classification
    # ─────────────────────────────────────────────────────────────────

    def _classify_error(self, exc: Exception) -> str:
        """Map SDK exceptions to human-readable error strings."""
        if not _SDK_AVAILABLE:
            return str(exc)

        name = type(exc).__name__
        if name == "GuardrailViolationError":
            return "Guardrail violation"
        if name == "RateLimitedError":
            return "Rate limited"
        if name == "RefusalError":
            reason = getattr(exc, "reason", "")
            return f"Refusal: {reason}" if reason else "Model refused"
        if name == "ExceededContextWindowSizeError":
            return "Context window exceeded"
        if name == "AssetsUnavailableError":
            return "Model assets unavailable"
        if name == "ConcurrentRequestsError":
            return "Too many concurrent requests"
        if name == "UnsupportedLanguageOrLocaleError":
            return "Unsupported language"
        if name == "DecodingFailureError":
            return "Decoding failure"
        return str(exc)

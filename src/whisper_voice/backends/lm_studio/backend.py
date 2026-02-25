# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
LM Studio backend implementation for grammar correction.

Handles grammar correction via LM Studio's OpenAI-compatible API.
"""

from typing import Optional, Tuple
from urllib.parse import urlparse

import requests

from ...config import get_config
from ...utils import SERVICE_CHECK_TIMEOUT, log
from ..base import GrammarBackend
from ..modes import get_mode, get_mode_lm_studio_messages


class LMStudioBackend(GrammarBackend):
    """Grammar correction backend using LM Studio's OpenAI-compatible API."""

    def __init__(self):
        self._session = requests.Session()

    @property
    def name(self) -> str:
        return "LM Studio"

    def close(self) -> None:
        """Clean up resources."""
        try:
            self._session.close()
        except Exception:
            pass

    def running(self) -> bool:
        """Check if LM Studio server is running."""
        config = get_config()

        if not self._is_local_url(config.lm_studio.check_url):
            log("LM Studio URL must be localhost or LAN", "ERR")
            return False

        try:
            r = self._session.get(
                config.lm_studio.check_url,
                timeout=SERVICE_CHECK_TIMEOUT
            )
            return r.status_code == 200
        except (requests.RequestException, ConnectionError):
            return False

    def start(self) -> bool:
        """Check LM Studio availability and verify model."""
        if not self.running():
            log("LM Studio not running - start LM Studio and load a model", "WARN")
            return False

        # Verify model is available
        model_ok, model_info = self._check_model()
        if model_ok:
            log(f"LM Studio ready ({model_info})", "OK")
            return True
        else:
            log(f"LM Studio: {model_info}", "WARN")
            return False

    def fix(self, text: str) -> Tuple[str, Optional[str]]:
        """Fix grammar using LM Studio. Delegates to transcription mode."""
        return self.fix_with_mode(text, "transcription")

    def fix_with_mode(self, text: str, mode_id: str) -> Tuple[str, Optional[str]]:
        """Fix text using a specific transformation mode."""
        # Validate mode exists before processing
        mode = get_mode(mode_id)
        if not mode:
            log(f"Unknown mode requested: {mode_id}", "ERR")
            return text, f"Unknown mode: {mode_id}"

        config = get_config()

        if not self._is_local_url(config.lm_studio.url):
            log(f"LM Studio URL not local: {config.lm_studio.url}", "ERR")
            return text, "LM Studio URL must be localhost or LAN"

        if not text or len(text.strip()) < 3:
            log("Text too short for mode processing, returning as-is", "INFO")
            return text, None

        # Build messages with error handling
        try:
            messages = get_mode_lm_studio_messages(mode_id, text)
        except ValueError as e:
            log(f"Failed to build messages for mode {mode_id}: {e}", "ERR")
            return text, f"Prompt error: {e}"

        # Handle max_chars chunking
        max_chars = config.lm_studio.max_chars
        if max_chars > 0 and len(text) > max_chars:
            log(f"LM Studio: splitting {len(text)} chars into chunks of {max_chars}", "INFO")
            chunks = self._split_text(text, max_chars)
            results = []
            for i, chunk in enumerate(chunks):
                log(f"LM Studio: processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)", "INFO")
                result, err = self.fix_with_mode(chunk, mode_id)
                if err:
                    return text, err
                results.append(result)
            return "\n\n".join(results), None

        log(f"LM Studio fix_with_mode: {mode.name} ({len(text)} chars)", "INFO")

        try:
            # Use shared timeout helper
            timeout = self._get_timeout(config.lm_studio.timeout)

            # Get model ID
            model_id = self._get_model_id()
            if not model_id:
                log("LM Studio: No model available for mode processing", "ERR")
                return text, "No model available"

            # Build request payload (OpenAI chat format)
            payload = {
                "model": model_id,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": config.lm_studio.max_tokens if config.lm_studio.max_tokens > 0 else 2048,
                "stream": False
            }

            r = self._session.post(
                config.lm_studio.url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer lm-studio"
                },
                timeout=timeout
            )
            r.raise_for_status()

            # Parse OpenAI chat completion response
            try:
                data = r.json()
            except ValueError as e:
                log(f"Invalid JSON response from LM Studio: {e}", "ERR")
                return text, "Invalid response"

            choices = data.get("choices", [])
            if not choices:
                log("LM Studio returned empty choices array", "WARN")
                return text, "Empty response"

            message = choices[0].get("message", {})
            if not message:
                log("LM Studio response missing message field", "WARN")
                return text, "Invalid response format"

            result = message.get("content", "").strip()
            if not result:
                log("LM Studio returned empty content", "WARN")
                return text, "Empty response"

            result = self._clean_result(result)
            result = self._normalize_leading_spaces(result)

            log(f"LM Studio {mode.name} complete: {len(text)} -> {len(result)} chars", "OK")
            return (result if result else text), None

        except requests.exceptions.ConnectionError as e:
            log(f"LM Studio connection error: {e}", "ERR")
            return text, "LM Studio not responding"
        except requests.exceptions.Timeout:
            log(f"LM Studio timeout for mode {mode_id}", "ERR")
            return text, "Timeout"
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "unknown"
            log(f"LM Studio HTTP error {status}: {e}", "ERR")
            return text, f"HTTP error {status}"
        except Exception as e:
            log(f"Unexpected LM Studio error: {type(e).__name__}: {e}", "ERR")
            return text, self._truncate_error(e)

    # ─────────────────────────────────────────────────────────────────
    # Private methods
    # ─────────────────────────────────────────────────────────────────

    def _is_local_url(self, url: str) -> bool:
        """Check if URL points to localhost or local network."""
        host = urlparse(url).hostname
        if not host:
            return False

        # Allow localhost
        if host in ("localhost", "127.0.0.1", "::1"):
            return True

        # Allow local network IPs (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
        try:
            parts = host.split(".")
            if len(parts) == 4:
                if parts[0] == "192" and parts[1] == "168":
                    return True
                if parts[0] == "10":
                    return True
                if parts[0] == "172" and 16 <= int(parts[1]) <= 31:
                    return True
        except (ValueError, IndexError):
            pass

        return False

    def _check_model(self) -> Tuple[bool, str]:
        """Check if the configured model is available."""
        config = get_config()

        try:
            # Get list of available models
            models_url = config.lm_studio.check_url.rstrip("/") + "/v1/models"
            r = self._session.get(models_url, timeout=SERVICE_CHECK_TIMEOUT)

            if r.status_code != 200:
                return False, "Cannot list models"

            data = r.json()
            models = data.get("data", [])

            if not models:
                return False, "No models loaded - load a model in LM Studio"

            model_ids = [m.get("id", "") for m in models]

            # If user specified a model, check if it's available
            if config.lm_studio.model:
                if config.lm_studio.model in model_ids:
                    return True, config.lm_studio.model
                else:
                    return False, f"Model '{config.lm_studio.model}' not found. Available: {', '.join(model_ids[:3])}"

            # No model specified, use first available
            first_model = model_ids[0] if model_ids else "unknown"
            return True, first_model

        except Exception as e:
            return False, str(e)[:50]

    def _get_model_id(self) -> str:
        """Get the model ID to use for requests."""
        config = get_config()

        # If user specified a model, use it
        if config.lm_studio.model:
            return config.lm_studio.model

        # Otherwise, try to get the first available model
        try:
            models_url = config.lm_studio.check_url.rstrip("/") + "/v1/models"
            r = self._session.get(models_url, timeout=SERVICE_CHECK_TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                models = data.get("data", [])
                if models:
                    return models[0].get("id", "")
        except Exception:
            pass

        return ""


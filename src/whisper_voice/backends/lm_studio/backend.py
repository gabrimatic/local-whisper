"""
LM Studio backend implementation for proofreading.

Handles proofreading via LM Studio's OpenAI-compatible API.
"""

from typing import Tuple, Optional
from urllib.parse import urlparse

import requests

from ..base import GrammarBackend
from ..prompts import get_lm_studio_messages
from ...config import get_config
from ...utils import log, SERVICE_CHECK_TIMEOUT


class LMStudioBackend(GrammarBackend):
    """Proofreading backend using LM Studio's OpenAI-compatible API."""

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

        config = get_config()

        # Verify model is available
        model_ok, model_info = self._check_model()
        if model_ok:
            log(f"LM Studio ready ({model_info})", "OK")
            return True
        else:
            log(f"LM Studio: {model_info}", "WARN")
            return False

    def fix(self, text: str) -> Tuple[str, Optional[str]]:
        """Fix grammar using LM Studio."""
        config = get_config()

        if not self._is_local_url(config.lm_studio.url):
            return text, "LM Studio URL must be localhost or LAN"

        if not text or len(text.strip()) < 3:
            return text, None

        # If max_chars is 0 or negative, don't chunk (unlimited)
        if config.lm_studio.max_chars <= 0:
            return self._fix_chunk(text)

        max_chars = max(500, config.lm_studio.max_chars)
        chunks = self._split_text(text, max_chars)

        if len(chunks) == 1:
            return self._fix_chunk(text)

        # Process chunks
        results = []
        for idx, chunk in enumerate(chunks, start=1):
            fixed, err = self._fix_chunk(chunk)
            if err:
                log(f"LM Studio chunk {idx}/{len(chunks)} skipped: {err}", "WARN")
                results.append(chunk)
            else:
                results.append(fixed)

        return "\n\n".join(results), None

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

    def _fix_chunk(self, text: str) -> Tuple[str, Optional[str]]:
        """Fix grammar for a single chunk of text."""
        config = get_config()

        try:
            # Use shared timeout helper
            timeout = self._get_timeout(config.lm_studio.timeout)

            # Get model ID
            model_id = self._get_model_id()
            if not model_id:
                log("LM Studio: No model available for proofreading", "WARN")
                return text, "No model available"

            # Build request payload (OpenAI chat format)
            payload = {
                "model": model_id,
                "messages": get_lm_studio_messages(text),
                "temperature": 0.2,
                "max_tokens": config.lm_studio.max_tokens if config.lm_studio.max_tokens > 0 else 2048,
                "stream": False
            }

            r = self._session.post(
                config.lm_studio.url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer lm-studio"  # LM Studio doesn't enforce this but some SDKs expect it
                },
                timeout=timeout
            )
            r.raise_for_status()

            # Parse OpenAI chat completion response
            data = r.json()
            choices = data.get("choices", [])
            if not choices:
                return text, "Empty response"

            result = choices[0].get("message", {}).get("content", "").strip()
            result = self._clean_result(result)
            result = self._normalize_leading_spaces(result)

            return (result if result else text), None

        except requests.exceptions.ConnectionError:
            return text, "LM Studio not responding"
        except requests.exceptions.Timeout:
            return text, "Grammar fix timeout"
        except Exception as e:
            return text, self._truncate_error(e)

"""
Ollama backend implementation for grammar correction.

Handles grammar correction via local Ollama server.
"""

from typing import Tuple, Optional
from urllib.parse import urlparse

import requests

from ..base import GrammarBackend
from ..modes import get_mode, get_mode_ollama_prompt
from ...config import get_config
from ...utils import log, SERVICE_CHECK_TIMEOUT


class OllamaBackend(GrammarBackend):
    """Grammar correction backend using local Ollama server."""

    def __init__(self):
        self._session = requests.Session()

    @property
    def name(self) -> str:
        return "Ollama"

    def close(self) -> None:
        """Clean up resources and optionally unload model from memory."""
        config = get_config()

        # Only unload model if configured to do so
        if config.ollama.unload_on_exit and self._is_local_url(config.ollama.check_url):
            try:
                log("Unloading Ollama model from memory...", "INFO")
                # Use generate endpoint from check_url base to ensure correct endpoint
                unload_url = config.ollama.check_url.rstrip("/") + "/api/generate"
                self._session.post(
                    unload_url,
                    json={
                        "model": config.ollama.model,
                        "prompt": "",
                        "keep_alive": 0
                    },
                    timeout=5
                )
                log("Ollama model unloaded", "OK")
            except Exception as e:
                log(f"Failed to unload Ollama model: {e}", "WARN")

        try:
            self._session.close()
        except Exception:
            pass

    def running(self) -> bool:
        """Check if Ollama server is running."""
        config = get_config()

        if not self._is_local_url(config.ollama.check_url):
            log("Ollama URL must be localhost", "ERR")
            return False

        try:
            r = self._session.get(
                config.ollama.check_url,
                timeout=SERVICE_CHECK_TIMEOUT
            )
            return r.status_code == 200
        except (requests.RequestException, ConnectionError):
            return False

    def start(self) -> bool:
        """Check Ollama availability."""
        if self.running():
            config = get_config()
            log(f"Ollama ready ({config.ollama.model})", "OK")
            return True

        log("Ollama not running - start with: ollama serve", "WARN")
        return False

    def fix(self, text: str) -> Tuple[str, Optional[str]]:
        """Fix grammar using Ollama. Delegates to proofread mode."""
        return self.fix_with_mode(text, "proofread")

    def fix_with_mode(self, text: str, mode_id: str) -> Tuple[str, Optional[str]]:
        """Fix text using a specific transformation mode."""
        # Validate mode exists before processing
        mode = get_mode(mode_id)
        if not mode:
            log(f"Unknown mode requested: {mode_id}", "ERR")
            return text, f"Unknown mode: {mode_id}"

        config = get_config()

        if not self._is_local_url(config.ollama.url):
            log(f"Ollama URL not localhost: {config.ollama.url}", "ERR")
            return text, "Ollama URL must be localhost"

        if not text or len(text.strip()) < 3:
            log("Text too short for mode processing, returning as-is", "INFO")
            return text, None

        # Build prompt with error handling
        try:
            prompt = get_mode_ollama_prompt(mode_id, text)
        except ValueError as e:
            log(f"Failed to build prompt for mode {mode_id}: {e}", "ERR")
            return text, f"Prompt error: {e}"

        log(f"Ollama fix_with_mode: {mode.name} ({len(text)} chars)", "INFO")

        try:
            # Use shared timeout helper
            timeout = self._get_timeout(config.ollama.timeout)

            # Build model options
            options = {
                "temperature": 0.2,
                "top_p": 0.9,
                "repeat_penalty": 1.1,
            }

            # Only set num_ctx if specified (0 = use model default)
            if config.ollama.num_ctx > 0:
                options["num_ctx"] = config.ollama.num_ctx

            r = self._session.post(
                config.ollama.url,
                json={
                    "model": config.ollama.model,
                    "prompt": prompt,
                    "stream": False,
                    "keep_alive": config.ollama.keep_alive,
                    "options": options
                },
                timeout=timeout
            )
            r.raise_for_status()

            # Parse response
            try:
                response_data = r.json()
            except ValueError as e:
                log(f"Invalid JSON response from Ollama: {e}", "ERR")
                return text, "Invalid response"

            result = response_data.get('response', '').strip()
            if not result:
                log("Empty response from Ollama", "WARN")
                return text, "Empty response"

            result = self._clean_result(result)
            result = self._normalize_leading_spaces(result)

            log(f"Ollama {mode.name} complete: {len(text)} -> {len(result)} chars", "OK")
            return (result if result else text), None

        except requests.exceptions.ConnectionError as e:
            log(f"Ollama connection error: {e}", "ERR")
            return text, "Ollama not responding"
        except requests.exceptions.Timeout:
            log(f"Ollama timeout for mode {mode_id}", "ERR")
            return text, "Timeout"
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "unknown"
            log(f"Ollama HTTP error {status}: {e}", "ERR")
            return text, f"HTTP error {status}"
        except Exception as e:
            log(f"Unexpected Ollama error: {type(e).__name__}: {e}", "ERR")
            return text, self._truncate_error(e)

    # ─────────────────────────────────────────────────────────────────
    # Private methods
    # ─────────────────────────────────────────────────────────────────

    def _is_local_url(self, url: str) -> bool:
        """Check if URL points to localhost."""
        host = urlparse(url).hostname
        return host in ("localhost", "127.0.0.1", "::1")

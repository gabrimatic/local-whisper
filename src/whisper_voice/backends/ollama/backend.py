"""
Ollama backend implementation for grammar correction.

Handles grammar correction via local Ollama server.
"""

from typing import Tuple, Optional
from urllib.parse import urlparse

import requests

from ..base import GrammarBackend
from ..prompts import get_ollama_prompt
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
        """Fix grammar using Ollama."""
        config = get_config()

        if not self._is_local_url(config.ollama.url):
            return text, "Ollama URL must be localhost"

        if not text or len(text.strip()) < 3:
            return text, None

        # If max_chars is 0 or negative, don't chunk (unlimited)
        if config.ollama.max_chars <= 0:
            return self._fix_chunk(text)

        max_chars = max(500, config.ollama.max_chars)
        chunks = self._split_text(text, max_chars)

        if len(chunks) == 1:
            return self._fix_chunk(text)

        # Process chunks
        results = []
        for idx, chunk in enumerate(chunks, start=1):
            fixed, err = self._fix_chunk(chunk)
            if err:
                log(f"Ollama chunk {idx}/{len(chunks)} skipped: {err}", "WARN")
                results.append(chunk)
            else:
                results.append(fixed)

        return "\n\n".join(results), None

    # ─────────────────────────────────────────────────────────────────
    # Private methods
    # ─────────────────────────────────────────────────────────────────

    def _is_local_url(self, url: str) -> bool:
        """Check if URL points to localhost."""
        host = urlparse(url).hostname
        return host in ("localhost", "127.0.0.1", "::1")

    def _build_prompt(self, text: str) -> str:
        """Build the grammar correction prompt."""
        return get_ollama_prompt(text)

    def _predict_length(self, text: str, max_predict: int) -> int:
        """Estimate output length for the model."""
        # Output should be at least as long as input
        # Add 20% buffer for punctuation/formatting changes
        estimate = max(256, int(len(text) * 1.2))

        if max_predict <= 0:
            return estimate

        return min(max_predict, estimate)

    def _fix_chunk(self, text: str) -> Tuple[str, Optional[str]]:
        """Fix grammar for a single chunk of text."""
        config = get_config()

        try:
            prompt = self._build_prompt(text)

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

            # Only set num_predict if we have a limit
            if config.ollama.max_predict > 0:
                predicted = self._predict_length(text, config.ollama.max_predict)
                options["num_predict"] = predicted

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

            result = r.json().get('response', '').strip()
            result = self._clean_result(result)
            result = self._normalize_leading_spaces(result)

            return (result if result else text), None

        except requests.exceptions.ConnectionError:
            return text, "Ollama not responding"
        except requests.exceptions.Timeout:
            return text, "Grammar fix timeout"
        except Exception as e:
            return text, self._truncate_error(e)

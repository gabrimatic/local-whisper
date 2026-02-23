# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Apple Intelligence backend implementation for grammar correction.

Uses Apple's on-device Foundation Models via a Swift CLI helper.
The CLI runs in server mode, keeping the LanguageModelSession warm
for efficient repeated calls without reloading the model.
"""

import json
import select
import subprocess
import threading
from pathlib import Path
from typing import Tuple, Optional

from ..base import GrammarBackend, ERROR_TRUNCATE_LENGTH
from ..modes import get_mode
from ...config import get_config
from ...utils import log, SERVICE_CHECK_TIMEOUT


# Path to the Swift CLI helper
CLI_DIR = Path(__file__).parent / "cli"
CLI_BUILD_DIR = CLI_DIR / ".build" / "release"
CLI_BINARY = CLI_BUILD_DIR / "apple-ai-cli"

# Server startup timeout
SERVER_STARTUP_TIMEOUT = 10


class AppleIntelligenceBackend(GrammarBackend):
    """
    Grammar correction backend using Apple Intelligence.

    Uses a long-lived Swift CLI process in server mode to keep the
    LanguageModelSession warm, avoiding repeated model loading.
    """

    def __init__(self):
        self._available: Optional[bool] = None
        self._server_process: Optional[subprocess.Popen] = None
        self._server_lock = threading.Lock()

    @property
    def name(self) -> str:
        return "Apple Intelligence"

    def close(self) -> None:
        """Clean up resources and shut down the server process."""
        self._stop_server()

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
        """Check Apple Intelligence availability and start the server process."""
        if not CLI_BINARY.exists():
            log(f"CLI not built. Run: cd {CLI_DIR} && swift build -c release", "ERR")
            return False

        if not self.running():
            log("Apple Intelligence not available", "WARN")
            return False

        # Start the server process
        if self._start_server():
            log("Apple Intelligence ready (server mode)", "OK")
            return True

        log("Failed to start Apple Intelligence server", "ERR")
        return False

    def fix(self, text: str) -> Tuple[str, Optional[str]]:
        """Fix grammar using Apple Intelligence. Delegates to proofread mode."""
        return self.fix_with_mode(text, "proofread")

    def fix_with_mode(self, text: str, mode_id: str) -> Tuple[str, Optional[str]]:
        """Fix text using a specific transformation mode."""
        if not text or len(text.strip()) < 3:
            log("Text too short for mode processing, returning as-is", "INFO")
            return text, None

        # Validate mode exists before processing
        mode = get_mode(mode_id)
        if not mode:
            log(f"Unknown mode requested: {mode_id}", "ERR")
            return text, f"Unknown mode: {mode_id}"

        # Handle max_chars chunking
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

        # Ensure server is running
        if not self._ensure_server():
            log("Apple Intelligence server not running", "ERR")
            return text, "Server not running"

        timeout = config.apple_intelligence.timeout if config.apple_intelligence.timeout > 0 else None

        # Build request for server mode using mode-specific prompts
        try:
            request = {
                "system": mode.system_prompt,
                "user_prompt": mode.user_prompt_template,
                "text": text
            }
        except Exception as e:
            log(f"Failed to build request for mode {mode_id}: {e}", "ERR")
            return text, f"Request build error: {e}"

        response, err = self._send_request(request, timeout=timeout)

        if err:
            log(f"Apple Intelligence server error for {mode.name}: {err}", "ERR")
            return text, err[:ERROR_TRUNCATE_LENGTH]

        if response is None:
            log("No response received from Apple Intelligence server", "ERR")
            return text, "No response from server"

        if not response.get("success", False):
            error_msg = response.get("error", "Unknown error")
            if "unavailable" in error_msg.lower() or "not available" in error_msg.lower():
                log("Apple Intelligence reported unavailable", "ERR")
                return text, "Apple Intelligence not available"
            log(f"Apple Intelligence error: {error_msg}", "ERR")
            return text, error_msg[:ERROR_TRUNCATE_LENGTH]

        result = response.get("result", "").strip()
        if not result:
            log("Apple Intelligence returned empty result", "WARN")
            return text, "Empty response"

        result = self._clean_result(result)
        result = self._normalize_leading_spaces(result)

        log(f"Apple Intelligence {mode.name} complete: {len(text)} -> {len(result)} chars", "OK")
        return (result if result else text), None

    # ─────────────────────────────────────────────────────────────────
    # Server management
    # ─────────────────────────────────────────────────────────────────

    def _start_server(self) -> bool:
        """Start the CLI server process."""
        with self._server_lock:
            if self._server_process is not None:
                # Check if still running
                if self._server_process.poll() is None:
                    return True
                # Process died, clean up
                self._server_process = None

            try:
                self._server_process = subprocess.Popen(
                    [str(CLI_BINARY), "serve"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,  # Line buffered
                )

                # Wait for READY signal on stderr
                ready = False
                timeout_remaining = SERVER_STARTUP_TIMEOUT

                while timeout_remaining > 0:
                    # Check if process died
                    if self._server_process.poll() is not None:
                        stderr_output = self._server_process.stderr.read()
                        log(f"Server process exited: {stderr_output}", "ERR")
                        self._server_process = None
                        return False

                    # Use select to check for data with timeout
                    rlist, _, _ = select.select([self._server_process.stderr], [], [], 0.5)
                    if rlist:
                        line = self._server_process.stderr.readline()
                        if "READY" in line:
                            ready = True
                            break

                    timeout_remaining -= 0.5

                if not ready:
                    log("Server startup timeout", "ERR")
                    self._stop_server()
                    return False

                return True

            except Exception as e:
                log(f"Failed to start server: {e}", "ERR")
                self._server_process = None
                return False

    def _stop_server(self) -> None:
        """Stop the CLI server process."""
        with self._server_lock:
            if self._server_process is not None:
                try:
                    # Close stdin to signal server to exit
                    if self._server_process.stdin:
                        self._server_process.stdin.close()
                    # Wait briefly for graceful exit
                    self._server_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Force kill if needed
                    self._server_process.kill()
                    self._server_process.wait()
                except Exception:
                    pass
                finally:
                    self._server_process = None

    def _ensure_server(self) -> bool:
        """Ensure the server is running, restart if needed."""
        with self._server_lock:
            if self._server_process is not None:
                if self._server_process.poll() is None:
                    return True
                # Process died
                self._server_process = None

        # Restart server
        return self._start_server()

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
        Run the Apple AI CLI with given arguments (for one-shot commands like 'check').

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

    def _send_request(self, request: dict, timeout: Optional[float] = None) -> Tuple[Optional[dict], Optional[str]]:
        """
        Send a request to the server process.

        Returns: (response_dict, error_message)
        """
        if not self._ensure_server():
            return None, "Server not running"

        try:
            with self._server_lock:
                if self._server_process is None:
                    return None, "Server not running"

                # Send request as JSON line
                json_line = json.dumps(request) + "\n"
                self._server_process.stdin.write(json_line)
                self._server_process.stdin.flush()

                # Read response with timeout
                if timeout and timeout > 0:
                    rlist, _, _ = select.select([self._server_process.stdout], [], [], timeout)
                    if not rlist:
                        return None, "Timeout waiting for response"

                response_line = self._server_process.stdout.readline()
                if not response_line:
                    # Server died - mark for cleanup (still inside lock)
                    self._server_process = None
                    return None, "Server process died"

                response = json.loads(response_line)
                return response, None

        except json.JSONDecodeError as e:
            return None, f"Invalid JSON response: {e}"
        except Exception as e:
            return None, str(e)


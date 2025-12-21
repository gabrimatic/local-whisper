"""
WhisperKit integration for Local Whisper.

Handles speech-to-text transcription via local WhisperKit server.
"""

import atexit
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from .config import get_config
from .utils import log, TRANSCRIBE_CHECK_TIMEOUT

# Startup timeout for WhisperKit server
STARTUP_TIMEOUT = 90


class Whisper:
    """WhisperKit client for speech-to-text transcription."""

    def __init__(self):
        self._session = requests.Session()
        self._process = None
        atexit.register(self.close)

    def _is_local_url(self, url: str) -> bool:
        host = urlparse(url).hostname
        return host in ("localhost", "127.0.0.1", "::1")

    def running(self) -> bool:
        """Check if WhisperKit server is running."""
        config = get_config()
        if not self._is_local_url(config.whisper.check_url):
            log("Whisper URL must be localhost", "ERR")
            return False
        try:
            r = self._session.get(config.whisper.check_url, timeout=TRANSCRIBE_CHECK_TIMEOUT)
            return r.status_code == 200
        except (requests.RequestException, ConnectionError):
            return False

    def start(self) -> bool:
        """Start WhisperKit server if not running."""
        config = get_config()

        if not self._is_local_url(config.whisper.check_url):
            log("Whisper URL must be localhost", "ERR")
            return False

        if self.running():
            log("Whisper server ready", "OK")
            return True

        log("Starting WhisperKit server...")
        try:
            self._process = subprocess.Popen(
                ['whisperkit-cli', 'serve', '--model', config.whisper.model],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
        except FileNotFoundError:
            log("whisperkit-cli not found! Run: brew install whisperkit-cli", "ERR")
            return False

        for i in range(STARTUP_TIMEOUT):
            time.sleep(1)
            if self.running():
                log("Whisper server ready", "OK")
                return True
            if i % 10 == 9:
                log(f"Loading Whisper model... ({i+1}s)")

        log("Whisper server timeout", "ERR")
        return False

    def transcribe(self, path: Path) -> tuple:
        """
        Transcribe audio file.

        Returns: (text, error) tuple. On success, error is None.
        """
        config = get_config()

        if not self._is_local_url(config.whisper.url):
            return None, "Whisper URL must be localhost"

        if not path or not path.exists():
            return None, "No audio"

        try:
            with open(path, 'rb') as f:
                data = {'model': config.whisper.model}
                if config.whisper.language and config.whisper.language != "auto":
                    data['language'] = config.whisper.language
                # timeout=0 means unlimited read, but keep reasonable connect timeout
                if config.whisper.timeout > 0:
                    timeout = config.whisper.timeout
                else:
                    timeout = (10, None)  # (connect_timeout, read_timeout=unlimited)
                r = self._session.post(
                    config.whisper.url,
                    files={'file': (path.name, f, 'audio/wav')},
                    data=data,
                    timeout=timeout
                )
                r.raise_for_status()
                text = r.json().get('text', '').strip()
                return (text, None) if text else (None, "Empty")
        except requests.exceptions.ConnectionError:
            return None, "Whisper not responding"
        except requests.exceptions.Timeout:
            return None, "Timeout"
        except Exception as e:
            return None, str(e)[:30]

    def close(self):
        """Clean up resources and kill WhisperKit server."""
        try:
            self._session.close()
        except Exception:
            pass
        if self._process and self._process.poll() is None:
            log("Killing WhisperKit server...", "INFO")
            try:
                # Use SIGKILL to ensure immediate termination
                self._process.kill()
                self._process.wait(timeout=3)
                log("WhisperKit server killed", "OK")
            except Exception as e:
                log(f"Failed to kill WhisperKit: {e}", "ERR")
                # Try to kill via pkill as fallback
                try:
                    import subprocess
                    subprocess.run(['pkill', '-9', '-f', 'whisperkit-cli'],
                                   timeout=2, capture_output=True)
                    log("WhisperKit killed via pkill", "OK")
                except Exception:
                    pass
            finally:
                self._process = None

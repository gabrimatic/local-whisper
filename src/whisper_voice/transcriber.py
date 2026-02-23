# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
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
STARTUP_TIMEOUT = 300


class Whisper:
    """WhisperKit client for speech-to-text transcription."""

    def __init__(self):
        self._session = requests.Session()
        self._process = None
        self._last_request_time: float = 0
        atexit.register(self.close)

    def _is_local_url(self, url: str) -> bool:
        host = urlparse(url).hostname
        return host in ("localhost", "127.0.0.1", "::1")

    def _ensure_fresh_session(self) -> None:
        """Refresh session if idle too long to prevent connection staleness."""
        idle_time = time.time() - self._last_request_time
        if self._last_request_time > 0 and idle_time > 300:  # 5 minutes
            log(f"Session idle {idle_time:.0f}s, refreshing")
            self._session.close()
            self._session = requests.Session()

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
                [
                    'whisperkit-cli', 'serve',
                    '--model', config.whisper.model,
                    '--compression-ratio-threshold', str(config.whisper.compression_ratio_threshold),
                    '--no-speech-threshold', str(config.whisper.no_speech_threshold),
                    '--logprob-threshold', str(config.whisper.logprob_threshold),
                    '--first-token-log-prob-threshold', '-1.5',
                    '--temperature-increment-on-fallback', '0.2',
                    '--temperature-fallback-count', str(config.whisper.temperature_fallback_count),
                ],
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

                # Use prompt from config (settings writes resolved text on save)
                preset = config.whisper.prompt_preset
                if preset != "none":
                    resolved_prompt = config.whisper.prompt
                    if resolved_prompt and resolved_prompt.strip():
                        data['prompt'] = resolved_prompt

                # Temperature for decoding
                data['temperature'] = str(config.whisper.temperature)

                # Request verbose JSON for segment-level filtering
                data['response_format'] = 'verbose_json'

                # timeout=0 means unlimited read, but keep reasonable connect timeout
                if config.whisper.timeout > 0:
                    timeout = config.whisper.timeout
                else:
                    timeout = (10, 120)  # (connect_timeout=10s, read_timeout=120s)

                # Retry with session refresh on connection errors
                for attempt in range(2):
                    try:
                        self._ensure_fresh_session()
                        r = self._session.post(
                            config.whisper.url,
                            files={'file': (path.name, f, 'audio/wav')},
                            data=data,
                            timeout=timeout
                        )
                        self._last_request_time = time.time()
                        r.raise_for_status()

                        try:
                            body = r.json()
                        except Exception:
                            body = {}

                        # Try verbose_json segment filtering first
                        segments = body.get('segments')
                        if segments is not None:
                            kept = []
                            for seg in segments:
                                no_speech_prob = seg.get('no_speech_prob', 0.0)
                                compression_ratio = seg.get('compression_ratio', 1.0)
                                if no_speech_prob > config.whisper.no_speech_threshold:
                                    log(f"Dropping segment (no_speech_prob={no_speech_prob:.2f})")
                                    continue
                                if compression_ratio > config.whisper.compression_ratio_threshold:
                                    log(f"Dropping segment (compression_ratio={compression_ratio:.2f})")
                                    continue
                                seg_text = seg.get('text', '').strip()
                                if seg_text:
                                    kept.append(seg_text)
                            if kept:
                                text = ' '.join(kept).strip()
                                return (text, None) if text else (None, "Empty")
                            elif segments:
                                # All segments were filtered out
                                log("All segments filtered (no speech / repetition)")
                                return None, "Empty"
                            # segments list was empty, fall through to plain text

                        # Fall back to plain text field
                        text = body.get('text', '').strip()
                        return (text, None) if text else (None, "Empty")
                    except requests.exceptions.ConnectionError as e:
                        if attempt == 0:
                            log(f"Connection error, refreshing session: {e}")
                            self._session.close()
                            self._session = requests.Session()
                            f.seek(0)  # Reset file position for retry
                            continue
                        raise
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

        log("Killing WhisperKit server...", "INFO")

        # First try to kill tracked process if we have one
        if self._process and self._process.poll() is None:
            try:
                self._process.kill()
                self._process.wait(timeout=3)
                log("WhisperKit server killed", "OK")
            except Exception as e:
                log(f"Failed to kill tracked process: {e}", "WARN")
            finally:
                self._process = None

        # Always use pkill to ensure any whisperkit-cli process is killed
        # (covers cases where server was already running before app started)
        try:
            result = subprocess.run(['pkill', '-9', '-f', 'whisperkit-cli serve'],
                                   timeout=2, capture_output=True)
            if result.returncode == 0:
                log("WhisperKit server killed via pkill", "OK")
        except Exception:
            pass

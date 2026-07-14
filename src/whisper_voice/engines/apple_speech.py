# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Apple SpeechTranscriber engine backed by the native Speech framework."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional, Tuple

from ..config import get_config
from ..utils import log
from .base import TranscriptionEngine

HELPER_NAME = "LocalWhisperSpeech"


def apple_speech_helper_candidates() -> tuple[Path, ...]:
    """Return native-helper locations in runtime priority order."""
    repo_root = Path(__file__).resolve().parents[3]
    return (
        Path.home() / ".whisper" / "LocalWhisperUI.app" / "Contents" / "MacOS" / HELPER_NAME,
        repo_root / "LocalWhisperUI" / ".build" / "release" / HELPER_NAME,
        Path(sys.prefix).parent / "LocalWhisperUI.app" / "Contents" / "MacOS" / HELPER_NAME,
    )


def find_apple_speech_helper() -> Optional[Path]:
    return next((path for path in apple_speech_helper_candidates() if path.is_file()), None)


def apple_speech_model_status() -> dict[str, Any]:
    """Return Apple's per-app asset reservation state without downloading it."""
    engine = AppleSpeechEngine()
    try:
        return engine._run_helper("status")
    except Exception as exc:
        return {
            "availability": "unavailable",
            "installed": False,
            "locale": get_config().apple_speech.locale,
            "message": str(exc),
        }


class AppleSpeechEngine(TranscriptionEngine):
    """Transcribe local audio through Apple's on-device SpeechTranscriber."""

    def __init__(self, helper_path: Path | None = None):
        self._helper_path = helper_path
        self._ready = False
        self.last_error = ""

    @property
    def name(self) -> str:
        return "Apple SpeechTranscriber"

    @property
    def supports_long_audio(self) -> bool:
        return True

    def _resolved_helper(self) -> Optional[Path]:
        if self._helper_path is not None:
            return self._helper_path if self._helper_path.is_file() else None
        return find_apple_speech_helper()

    def _run_helper(self, command: str, path: Path | None = None) -> dict[str, Any]:
        helper = self._resolved_helper()
        if helper is None:
            raise RuntimeError(
                "Apple SpeechTranscriber helper is missing. Run 'wh build' to install it."
            )
        cfg = get_config().apple_speech
        args = [str(helper), command, "--locale", cfg.locale]
        if path is not None:
            args.append(str(path))
        timeout = cfg.timeout if cfg.timeout > 0 else None
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Apple SpeechTranscriber timed out after {int(exc.timeout)} seconds."
            ) from exc
        try:
            payload = json.loads(result.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "Apple SpeechTranscriber returned an invalid response."
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Apple SpeechTranscriber returned an invalid response.")
        if result.returncode != 0 or payload.get("ok") is not True:
            message = str(payload.get("message") or result.stderr or "Apple SpeechTranscriber failed.")
            raise RuntimeError(message.strip())
        return payload

    def start(self) -> bool:
        try:
            payload = self._run_helper("install")
            if payload.get("availability") != "installed" or payload.get("installed") is not True:
                raise RuntimeError(
                    str(payload.get("message") or "Apple SpeechTranscriber model is not installed.")
                )
            self._ready = True
            self.last_error = ""
            log("Apple SpeechTranscriber ready", "OK")
            return True
        except Exception as exc:
            self._ready = False
            self.last_error = str(exc)
            log(self.last_error, "ERR")
            return False

    def running(self) -> bool:
        return self._ready and self._resolved_helper() is not None

    def transcribe(self, path: Path) -> Tuple[Optional[str], Optional[str]]:
        if not path or not path.exists():
            return None, "No audio"
        try:
            payload = self._run_helper("transcribe", path)
            transcript = str(payload.get("transcript") or "").strip()
            if not transcript:
                return None, "Apple SpeechTranscriber did not detect speech in the recording."
            return transcript, None
        except Exception as exc:
            return None, str(exc)

    def close(self) -> None:
        self._ready = False

    def release(self) -> bool:
        """Release this app's Apple-managed locale reservation."""
        try:
            self._run_helper("release")
            self._ready = False
            self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False

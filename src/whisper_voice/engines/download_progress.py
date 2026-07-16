# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Download progress tracking for HuggingFace-backed assets.

Streams `download_progress` IPC messages so Settings panels can render inline
progress bars during engine/TTS downloads instead of a modal "loading"
dialogue. Works by:

  1. Polling the on-disk cache directory every 500 ms and emitting
     bytes / total / percent / phase so the UI can animate a definite bar.

Polling vs hooking tqdm keeps the integration surface small: the various
`*-mlx` wrappers (parakeet-mlx, qwen3-asr-mlx, kokoro-mlx) all funnel through
`huggingface_hub.snapshot_download` into the same cache layout, so we only need
to watch the blobs directory regardless of which engine is loading. The total
byte count is optional; Settings can still show an active indeterminate bar
with aggregate downloaded bytes when a size preflight is unavailable or skipped.
"""

import threading
from pathlib import Path
from typing import Callable, Dict, Optional

from .status import _dir_size_bytes

POLL_INTERVAL_SEC = 0.5

_SIZE_CACHE: Dict[str, Optional[int]] = {}
_SIZE_CACHE_LOCK = threading.Lock()


def expected_size_bytes(hf_repo: str) -> Optional[int]:
    """Sum file sizes for a HuggingFace repo. Cached per-session.

    Returns None on any failure (offline, rate-limited, unknown repo). The
    caller is expected to fall back to indeterminate progress rather than
    bailing out — a missing preflight must never block the download itself.
    """
    with _SIZE_CACHE_LOCK:
        if hf_repo in _SIZE_CACHE:
            return _SIZE_CACHE[hf_repo]
    total: Optional[int]
    try:
        from huggingface_hub import model_info
        # Bounded: this preflight runs on the engine-switch thread before the
        # download watcher starts. A stalled network must degrade to an
        # indeterminate bar, not hang the switch.
        info = model_info(hf_repo, files_metadata=True, timeout=5)
        siblings = getattr(info, "siblings", None) or []
        total_bytes = 0
        for sib in siblings:
            size = getattr(sib, "size", None)
            if size:
                total_bytes += int(size)
        total = total_bytes if total_bytes > 0 else None
    except Exception:
        total = None
    with _SIZE_CACHE_LOCK:
        _SIZE_CACHE[hf_repo] = total
    return total


class DownloadWatcher:
    """Polls a cache directory and streams progress over IPC.

    Lifecycle:
      watcher = DownloadWatcher(target, cache_path, total, ipc_send)
      watcher.start()                 # begin polling
      watcher.set_phase("downloading")
      ...                             # heavy work
      watcher.set_phase("warming")
      ...                             # heavy work
      watcher.finish()                # emits 'ready' and joins
      # or
      watcher.finish(error="...")     # emits 'error' and joins
      watcher.finish(error="...", phase="canceled")

    Size is reported as aggregate cache bytes. That lets a resumed partial
    download show real progress instead of sitting at zero because the partial
    files existed before this watcher started.
    """

    def __init__(
        self,
        target_id: str,
        cache_path: Path,
        total_bytes: Optional[int],
        ipc_send: Callable[[dict], None],
    ):
        self._target_id = target_id
        self._cache_path = cache_path
        self._total = int(total_bytes) if total_bytes else 0
        self._ipc_send = ipc_send
        self._phase = "preparing"
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._emit()
        self._thread = threading.Thread(
            target=self._run, name=f"dl-watch-{self._target_id}", daemon=True
        )
        self._thread.start()

    def set_phase(self, phase: str) -> None:
        self._phase = phase
        self._emit()

    def finish(self, error: Optional[str] = None, phase: Optional[str] = None) -> None:
        if phase is not None:
            self._phase = phase
        elif error is not None:
            self._phase = "error"
        else:
            self._phase = "ready"
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._emit(error=error)

    def _emit(self, error: Optional[str] = None) -> None:
        bytes_now = _safe_size(self._cache_path)
        if self._total > 0:
            percent = min(1.0, bytes_now / self._total)
        else:
            percent = 0.0
        msg = {
            "type": "download_progress",
            "target": self._target_id,
            "bytes": bytes_now,
            "total": self._total,
            "percent": percent,
            "phase": self._phase,
        }
        if error:
            msg["error"] = error
        try:
            self._ipc_send(msg)
        except Exception:
            pass

    def _run(self) -> None:
        while not self._stop.wait(POLL_INTERVAL_SEC):
            if self._phase == "downloading":
                self._emit()


def _safe_size(path: Path) -> int:
    try:
        if not path.exists():
            return 0
        return _dir_size_bytes(path)
    except Exception:
        return 0


def kokoro_cache_path(hf_repo: str) -> Path:
    """Resolve the HF cache directory for a repo id (org/name → models--org--name)."""
    from .status import MODEL_DIR
    folder = "models--" + hf_repo.replace("/", "--")
    return MODEL_DIR / folder

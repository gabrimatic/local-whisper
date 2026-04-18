# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Engine model management helpers.

Reports per-engine cache status (downloaded, size on disk, cache path) so the
UI can tell users what's on disk vs what will download on next switch, and
offers cache removal so users can reclaim gigabytes without leaving the app.
"""

import os
import shutil
from pathlib import Path
from typing import Dict, Optional

MODEL_DIR = Path.home() / ".whisper" / "models"

# Engine id → (HF repo id, cache dir name, warm sentinel filename).
# `hf_repo` is what HuggingFace writes as ``models--<org>--<name>``.
ENGINE_MODEL_MAP: Dict[str, Dict[str, str]] = {
    "parakeet_v3": {
        "hf_repo": "mlx-community/parakeet-tdt-0.6b-v3",
        "cache_dir": "models--mlx-community--parakeet-tdt-0.6b-v3",
        "warm_sentinel": ".parakeet_v3_warmed",
    },
    "qwen3_asr": {
        "hf_repo": "mlx-community/Qwen3-ASR-1.7B-bf16",
        "cache_dir": "models--mlx-community--Qwen3-ASR-1.7B-bf16",
        "warm_sentinel": ".qwen3_warmed",
    },
    # whisperkit: models live under WhisperKit's own cache; not managed here.
}


def _dir_size_bytes(path: Path) -> int:
    """Recursive size in bytes, following HF's symlink-heavy cache layout."""
    total = 0
    for root, _dirs, files in os.walk(path, followlinks=False):
        for f in files:
            try:
                fp = Path(root) / f
                total += fp.stat().st_size
            except OSError:
                continue
    return total


def _bytes_to_mb(n: int) -> int:
    return int(round(n / (1024 * 1024)))


def engine_model_status(engine_id: str) -> Dict:
    """Return cache status for a single engine.

    Keys:
      downloaded: bool -- weights present on disk
      size_mb:    int|None -- megabytes used (None if unknown)
      warmed:     bool -- MLX graph cache primed (sentinel file exists)
      cache_dir:  str|None -- absolute path to the HF cache folder
      hf_repo:    str|None -- which HF repo the engine uses
    """
    info = ENGINE_MODEL_MAP.get(engine_id)
    if info is None:
        return {
            "downloaded": False,
            "size_mb": None,
            "warmed": False,
            "cache_dir": None,
            "hf_repo": None,
        }

    cache_path = MODEL_DIR / info["cache_dir"]
    warmed_path = MODEL_DIR / info["warm_sentinel"]
    downloaded = cache_path.is_dir() and any(cache_path.iterdir())
    size_mb = _bytes_to_mb(_dir_size_bytes(cache_path)) if downloaded else 0
    return {
        "downloaded": downloaded,
        "size_mb": size_mb if downloaded else 0,
        "warmed": warmed_path.exists(),
        "cache_dir": str(cache_path),
        "hf_repo": info["hf_repo"],
    }


def all_engine_statuses(active_id: Optional[str]) -> Dict[str, Dict]:
    """Return a mapping of engine_id → status dict, including `active` flag."""
    from . import ENGINE_REGISTRY
    out: Dict[str, Dict] = {}
    for engine_id, info in ENGINE_REGISTRY.items():
        status = engine_model_status(engine_id)
        status["id"] = engine_id
        status["name"] = info.name
        status["description"] = info.description
        status["active"] = (engine_id == active_id)
        out[engine_id] = status
    return out


def remove_engine_cache(engine_id: str) -> bool:
    """Delete the on-disk weights + warm sentinel for an engine. Returns True if anything removed."""
    info = ENGINE_MODEL_MAP.get(engine_id)
    if info is None:
        return False
    removed = False
    cache_path = MODEL_DIR / info["cache_dir"]
    if cache_path.is_dir():
        shutil.rmtree(cache_path, ignore_errors=True)
        removed = True
    warmed_path = MODEL_DIR / info["warm_sentinel"]
    if warmed_path.exists():
        try:
            warmed_path.unlink()
            removed = True
        except OSError:
            pass
    return removed

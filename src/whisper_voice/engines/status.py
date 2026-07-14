# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Engine model management helpers.

Reports per-engine cache status (downloaded, size on disk, cache path) so the
UI can tell users what's on disk vs what will download on next switch, and
offers cache removal so users can reclaim gigabytes without leaving the app.
"""

import math
import os
import shutil
from pathlib import Path
from typing import Dict, Iterable, Optional

MODEL_DIR = Path.home() / ".whisper" / "models"

# Engine id → Hugging Face repo metadata.
# `hf_repo` is what HuggingFace writes as ``models--<org>--<name>``.
ENGINE_MODEL_MAP: Dict[str, Dict[str, object]] = {
    "parakeet_v3": {
        "hf_repo": "mlx-community/parakeet-tdt-0.6b-v3",
        "warm_sentinel": ".parakeet_v3_warmed",
        "required_files": ("config.json", "model.safetensors"),
    },
    "qwen3_asr": {
        "hf_repo": "mlx-community/Qwen3-ASR-1.7B-bf16",
        "warm_sentinel": ".qwen3_warmed",
        "required_files": ("config.json", "model.safetensors"),
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
    if n <= 0:
        return 0
    return max(1, int(math.ceil(n / (1024 * 1024))))


def hf_cache_complete(cache_path: Path, required_files: Iterable[str]) -> bool:
    """Return True only when a HF cache has a usable snapshot.

    Hugging Face creates refs, locks, and partial blob files before the model is
    usable. A cache directory existing is therefore not enough; the UI should
    show partial/resumable until one snapshot contains the minimum files the
    engine needs to load.
    """
    if not cache_path.is_dir():
        return False
    snapshots_dir = cache_path / "snapshots"
    if not snapshots_dir.is_dir():
        return False
    required = tuple(required_files)
    for snapshot in snapshots_dir.iterdir():
        if not snapshot.is_dir():
            continue
        complete = True
        for rel in required:
            candidate = snapshot / rel
            try:
                if not candidate.is_file() or candidate.stat().st_size <= 0:
                    complete = False
                    break
            except OSError:
                complete = False
                break
        if complete:
            return True
    return False


def hf_cache_dir_name(hf_repo: str) -> str:
    """Return Hugging Face's cache folder name for a repo id."""
    return "models--" + hf_repo.replace("/", "--")


def _configured_hf_repo(engine_id: str) -> Optional[str]:
    try:
        from ..config import get_config

        cfg = get_config()
        if engine_id == "parakeet_v3":
            return str(cfg.parakeet.model)
        if engine_id == "qwen3_asr":
            return str(cfg.qwen3_asr.model)
    except Exception:
        pass
    info = ENGINE_MODEL_MAP.get(engine_id)
    return str(info["hf_repo"]) if info and info.get("hf_repo") else None


def engine_model_metadata(engine_id: str) -> Optional[Dict[str, object]]:
    """Return managed HF model metadata for an engine using current config."""
    info = ENGINE_MODEL_MAP.get(engine_id)
    if info is None:
        return None
    hf_repo = _configured_hf_repo(engine_id) or str(info["hf_repo"])
    return {
        "hf_repo": hf_repo,
        "cache_dir": hf_cache_dir_name(hf_repo),
        "warm_sentinel": info["warm_sentinel"],
        "required_files": tuple(info.get("required_files", ())),
    }


def engine_model_status(engine_id: str) -> Dict:
    """Return cache status for a single engine.

    Keys:
      downloaded: bool -- weights present on disk
      size_mb:    int|None -- megabytes used (None if unknown)
      warmed:     bool -- MLX graph cache primed (sentinel file exists)
      cache_dir:  str|None -- absolute path to the HF cache folder
      hf_repo:    str|None -- which HF repo the engine uses
    """
    if engine_id == "apple_speech":
        from .apple_speech import apple_speech_model_status

        native = apple_speech_model_status()
        availability = str(native.get("availability") or "unavailable")
        installed = availability == "installed" and native.get("installed") is True
        return {
            "downloaded": installed,
            "download_status": availability,
            "size_mb": None,
            "warmed": installed,
            "cache_dir": None,
            "hf_repo": None,
            "managed_by": "apple",
            "available": availability != "unavailable",
            "removable": installed,
            "locale": native.get("locale"),
            "message": native.get("message"),
        }

    info = engine_model_metadata(engine_id)
    if info is None:
        return {
            "downloaded": False,
            "size_mb": None,
            "warmed": False,
            "cache_dir": None,
            "hf_repo": None,
        }

    cache_path = MODEL_DIR / str(info["cache_dir"])
    warmed_path = MODEL_DIR / str(info["warm_sentinel"])
    size_bytes = _dir_size_bytes(cache_path) if cache_path.exists() else 0
    required_files = tuple(info.get("required_files", ()))
    downloaded = hf_cache_complete(cache_path, required_files)
    download_status = "downloaded" if downloaded else ("partial" if size_bytes > 0 else "missing")
    size_mb = _bytes_to_mb(size_bytes)
    return {
        "downloaded": downloaded,
        "download_status": download_status,
        "size_mb": size_mb,
        "warmed": warmed_path.exists(),
        "cache_dir": str(cache_path),
        "hf_repo": info["hf_repo"],
    }


def ensure_engine_model_cached(engine_id: str) -> None:
    """Download a managed engine's HF snapshot if it is missing or partial."""
    info = engine_model_metadata(engine_id)
    if info is None:
        return
    status = engine_model_status(engine_id)
    if status.get("downloaded", False):
        return

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    old_cache = os.environ.get("HF_HUB_CACHE")
    old_telemetry = os.environ.get("HF_HUB_DISABLE_TELEMETRY")
    old_offline = os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ["HF_HUB_CACHE"] = str(MODEL_DIR)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(repo_id=str(info["hf_repo"]), cache_dir=str(MODEL_DIR))
    finally:
        if old_cache is None:
            os.environ.pop("HF_HUB_CACHE", None)
        else:
            os.environ["HF_HUB_CACHE"] = old_cache
        if old_telemetry is None:
            os.environ.pop("HF_HUB_DISABLE_TELEMETRY", None)
        else:
            os.environ["HF_HUB_DISABLE_TELEMETRY"] = old_telemetry
        if old_offline is not None:
            os.environ["HF_HUB_OFFLINE"] = old_offline

    refreshed = engine_model_status(engine_id)
    if not refreshed.get("downloaded", False):
        raise RuntimeError(f"{engine_id} model download did not finish cleanly")


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
    if engine_id == "apple_speech":
        from .apple_speech import AppleSpeechEngine

        engine = AppleSpeechEngine()
        status = engine_model_status(engine_id)
        if not status.get("downloaded", False):
            return False
        if not engine.release():
            raise RuntimeError(engine.last_error or "Apple speech model reservation could not be released.")
        return True

    info = engine_model_metadata(engine_id)
    if info is None:
        return False
    removed = False
    cache_path = MODEL_DIR / str(info["cache_dir"])
    if cache_path.is_dir():
        shutil.rmtree(cache_path, ignore_errors=True)
        removed = True
    warmed_path = MODEL_DIR / str(info["warm_sentinel"])
    if warmed_path.exists():
        try:
            warmed_path.unlink()
            removed = True
        except OSError:
            pass
    return removed

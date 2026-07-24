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

from .qwen3_models import DEFAULT_QWEN3_ASR_MODEL, qwen3_warm_sentinel_name

MODEL_DIR = Path.home() / ".whisper" / "models"

# WhisperKit is not an HF-cache engine: whisperkit-cli downloads Core ML model
# packages via its own downloader (ignoring HF_HUB_CACHE) into
# ``~/Documents/huggingface/models/argmaxinc/whisperkit-coreml/<prefix>_<model>``.
# We still manage that directory here so its card reports size and gets a
# Remove button like every other engine — but deliberately WITHOUT an
# ``hf_repo``, so the switch path never attaches an HF DownloadWatcher or tries
# to snapshot_download it (the argmaxinc repo hosts many models; whisperkit-cli
# fetches only the one variant on `serve`).
WHISPERKIT_MODELS_DIR = (
    Path.home() / "Documents" / "huggingface" / "models" / "argmaxinc" / "whisperkit-coreml"
)
# whisperkit.py launches `serve --model <model>` without --model-prefix, so the
# default prefix applies. Each model dir holds these Core ML packages.
WHISPERKIT_MODEL_PREFIX = "openai"
WHISPERKIT_REQUIRED = (
    "AudioEncoder.mlmodelc",
    "TextDecoder.mlmodelc",
    "MelSpectrogram.mlmodelc",
)

# Engine id → Hugging Face repo metadata.
# `hf_repo` is what HuggingFace writes as ``models--<org>--<name>``.
ENGINE_MODEL_MAP: Dict[str, Dict[str, object]] = {
    "parakeet_v3": {
        "hf_repo": "mlx-community/parakeet-tdt-0.6b-v3",
        "warm_sentinel": ".parakeet_v3_warmed",
        "required_files": ("config.json", "model.safetensors"),
    },
    "qwen3_asr": {
        "hf_repo": DEFAULT_QWEN3_ASR_MODEL,
        "warm_sentinel": qwen3_warm_sentinel_name(DEFAULT_QWEN3_ASR_MODEL),
        "required_files": ("config.json", "model.safetensors"),
    },
    # whisperkit is handled separately (see WHISPERKIT_* above): its weights are
    # Core ML packages outside the HF cache, so it stays out of this HF map.
}


def _whisperkit_model_dir() -> Optional[Path]:
    """Directory where whisperkit-cli stores the currently configured model.

    Returns None when the config can't be read. The path is deterministic from
    ``config.whisper.model`` and the default ``openai`` prefix — it may not
    exist yet if the model was never downloaded.
    """
    try:
        from ..config import get_config

        model = str(get_config().whisper.model).strip()
    except Exception:
        return None
    if not model:
        return None
    return WHISPERKIT_MODELS_DIR / f"{WHISPERKIT_MODEL_PREFIX}_{model}"


def _whisperkit_complete(model_dir: Path) -> bool:
    """A WhisperKit model is usable once all three Core ML packages are present.

    Each ``.mlmodelc`` is a directory; a half-pulled model can leave an empty
    or missing package, so require every one to exist and be non-empty.
    """
    for rel in WHISPERKIT_REQUIRED:
        pkg = model_dir / rel
        if not pkg.is_dir():
            return False
        try:
            if not any(pkg.iterdir()):
                return False
        except OSError:
            return False
    return True


def _whisperkit_status() -> Dict:
    model_dir = _whisperkit_model_dir()
    if model_dir is None:
        return {
            "downloaded": False,
            "download_status": "missing",
            "size_mb": None,
            "warmed": False,
            "cache_dir": None,
            "hf_repo": None,
            "managed_by": "whisperkit",
            "removable": False,
        }
    exists = model_dir.is_dir()
    downloaded = bool(exists and _whisperkit_complete(model_dir))
    size_bytes = _dir_size_bytes(model_dir) if exists else 0
    if downloaded:
        download_status = "downloaded"
    elif size_bytes > 0:
        download_status = "partial"
    else:
        download_status = "missing"
    return {
        "downloaded": downloaded,
        "download_status": download_status,
        "size_mb": _bytes_to_mb(size_bytes) if size_bytes > 0 else None,
        # "warmed" is the MLX graph-cache signal; WhisperKit has no equivalent,
        # so leave it off rather than tag the card with a misleading "warmed".
        "warmed": False,
        "cache_dir": str(model_dir),
        # No hf_repo on purpose — keeps whisperkit out of the HF download path.
        "hf_repo": None,
        "managed_by": "whisperkit",
        "removable": downloaded,
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


def engine_model_metadata(
    engine_id: str, hf_repo: Optional[str] = None
) -> Optional[Dict[str, object]]:
    """Return managed HF model metadata for an engine using current config."""
    info = ENGINE_MODEL_MAP.get(engine_id)
    if info is None:
        return None
    hf_repo = hf_repo or _configured_hf_repo(engine_id) or str(info["hf_repo"])
    warm_sentinel = info["warm_sentinel"]
    legacy_warm_sentinels: tuple[str, ...] = ()
    if engine_id == "qwen3_asr":
        warm_sentinel = qwen3_warm_sentinel_name(hf_repo)
        if hf_repo == DEFAULT_QWEN3_ASR_MODEL:
            legacy_warm_sentinels = (".qwen3_warmed",)
    return {
        "hf_repo": hf_repo,
        "cache_dir": hf_cache_dir_name(hf_repo),
        "warm_sentinel": warm_sentinel,
        "legacy_warm_sentinels": legacy_warm_sentinels,
        "required_files": tuple(info.get("required_files", ())),
    }


def engine_model_status(engine_id: str, hf_repo: Optional[str] = None) -> Dict:
    """Return cache status for a single engine.

    Keys:
      downloaded: bool -- weights present on disk
      size_mb:    int|None -- megabytes used (None if unknown)
      warmed:     bool -- MLX graph cache primed (sentinel file exists)
      cache_dir:  str|None -- absolute path to the HF cache folder
      hf_repo:    str|None -- which HF repo the engine uses
    """
    if engine_id == "whisperkit":
        return _whisperkit_status()

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

    info = engine_model_metadata(engine_id, hf_repo=hf_repo)
    if info is None:
        return {
            "downloaded": False,
            "size_mb": None,
            "warmed": False,
            "cache_dir": None,
            "hf_repo": None,
        }

    cache_path = MODEL_DIR / str(info["cache_dir"])
    warmed_paths = [MODEL_DIR / str(info["warm_sentinel"])]
    warmed_paths.extend(
        MODEL_DIR / str(name) for name in info.get("legacy_warm_sentinels", ())
    )
    size_bytes = _dir_size_bytes(cache_path) if cache_path.exists() else 0
    required_files = tuple(info.get("required_files", ()))
    downloaded = hf_cache_complete(cache_path, required_files)
    download_status = "downloaded" if downloaded else ("partial" if size_bytes > 0 else "missing")
    size_mb = _bytes_to_mb(size_bytes)
    return {
        "downloaded": downloaded,
        "download_status": download_status,
        "size_mb": size_mb,
        "warmed": any(path.exists() for path in warmed_paths),
        "cache_dir": str(cache_path),
        "hf_repo": info["hf_repo"],
    }


def ensure_engine_model_cached(engine_id: str, hf_repo: Optional[str] = None) -> None:
    """Download a managed engine's HF snapshot if it is missing or partial."""
    info = engine_model_metadata(engine_id, hf_repo=hf_repo)
    if info is None:
        return
    status = engine_model_status(engine_id, hf_repo=hf_repo)
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

    refreshed = engine_model_status(engine_id, hf_repo=hf_repo)
    if not refreshed.get("downloaded", False):
        raise RuntimeError(f"{engine_id} model download did not finish cleanly")


def mark_engine_model_warmed(engine_id: str, hf_repo: Optional[str] = None) -> bool:
    """Persist that the selected managed model completed runtime warm-up."""
    info = engine_model_metadata(engine_id, hf_repo=hf_repo)
    if info is None:
        return False
    try:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        (MODEL_DIR / str(info["warm_sentinel"])).touch()
        return True
    except OSError:
        return False


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
    if engine_id == "whisperkit":
        model_dir = _whisperkit_model_dir()
        if model_dir is not None and model_dir.is_dir():
            shutil.rmtree(model_dir, ignore_errors=True)
            return True
        return False

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
    warmed_paths = [MODEL_DIR / str(info["warm_sentinel"])]
    warmed_paths.extend(
        MODEL_DIR / str(name) for name in info.get("legacy_warm_sentinels", ())
    )
    for warmed_path in warmed_paths:
        if warmed_path.exists():
            try:
                warmed_path.unlink()
                removed = True
            except OSError:
                pass
    return removed

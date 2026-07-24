# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Qwen3-ASR model catalog and live-reload contracts."""

import sys
from types import SimpleNamespace


def _config(model: str):
    return SimpleNamespace(
        hotkey=SimpleNamespace(key="alt_r"),
        transcription=SimpleNamespace(engine="qwen3_asr"),
        qwen3_asr=SimpleNamespace(model=model),
        parakeet=SimpleNamespace(model="mlx-community/parakeet-tdt-0.6b-v3"),
        whisper=SimpleNamespace(model="large-v3-v20240930_626MB"),
        apple_speech=SimpleNamespace(locale="en-US"),
        grammar=SimpleNamespace(backend="apple_intelligence", enabled=False),
        tts=SimpleNamespace(enabled=False),
    )


def test_qwen3_catalog_exposes_both_bf16_variants_with_1_7b_default():
    from whisper_voice.engines.qwen3_models import (
        DEFAULT_QWEN3_ASR_MODEL,
        QWEN3_ASR_MODELS,
    )

    assert DEFAULT_QWEN3_ASR_MODEL == "mlx-community/Qwen3-ASR-1.7B-bf16"
    assert [model.id for model in QWEN3_ASR_MODELS] == [
        "mlx-community/Qwen3-ASR-1.7B-bf16",
        "mlx-community/Qwen3-ASR-0.6B-bf16",
    ]
    assert QWEN3_ASR_MODELS[0].quality == "higher"
    assert QWEN3_ASR_MODELS[1].memory == "lower"
    assert all(model.supports_contextual_prompting for model in QWEN3_ASR_MODELS)


def test_qwen3_model_aliases_resolve_to_catalog_ids():
    from whisper_voice.engines.qwen3_models import (
        qwen3_warm_sentinel_name,
        resolve_qwen3_asr_model,
    )

    assert resolve_qwen3_asr_model("1.7b") == "mlx-community/Qwen3-ASR-1.7B-bf16"
    assert resolve_qwen3_asr_model("0.6B") == "mlx-community/Qwen3-ASR-0.6B-bf16"
    assert (
        resolve_qwen3_asr_model("mlx-community/Qwen3-ASR-0.6B-bf16")
        == "mlx-community/Qwen3-ASR-0.6B-bf16"
    )
    assert qwen3_warm_sentinel_name("mlx-community/Qwen3-ASR-1.7B-bf16") != (
        qwen3_warm_sentinel_name("mlx-community/Qwen3-ASR-0.6B-bf16")
    )


def test_reload_config_reloads_active_qwen_model_when_only_model_changes(monkeypatch):
    from whisper_voice.app_commands import CommandsMixin

    old = _config("mlx-community/Qwen3-ASR-1.7B-bf16")
    new = _config("mlx-community/Qwen3-ASR-0.6B-bf16")
    switches = []
    responses = []

    app = SimpleNamespace(
        config=old,
        _busy=False,
        recorder=SimpleNamespace(recording=False),
        _set_record_key=lambda _key: None,
        _schedule_idle_unload=lambda: None,
        _switch_engine=lambda engine: switches.append(engine),
        _switch_backend=lambda _backend: None,
        _disable_grammar=lambda: None,
        _enable_tts=lambda: None,
        _disable_tts=lambda: None,
        _send_config_snapshot=lambda: None,
    )

    class ImmediateThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr("whisper_voice.config.reload_config", lambda: new)
    monkeypatch.setattr("threading.Thread", ImmediateThread)

    CommandsMixin._cmd_reload_config(app, responses.append)

    assert switches == ["qwen3_asr"]
    assert responses[-1]["success"] is True
    assert responses[-1]["engine_switching"] is True


def test_qwen_engine_marks_the_loaded_variant_warmed(monkeypatch):
    import whisper_voice.engines.qwen3_asr as qwen_mod

    model_id = "mlx-community/Qwen3-ASR-0.6B-bf16"
    marked = []

    class FakeModel:
        def warm_up(self):
            return None

    class FakeQwen3ASR:
        @staticmethod
        def from_pretrained(loaded_model):
            assert loaded_model == model_id
            return FakeModel()

    monkeypatch.setitem(
        sys.modules,
        "qwen3_asr_mlx",
        SimpleNamespace(Qwen3ASR=FakeQwen3ASR),
    )
    monkeypatch.setattr(
        qwen_mod,
        "get_config",
        lambda: SimpleNamespace(
            qwen3_asr=SimpleNamespace(model=model_id, timeout=0),
        ),
    )
    monkeypatch.setattr(
        qwen_mod,
        "mark_engine_model_warmed",
        lambda engine, hf_repo=None: marked.append((engine, hf_repo)),
        raising=False,
    )

    assert qwen_mod.Qwen3ASREngine().start() is True
    assert marked == [("qwen3_asr", model_id)]

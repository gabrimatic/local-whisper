# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Capability-gated Vocabulary context dispatch for transcription engines."""

from types import SimpleNamespace

import pytest

from whisper_voice.engines import (
    ENGINE_REGISTRY,
    EngineCapability,
    supports_engine_capability,
)
from whisper_voice.engines.base import ContextualPromptingEngine, TranscriptionEngine
from whisper_voice.engines.context import MAX_CONTEXT_CHARS, build_vocabulary_context
from whisper_voice.engines.qwen3_models import (
    QWEN3_ASR_MODELS,
    qwen3_model_supports_contextual_prompting,
)


class _PlainEngine(TranscriptionEngine):
    name = "Plain"

    def __init__(self):
        self.paths = []

    def start(self):
        return True

    def running(self):
        return True

    def transcribe(self, path):
        self.paths.append(path)
        return "plain", None

    def close(self):
        pass


class _ContextEngine(ContextualPromptingEngine):
    name = "Context"

    def __init__(self):
        self.plain_paths = []
        self.context_calls = []

    def start(self):
        return True

    def running(self):
        return True

    def transcribe(self, path):
        self.plain_paths.append(path)
        return "plain", None

    def transcribe_with_context(self, path, context):
        self.context_calls.append((path, context))
        return "context", None

    def close(self):
        pass


def _config(*, enabled=True, use_vocabulary=True, model=None):
    return SimpleNamespace(
        qwen3_asr=SimpleNamespace(
            model=model or QWEN3_ASR_MODELS[0].id,
            use_vocabulary=use_vocabulary,
        ),
        replacements=SimpleNamespace(
            enabled=enabled,
            rules={
                "open ai": "OpenAI",
                "chat gpt": "ChatGPT",
                "um": "",
            },
        ),
    )


def _transcriber(monkeypatch, engine_id, engine, config):
    import whisper_voice.transcriber as transcriber_mod

    monkeypatch.setattr(transcriber_mod, "create_engine", lambda _engine_id: engine)
    monkeypatch.setattr(transcriber_mod, "get_config", lambda: config)
    monkeypatch.setattr(transcriber_mod, "ensure_engine_model_cached", lambda _engine_id: None)
    return transcriber_mod.Transcriber(engine_id=engine_id)


def test_registry_capability_matrix_only_declares_qwen_context():
    supporting = {
        engine_id
        for engine_id in ENGINE_REGISTRY
        if supports_engine_capability(
            engine_id,
            EngineCapability.CONTEXTUAL_PROMPTING,
        )
    }
    assert supporting == {"qwen3_asr"}


def test_both_catalog_models_declare_context_support():
    assert {model.id for model in QWEN3_ASR_MODELS} == {
        "mlx-community/Qwen3-ASR-1.7B-bf16",
        "mlx-community/Qwen3-ASR-0.6B-bf16",
    }
    assert all(model.supports_contextual_prompting for model in QWEN3_ASR_MODELS)
    assert all(
        qwen3_model_supports_contextual_prompting(model.id)
        for model in QWEN3_ASR_MODELS
    )
    assert not qwen3_model_supports_contextual_prompting("custom/unknown")


def test_vocabulary_context_retains_spoken_and_preferred_forms():
    result = build_vocabulary_context(
        {
            "open ai": "OpenAI",
            "Local Whisper": "Local Whisper",
            "um": "",
            "line\nbreak": 'quoted "term"',
        }
    )
    assert result.text is not None
    assert '"OpenAI" (spoken as "open ai")' in result.text
    assert '"Local Whisper"' in result.text
    assert '"quoted \\"term\\"" (spoken as "line break")' in result.text
    assert '"um"' not in result.text
    assert result.included_rules == result.eligible_rules == 3
    assert not result.truncated


def test_vocabulary_context_is_bounded_and_reports_truncation():
    rules = {f"spoken {index}": "x" * 500 for index in range(20)}
    result = build_vocabulary_context(rules)
    assert result.text is not None
    assert len(result.text) <= MAX_CONTEXT_CHARS
    assert result.included_rules < result.eligible_rules
    assert result.truncated


def test_qwen_receives_enabled_vocabulary_through_context_contract(
    monkeypatch,
    tmp_path,
):
    engine = _ContextEngine()
    transcriber = _transcriber(monkeypatch, "qwen3_asr", engine, _config())
    audio = tmp_path / "audio.wav"

    assert transcriber.transcribe(audio) == ("context", None)
    assert engine.plain_paths == []
    assert engine.context_calls[0][0] == audio
    assert '"OpenAI" (spoken as "open ai")' in engine.context_calls[0][1]
    assert '"ChatGPT" (spoken as "chat gpt")' in engine.context_calls[0][1]
    assert '"um"' not in engine.context_calls[0][1]


def test_qwen_reads_live_vocabulary_changes_without_engine_reload(
    monkeypatch,
    tmp_path,
):
    engine = _ContextEngine()
    config = _config()
    transcriber = _transcriber(monkeypatch, "qwen3_asr", engine, config)
    audio = tmp_path / "audio.wav"

    transcriber.transcribe(audio)
    config.replacements.rules = {"new term": "NewTerm"}
    transcriber.transcribe(audio)

    assert len(engine.context_calls) == 2
    assert "OpenAI" in engine.context_calls[0][1]
    assert "OpenAI" not in engine.context_calls[1][1]
    assert '"NewTerm" (spoken as "new term")' in engine.context_calls[1][1]


@pytest.mark.parametrize(
    "config",
    [
        _config(enabled=False),
        _config(use_vocabulary=False),
        _config(model="custom/unknown"),
    ],
)
def test_qwen_uses_plain_path_when_context_is_disabled_or_unsupported(
    monkeypatch,
    tmp_path,
    config,
):
    engine = _ContextEngine()
    transcriber = _transcriber(monkeypatch, "qwen3_asr", engine, config)
    audio = tmp_path / "audio.wav"

    assert transcriber.transcribe(audio) == ("plain", None)
    assert engine.plain_paths == [audio]
    assert engine.context_calls == []


@pytest.mark.parametrize(
    "engine_id",
    ["parakeet_v3", "whisperkit", "apple_speech"],
)
def test_unsupported_engines_never_receive_vocabulary_context(
    monkeypatch,
    tmp_path,
    engine_id,
):
    engine = _PlainEngine()
    transcriber = _transcriber(monkeypatch, engine_id, engine, _config())
    audio = tmp_path / f"{engine_id}.wav"

    assert transcriber.transcribe(audio) == ("plain", None)
    assert engine.paths == [audio]


def test_context_limit_rejects_impossible_value():
    with pytest.raises(ValueError, match="max_chars must be at least"):
        build_vocabulary_context({"a": "b"}, max_chars=1)


def test_qwen_engine_passes_context_to_published_runtime(monkeypatch, tmp_path):
    import whisper_voice.engines.qwen3_asr as qwen_mod

    calls = []

    class FakeModel:
        def transcribe(self, path, **kwargs):
            calls.append((path, kwargs))
            return SimpleNamespace(text="transcript")

    config = SimpleNamespace(
        qwen3_asr=SimpleNamespace(
            timeout=0,
            temperature=0.0,
            top_p=1.0,
            top_k=0,
            repetition_penalty=1.2,
            repetition_context_size=100,
            chunk_duration=1200.0,
            max_tokens=0,
        )
    )
    monkeypatch.setattr(qwen_mod, "get_config", lambda: config)
    monkeypatch.setattr(qwen_mod, "_quick_duration", lambda _path: 1.0)

    engine = qwen_mod.Qwen3ASREngine()
    engine._model = FakeModel()
    audio = tmp_path / "audio.wav"
    context = 'Vocabulary and preferred spellings: "OpenAI".'

    assert engine.transcribe_with_context(audio, context) == ("transcript", None)
    assert calls == [
        (
            str(audio),
            {
                "temperature": 0.0,
                "top_p": 1.0,
                "top_k": 0,
                "repetition_penalty": 1.2,
                "repetition_context_size": 100,
                "chunk_duration": 1200.0,
                "context": context,
            },
        )
    ]

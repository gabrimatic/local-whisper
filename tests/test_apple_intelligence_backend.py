# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Unit tests for Apple Intelligence backend session lifecycle.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from conftest import import_with_stubs


class _FakeReason:
    name = "available"


class _FakeUseCase:
    GENERAL = "general"


class _FakeGuardrails:
    PERMISSIVE_CONTENT_TRANSFORMATIONS = "permissive"


class _FakeSystemLanguageModel:
    instances = []

    def __init__(self, use_case=None, guardrails=None, _ptr=None):
        self.use_case = use_case
        self.guardrails = guardrails
        self._ptr = _ptr
        self.__class__.instances.append(self)

    def is_available(self):
        return True, _FakeReason()


class _FakeLanguageModelSession:
    instances = []
    responses = []

    def __init__(self, instructions=None, model=None, tools=None, _ptr=None):
        self.instructions = instructions
        self.model = model
        self.tools = tools
        self._ptr = _ptr
        self.prompts = []
        self.__class__.instances.append(self)

    async def respond(self, prompt):
        self.prompts.append(prompt)
        if self.__class__.responses:
            return self.__class__.responses.pop(0)
        return f"resp:{prompt}"


FAKE_FM = SimpleNamespace(
    SystemLanguageModel=_FakeSystemLanguageModel,
    SystemLanguageModelUseCase=_FakeUseCase,
    SystemLanguageModelGuardrails=_FakeGuardrails,
    LanguageModelSession=_FakeLanguageModelSession,
)

APPLE_MOD = import_with_stubs(
    "whisper_voice.backends.apple_intelligence.backend",
    extra_stubs={"apple_fm_sdk": FAKE_FM},
)


class TestAppleIntelligenceBackend:
    def setup_method(self):
        _FakeSystemLanguageModel.instances.clear()
        _FakeLanguageModelSession.instances.clear()
        _FakeLanguageModelSession.responses.clear()

    def test_generate_uses_fresh_session_per_request(self):
        backend = APPLE_MOD.AppleIntelligenceBackend()

        first = asyncio.run(backend._generate("sys", "one"))
        second = asyncio.run(backend._generate("sys", "two"))

        assert first == "resp:one"
        assert second == "resp:two"
        assert len(_FakeSystemLanguageModel.instances) == 1
        assert len(_FakeLanguageModelSession.instances) == 2
        assert _FakeLanguageModelSession.instances[0] is not _FakeLanguageModelSession.instances[1]

    def test_fix_with_mode_reuses_model_but_not_session(self):
        backend = APPLE_MOD.AppleIntelligenceBackend()
        cfg = SimpleNamespace(apple_intelligence=SimpleNamespace(max_chars=0, timeout=0))
        _FakeLanguageModelSession.responses[:] = [" First. ", " Second. "]

        with patch.object(APPLE_MOD, "get_config", return_value=cfg):
            first, first_err = backend.fix_with_mode("hello there", "transcription")
            second, second_err = backend.fix_with_mode("hello again", "transcription")

        assert first_err is None
        assert second_err is None
        assert first == "First."
        assert second == "Second."
        assert len(_FakeSystemLanguageModel.instances) == 1
        assert len(_FakeLanguageModelSession.instances) == 2

    def test_close_releases_cached_model_and_loop(self):
        backend = APPLE_MOD.AppleIntelligenceBackend()
        backend._model = object()
        backend._loop = SimpleNamespace(
            is_closed=lambda: False,
            call_soon_threadsafe=lambda fn: fn(),
            stop=lambda: None,
            close=lambda: None,
        )
        backend._loop_thread = SimpleNamespace(
            is_alive=lambda: False,
            join=lambda timeout=0: None,
        )

        backend.close()

        assert backend._model is None
        assert backend._loop is None
        assert backend._loop_thread is None

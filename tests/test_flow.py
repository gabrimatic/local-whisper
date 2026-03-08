# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Integration tests for the Local Whisper pipeline.

Tests the real transcription and grammar correction flow using live services.
Skipped automatically when the required services are not running.

Run explicitly:
    pytest tests/test_flow.py -v
    pytest -m integration -v

These tests use the configured engine (Qwen3-ASR or WhisperKit) and grammar
backend (Apple Intelligence, Ollama, or LM Studio) from ~/.whisper/config.toml.
"""

import difflib
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_AUDIO = FIXTURES_DIR / "test_audio.wav"
EXPECTED_RAW = FIXTURES_DIR / "expected_raw.txt"
EXPECTED_FIXED = FIXTURES_DIR / "expected_fixed.txt"

# Words that must appear in a correct transcription of the test audio
EXPECTED_KEYWORDS = ["test", "bottle", "desk"]

# Minimum acceptable similarity ratio (0.0 to 1.0) for fuzzy comparison
MIN_SIMILARITY = 0.75


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    """Sequence similarity ratio between two strings (order-aware, 0.0-1.0)."""
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _try_import_transcriber():
    """Try to import and create a Transcriber. Returns (transcriber, error_msg)."""
    try:
        from whisper_voice.transcriber import Transcriber
        t = Transcriber()
        return t, None
    except Exception as e:
        return None, str(e)


def _try_import_grammar():
    """Try to import and create a Grammar instance. Returns (grammar, error_msg)."""
    try:
        from whisper_voice.grammar import Grammar
        g = Grammar()
        return g, None
    except Exception as e:
        return None, str(e)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def transcriber():
    """Provide a live Transcriber, skip if the engine isn't available."""
    t, err = _try_import_transcriber()
    if t is None:
        pytest.skip(f"Transcriber unavailable: {err}")

    if not t.start():
        pytest.skip(f"{t.name} engine failed to start")

    yield t

    try:
        t.close()
    except Exception:
        pass


@pytest.fixture(scope="module")
def grammar():
    """Provide a live Grammar backend, skip if unavailable."""
    g, err = _try_import_grammar()
    if g is None:
        pytest.skip(f"Grammar unavailable: {err}")

    if not g.running():
        pytest.skip(f"{g.name} backend not running")

    yield g

    try:
        g.close()
    except Exception:
        pass


@pytest.fixture(scope="module")
def expected_raw() -> str:
    if not EXPECTED_RAW.exists():
        pytest.skip(f"Fixture missing: {EXPECTED_RAW}")
    return EXPECTED_RAW.read_text().strip()


@pytest.fixture(scope="module")
def expected_fixed() -> str:
    if not EXPECTED_FIXED.exists():
        pytest.skip(f"Fixture missing: {EXPECTED_FIXED}")
    return EXPECTED_FIXED.read_text().strip()


# ---------------------------------------------------------------------------
# Fixtures validation
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestFixtures:
    """Verify test fixtures are present and well-formed."""

    def test_audio_file_exists(self):
        assert TEST_AUDIO.exists(), f"Missing: {TEST_AUDIO}"

    def test_audio_file_not_empty(self):
        assert TEST_AUDIO.stat().st_size > 1000, "Test audio too small"

    def test_expected_raw_not_empty(self, expected_raw):
        assert len(expected_raw) > 10

    def test_expected_fixed_not_empty(self, expected_fixed):
        assert len(expected_fixed) > 10


# ---------------------------------------------------------------------------
# Transcription tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestTranscription:
    """Test the transcription engine with real audio."""

    def test_transcription_succeeds(self, transcriber):
        text, err = transcriber.transcribe(TEST_AUDIO)
        assert err is None, f"Transcription failed: {err}"
        assert text is not None
        assert len(text.strip()) > 0, "Transcription returned empty text"

    def test_transcription_not_hallucination(self, transcriber):
        from whisper_voice.utils import is_hallucination, strip_hallucination_lines

        text, _ = transcriber.transcribe(TEST_AUDIO)
        assert text is not None

        cleaned, had_hallucinations = strip_hallucination_lines(text)
        assert not is_hallucination(cleaned), f"Hallucination detected: {cleaned!r}"

    def test_transcription_contains_keywords(self, transcriber):
        text, _ = transcriber.transcribe(TEST_AUDIO)
        assert text is not None
        text_lower = text.lower()

        missing = [kw for kw in EXPECTED_KEYWORDS if kw not in text_lower]
        assert not missing, f"Missing keywords in transcription: {missing}. Got: {text!r}"

    def test_transcription_matches_expected(self, transcriber, expected_raw):
        text, _ = transcriber.transcribe(TEST_AUDIO)
        assert text is not None

        ratio = _similarity(text, expected_raw)
        assert ratio >= MIN_SIMILARITY, (
            f"Transcription similarity too low: {ratio:.0%} (need {MIN_SIMILARITY:.0%})\n"
            f"  Expected: {expected_raw[:80]}...\n"
            f"  Got:      {text[:80]}..."
        )


# ---------------------------------------------------------------------------
# Grammar correction tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestGrammar:
    """Test grammar correction with known input."""

    def test_grammar_fix_succeeds(self, grammar, expected_raw):
        fixed, err = grammar.fix(expected_raw)
        assert err is None, f"Grammar correction failed: {err}"
        assert fixed is not None
        assert len(fixed.strip()) > 0, "Grammar returned empty text"

    def test_grammar_preserves_meaning(self, grammar, expected_raw):
        """Grammar should not drastically change the content."""
        fixed, _ = grammar.fix(expected_raw)
        assert fixed is not None

        ratio = _similarity(fixed, expected_raw)
        assert ratio >= 0.6, (
            f"Grammar changed text too much: {ratio:.0%} similarity\n"
            f"  Input:  {expected_raw[:80]}...\n"
            f"  Output: {fixed[:80]}..."
        )

    def test_grammar_output_matches_expected(self, grammar, expected_raw, expected_fixed):
        fixed, _ = grammar.fix(expected_raw)
        assert fixed is not None

        ratio = _similarity(fixed, expected_fixed)
        assert ratio >= MIN_SIMILARITY, (
            f"Grammar output similarity too low: {ratio:.0%} (need {MIN_SIMILARITY:.0%})\n"
            f"  Expected: {expected_fixed[:80]}...\n"
            f"  Got:      {fixed[:80]}..."
        )

    def test_grammar_output_reasonable_length(self, grammar, expected_raw):
        fixed, _ = grammar.fix(expected_raw)
        assert fixed is not None

        input_len = len(expected_raw)
        output_len = len(fixed.strip())
        # Output should be within 50%-200% of input length
        assert output_len >= input_len * 0.5, f"Output too short: {output_len} vs input {input_len}"
        assert output_len <= input_len * 2.0, f"Output too long: {output_len} vs input {input_len}"


# ---------------------------------------------------------------------------
# Full pipeline test
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestFullPipeline:
    """End-to-end: audio file -> transcription -> grammar correction."""

    def test_pipeline_produces_corrected_text(self, transcriber, grammar):
        # Step 1: Transcribe
        raw_text, t_err = transcriber.transcribe(TEST_AUDIO)
        assert t_err is None, f"Transcription failed: {t_err}"
        assert raw_text and len(raw_text.strip()) > 0

        # Step 2: Grammar correct
        fixed_text, g_err = grammar.fix(raw_text)
        assert g_err is None, f"Grammar failed: {g_err}"
        assert fixed_text and len(fixed_text.strip()) > 0

    def test_pipeline_output_contains_keywords(self, transcriber, grammar):
        raw_text, _ = transcriber.transcribe(TEST_AUDIO)
        assert raw_text is not None
        fixed_text, _ = grammar.fix(raw_text)
        assert fixed_text is not None

        text_lower = fixed_text.lower()
        missing = [kw for kw in EXPECTED_KEYWORDS if kw not in text_lower]
        assert not missing, f"Missing keywords after full pipeline: {missing}. Got: {fixed_text!r}"

    def test_pipeline_output_matches_expected(self, transcriber, grammar, expected_fixed):
        raw_text, _ = transcriber.transcribe(TEST_AUDIO)
        assert raw_text is not None
        fixed_text, _ = grammar.fix(raw_text)
        assert fixed_text is not None

        ratio = _similarity(fixed_text, expected_fixed)
        assert ratio >= MIN_SIMILARITY, (
            f"Pipeline output similarity too low: {ratio:.0%}\n"
            f"  Expected: {expected_fixed[:80]}...\n"
            f"  Got:      {fixed_text[:80]}..."
        )

# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
#!/usr/bin/env python3
"""
End-to-end test for Local Whisper flow.

Tests: Audio file → WhisperKit transcription → Grammar correction

Usage:
    cd local-whisper
    python tests/test_flow.py

Requirements:
    - WhisperKit server running (localhost:50060)
    - Grammar backend available (Apple Intelligence or Ollama)
"""

import sys
from pathlib import Path

# Paths
TESTS_DIR = Path(__file__).parent
PROJECT_DIR = TESTS_DIR.parent
FIXTURES_DIR = TESTS_DIR / "fixtures"

# Add src to path for imports
sys.path.insert(0, str(PROJECT_DIR / "src"))

from whisper_voice.config import get_config
from whisper_voice.transcriber import Whisper
from whisper_voice.grammar import Grammar
from whisper_voice.utils import is_hallucination, strip_hallucination_lines, log

# Test fixtures
TEST_AUDIO = FIXTURES_DIR / "test_audio.wav"
EXPECTED_RAW = FIXTURES_DIR / "expected_raw.txt"
EXPECTED_FIXED = FIXTURES_DIR / "expected_fixed.txt"

# Expected content patterns (flexible to handle different number formats)
EXPECTED_PATTERNS = ["test", "bottle", "desk"]


def test_full_flow():
    """Test complete flow: audio → transcription → grammar correction."""

    print("\n" + "=" * 60)
    print("  LOCAL WHISPER - END-TO-END TEST")
    print("=" * 60 + "\n")

    config = get_config()
    errors = []

    # -------------------------------------------------------------------------
    # Step 0: Validate test audio exists
    # -------------------------------------------------------------------------
    log("Checking test fixtures...", "INFO")
    if not TEST_AUDIO.exists():
        log(f"Test audio not found: {TEST_AUDIO}", "ERR")
        return False
    if not EXPECTED_RAW.exists():
        log(f"Expected raw not found: {EXPECTED_RAW}", "ERR")
        return False
    if not EXPECTED_FIXED.exists():
        log(f"Expected fixed not found: {EXPECTED_FIXED}", "ERR")
        return False

    file_size = TEST_AUDIO.stat().st_size
    expected_raw_text = EXPECTED_RAW.read_text().strip()
    expected_fixed_text = EXPECTED_FIXED.read_text().strip()
    log(f"Test audio: {file_size:,} bytes", "OK")
    log(f"Expected raw: {len(expected_raw_text)} chars", "OK")
    log(f"Expected fixed: {len(expected_fixed_text)} chars", "OK")

    # -------------------------------------------------------------------------
    # Step 1: Check WhisperKit server
    # -------------------------------------------------------------------------
    log("Checking WhisperKit server...", "INFO")
    whisper = Whisper()

    if not whisper.running():
        log("WhisperKit not running at localhost:50060", "ERR")
        log("Start with: whisperkit-cli serve --model whisper-large-v3-v20240930", "WARN")
        errors.append("WhisperKit not running")
    else:
        log("WhisperKit server ready", "OK")

    # -------------------------------------------------------------------------
    # Step 2: Check grammar backend availability
    # -------------------------------------------------------------------------
    grammar = Grammar()
    log(f"Checking {grammar.name} availability...", "INFO")

    if not grammar.running():
        log(f"{grammar.name} not available", "ERR")
        if config.grammar.backend == "apple_intelligence":
            log("Requirements: macOS 26+, Apple Silicon, Apple Intelligence enabled", "WARN")
        else:
            log("Start with: ollama serve", "WARN")
        errors.append(f"{grammar.name} not available")
    else:
        log(f"{grammar.name} ready", "OK")

    # Bail early if services not available
    if errors:
        log(f"Cannot continue - {len(errors)} service(s) unavailable", "ERR")
        return False

    # -------------------------------------------------------------------------
    # Step 3: Transcribe audio
    # -------------------------------------------------------------------------
    log("Transcribing audio with WhisperKit...", "INFO")
    raw_text, err = whisper.transcribe(TEST_AUDIO)

    if err:
        log(f"Transcription failed: {err}", "ERR")
        errors.append(f"Transcription error: {err}")
    elif not raw_text:
        log("Transcription returned empty", "ERR")
        errors.append("Empty transcription")
    else:
        log(f"Raw transcription: {raw_text}", "OK")

        # Validate not hallucination
        cleaned, stripped = strip_hallucination_lines(raw_text)
        if stripped:
            log("Hallucination lines stripped", "WARN")
            raw_text = cleaned

        if is_hallucination(raw_text):
            log("Transcription detected as hallucination", "ERR")
            errors.append("Hallucination detected")
        else:
            log("Hallucination check passed", "OK")

    if errors:
        log(f"Transcription failed with {len(errors)} error(s)", "ERR")
        return False

    # -------------------------------------------------------------------------
    # Step 4: Grammar correction
    # -------------------------------------------------------------------------
    log(f"Applying grammar correction with {grammar.name}...", "INFO")
    fixed_text, g_err = grammar.fix(raw_text)

    if g_err:
        log(f"Grammar correction failed: {g_err}", "ERR")
        errors.append(f"Grammar error: {g_err}")
    elif not fixed_text:
        log("Grammar correction returned empty", "ERR")
        errors.append("Empty grammar result")
    else:
        log(f"Fixed transcription: {fixed_text}", "OK")

    if errors:
        log(f"Grammar correction failed with {len(errors)} error(s)", "ERR")
        return False

    # -------------------------------------------------------------------------
    # Step 5: Validate transcription matches expected
    # -------------------------------------------------------------------------
    log("Validating transcription...", "INFO")

    # Check raw transcription matches expected
    if raw_text.strip() == expected_raw_text:
        log("Raw transcription matches expected exactly", "OK")
    else:
        # Check if it's similar enough (WhisperKit can vary slightly)
        raw_words = set(raw_text.lower().split())
        expected_words = set(expected_raw_text.lower().split())
        overlap = len(raw_words & expected_words) / max(len(expected_words), 1)
        if overlap >= 0.9:
            log(f"Raw transcription ~{overlap*100:.0f}% similar to expected", "OK")
        else:
            log(f"Raw transcription differs significantly ({overlap*100:.0f}% match)", "WARN")
            log(f"  Expected: {expected_raw_text[:60]}...", "INFO")
            log(f"  Got:      {raw_text[:60]}...", "INFO")

    # Check expected patterns are present
    missing_patterns = []
    for pattern in EXPECTED_PATTERNS:
        if pattern.lower() not in raw_text.lower():
            missing_patterns.append(pattern)

    if missing_patterns:
        log(f"Missing expected patterns in raw: {missing_patterns}", "ERR")
        errors.append(f"Missing patterns: {missing_patterns}")
    else:
        log(f"All expected patterns found: {EXPECTED_PATTERNS}", "OK")

    # -------------------------------------------------------------------------
    # Step 6: Validate grammar correction
    # -------------------------------------------------------------------------
    log("Validating grammar correction...", "INFO")

    # Check text is different (grammar was applied)
    if raw_text.strip() == fixed_text.strip():
        log("Grammar made no changes (raw == fixed)", "WARN")
    else:
        log("Grammar correction modified the text", "OK")

    # Check fixed output matches expected
    if fixed_text.strip() == expected_fixed_text:
        log("Fixed text matches expected exactly", "OK")
    else:
        # Check similarity
        fixed_words = set(fixed_text.lower().split())
        expected_fixed_words = set(expected_fixed_text.lower().split())
        overlap = len(fixed_words & expected_fixed_words) / max(len(expected_fixed_words), 1)
        if overlap >= 0.9:
            log(f"Fixed text ~{overlap*100:.0f}% similar to expected", "OK")
        else:
            log(f"Fixed text differs significantly ({overlap*100:.0f}% match)", "WARN")
            log(f"  Expected: {expected_fixed_text[:60]}...", "INFO")
            log(f"  Got:      {fixed_text[:60]}...", "INFO")

    # Check reasonable length
    if len(fixed_text) < 10:
        log(f"Output too short ({len(fixed_text)} chars)", "ERR")
        errors.append("Output too short")
    else:
        log(f"Output length: {len(fixed_text)} chars", "OK")

    # Check grammar actually improved something (punctuation, etc.)
    raw_punct = sum(1 for c in raw_text if c in '.,;:!?')
    fixed_punct = sum(1 for c in fixed_text if c in '.,;:!?')
    if fixed_punct >= raw_punct:
        log(f"Punctuation preserved/improved ({raw_punct} → {fixed_punct})", "OK")
    else:
        log(f"Punctuation reduced ({raw_punct} → {fixed_punct})", "WARN")

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------
    try:
        grammar.close()
        whisper.close()
    except Exception:
        pass

    # -------------------------------------------------------------------------
    # Results
    # -------------------------------------------------------------------------
    print("\n" + "-" * 60)
    if errors:
        log(f"TEST FAILED - {len(errors)} error(s)", "ERR")
        for e in errors:
            log(f"  • {e}", "ERR")
        print("-" * 60 + "\n")
        return False
    else:
        log("TEST PASSED - Full flow completed successfully", "OK")
        print("-" * 60)
        print(f"\n  Raw:   {raw_text[:70]}{'...' if len(raw_text) > 70 else ''}")
        print(f"  Fixed: {fixed_text[:70]}{'...' if len(fixed_text) > 70 else ''}")
        print("-" * 60 + "\n")
        return True


if __name__ == "__main__":
    success = test_full_flow()
    sys.exit(0 if success else 1)

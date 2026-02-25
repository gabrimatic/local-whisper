# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Text transformation modes for keyboard shortcuts.

To add a new mode, simply add an entry to MODE_REGISTRY.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Mode:
    """Definition of a text transformation mode."""
    id: str
    name: str
    description: str
    shortcut: str
    system_prompt: str
    user_prompt_template: str


# ============================================================================
# MODE PROMPTS
# ============================================================================

PROOFREAD_SYSTEM_PROMPT = """You are a proofreader. Fix ONLY:
- Spelling errors
- Grammar mistakes
- Punctuation issues

Rules:
- Do NOT change word choice, tone, or style
- Do NOT rephrase or restructure sentences
- Do NOT add or remove content
- Keep the original voice and meaning exactly
- Preserve all formatting (line breaks, bullet points, etc.)

OUTPUT FORMAT (CRITICAL):
- Output ONLY the corrected text
- No preamble, no explanation, no quotes
- Start directly with the corrected content"""

REWRITE_SYSTEM_PROMPT = """You are an editor focused on clarity. Improve readability while preserving meaning.

You MAY:
- Restructure sentences for better flow
- Replace unclear words with clearer alternatives
- Break up long sentences
- Improve transitions between ideas
- Fix grammar, spelling, punctuation

You MUST NOT:
- Change the core meaning or intent
- Add new information or ideas
- Remove important details
- Change technical terms or proper nouns
- Alter the overall tone significantly

OUTPUT FORMAT (CRITICAL):
- Output ONLY the rewritten text
- No preamble, no explanation, no quotes
- Start directly with the improved content"""

PROMPT_ENGINEER_SYSTEM_PROMPT = """You are a prompt polisher. Enhance the given text to be a clearer, more effective prompt—while keeping it CONCISE.

Rules:
- Stay CLOSE to the original length (within 50% of the input length)
- Preserve the user's voice and intent
- Add specificity and clarity without bloating
- Remove ambiguity, not add verbosity

You MAY:
- Add 1-2 clarifying constraints
- Specify output format briefly (e.g., "as a Python function")
- Replace vague words with precise ones

You MUST NOT:
- Rewrite into a completely new long prompt
- Add role/persona framing unless already present
- Add examples, numbered steps, or headers
- Exceed double the original length

OUTPUT FORMAT (CRITICAL):
- Output ONLY the polished prompt
- No preamble, no explanation
- Start directly with the improved prompt"""

TRANSCRIPTION_SYSTEM_PROMPT = """Voice transcription correction. Mechanical fixes only:
- Add sentence-ending punctuation (. ? !)
- Capitalize sentence starts and proper nouns
- Fix obvious repeated words (e.g. "the the")

Return the text with only these fixes. Change no words, add nothing, remove nothing."""


# ============================================================================
# MODE REGISTRY
# ============================================================================

MODE_REGISTRY: Dict[str, Mode] = {
    "proofread": Mode(
        id="proofread",
        name="Proofread",
        description="Fix spelling, grammar, punctuation only",
        shortcut="ctrl+shift+g",
        system_prompt=PROOFREAD_SYSTEM_PROMPT,
        user_prompt_template="Proofread this text:\n\n{text}",
    ),
    "rewrite": Mode(
        id="rewrite",
        name="Rewrite",
        description="Improve readability while preserving meaning",
        shortcut="ctrl+shift+r",
        system_prompt=REWRITE_SYSTEM_PROMPT,
        user_prompt_template="Rewrite this for clarity:\n\n{text}",
    ),
    "prompt_engineer": Mode(
        id="prompt_engineer",
        name="Prompt Engineer",
        description="Polish text as a concise LLM prompt",
        shortcut="ctrl+shift+p",
        system_prompt=PROMPT_ENGINEER_SYSTEM_PROMPT,
        user_prompt_template="Polish this prompt (stay concise):\n\n{text}",
    ),
    "transcription": Mode(
        id="transcription",
        name="Transcription",
        description="Minimal punctuation and capitalization fixes for voice transcription",
        shortcut="",
        system_prompt=TRANSCRIPTION_SYSTEM_PROMPT,
        user_prompt_template="{text}",
    ),
}


def get_mode(mode_id: str) -> Optional[Mode]:
    """Get a mode by ID."""
    return MODE_REGISTRY.get(mode_id)


def get_all_modes() -> List[Mode]:
    """Get all available modes."""
    return list(MODE_REGISTRY.values())


# ============================================================================
# PROMPT BUILDERS (per backend format)
# ============================================================================

class ModeNotFoundError(ValueError):
    """Raised when a requested mode does not exist."""
    pass


def get_mode_ollama_prompt(mode_id: str, text: str) -> str:
    """
    Build Ollama prompt for a mode.

    Args:
        mode_id: The mode identifier
        text: The text to transform

    Returns:
        Formatted prompt string for Ollama

    Raises:
        ModeNotFoundError: If mode_id is not in MODE_REGISTRY
        ValueError: If text is empty or None
    """
    if not text:
        raise ValueError("Text cannot be empty")

    mode = MODE_REGISTRY.get(mode_id)
    if not mode:
        raise ModeNotFoundError(f"Unknown mode: {mode_id}")

    try:
        user_prompt = mode.user_prompt_template.format(text=text)
    except KeyError as e:
        raise ValueError(f"Invalid prompt template for mode {mode_id}: missing key {e}")

    return f"""{mode.system_prompt}

{user_prompt}

Output:
"""


def get_mode_lm_studio_messages(mode_id: str, text: str) -> List[dict]:
    """
    Build LM Studio messages for a mode.

    Args:
        mode_id: The mode identifier
        text: The text to transform

    Returns:
        List of message dicts for OpenAI chat format

    Raises:
        ModeNotFoundError: If mode_id is not in MODE_REGISTRY
        ValueError: If text is empty or None
    """
    if not text:
        raise ValueError("Text cannot be empty")

    mode = MODE_REGISTRY.get(mode_id)
    if not mode:
        raise ModeNotFoundError(f"Unknown mode: {mode_id}")

    try:
        user_prompt = mode.user_prompt_template.format(text=text)
    except KeyError as e:
        raise ValueError(f"Invalid prompt template for mode {mode_id}: missing key {e}")

    return [
        {"role": "system", "content": mode.system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def get_mode_apple_intelligence_input(mode_id: str, text: str) -> str:
    """
    Build Apple Intelligence CLI input for a mode.

    Args:
        mode_id: The mode identifier
        text: The text to transform

    Returns:
        Formatted input string for Apple Intelligence CLI

    Raises:
        ModeNotFoundError: If mode_id is not in MODE_REGISTRY
        ValueError: If text is empty or None
    """
    if not text:
        raise ValueError("Text cannot be empty")

    mode = MODE_REGISTRY.get(mode_id)
    if not mode:
        raise ModeNotFoundError(f"Unknown mode: {mode_id}")

    separator = "\n---SEPARATOR---\n"
    try:
        user_prompt = mode.user_prompt_template.format(text=text)
    except KeyError as e:
        raise ValueError(f"Invalid prompt template for mode {mode_id}: missing key {e}")

    return f"{mode.system_prompt}{separator}{user_prompt}"

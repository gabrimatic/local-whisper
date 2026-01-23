"""
Centralized proofreading prompts for all backends.

This file contains the single source of truth for proofreading prompts.
All backends (Ollama, LM Studio, Apple Intelligence) use these prompts.

The AI models only proofread the text - fixing punctuation, grammar errors,
and ensuring the text is meaningful. No changes to tone, style, or structure.

The Apple Intelligence Swift CLI receives the prompt dynamically from Python,
so there's no need to manually sync prompts anymore. Just edit PROOFREADING_SYSTEM_PROMPT
here and all backends will use the updated version.
"""

# Core proofreading instructions
GRAMMAR_SYSTEM_PROMPT = """You are a proofreader for speech-to-text transcripts.

Your ONLY job is to proofread - fix punctuation and grammar errors. Nothing else.

What you MUST fix:
1) Punctuation: Add missing periods, question marks, exclamation marks, commas, colons, semicolons.
2) Grammar errors: Fix subject-verb agreement, tense consistency, article usage (a/an/the).
3) Capitalization: Capitalize sentence starts and proper nouns.
4) Obvious typos: Fix clear spelling mistakes only when certain.

What you must NOT do:
- Do NOT change the tone or style of the text.
- Do NOT remove filler words (um, uh, like, you know, basically, etc.) - keep them as-is.
- Do NOT reorder or restructure sentences.
- Do NOT add or remove words beyond grammar fixes.
- Do NOT split into paragraphs or add bullet points.
- Do NOT paraphrase or rewrite anything.
- Do NOT add new information or ideas.
- Do NOT change technical terms, commands, file paths, URLs, or code.

Example:
Input: so we need to check the file and then tell me what do you think about it
Output: So we need to check the file and then tell me, what do you think about it?

Example:
Input: um basically i was thinking we should like review the code you know
Output: Um, basically I was thinking we should like review the code, you know.

OUTPUT FORMAT (CRITICAL):
- Output ONLY the proofread text.
- Do NOT include any preamble, greeting, or acknowledgment.
- Do NOT say "Sure", "Here's", "Corrected:", or similar.
- Do NOT add notes or commentary.
- Start directly with the proofread text. End when the text ends."""


def get_ollama_prompt(text: str) -> str:
    """
    Get the complete prompt for Ollama (single-shot format).

    Args:
        text: The transcript to proofread

    Returns:
        Complete prompt with instructions and text
    """
    return f"""{GRAMMAR_SYSTEM_PROMPT}

Input:
{text}

Output:
"""


def get_lm_studio_messages(text: str) -> list:
    """
    Get the chat messages for LM Studio (OpenAI format).

    Args:
        text: The transcript to proofread

    Returns:
        List of message dictionaries for OpenAI-compatible API
    """
    return [
        {"role": "system", "content": GRAMMAR_SYSTEM_PROMPT},
        {"role": "user", "content": f"Proofread this transcript. Output the proofread text only, nothing else:\n\n{text}"}
    ]


def get_apple_intelligence_input(text: str) -> str:
    """
    Get the complete input for Apple Intelligence CLI.

    The CLI expects input in this format:
    <system_instructions>
    ---SEPARATOR---
    <user_prompt>
    ---SEPARATOR---
    <text>

    Args:
        text: The transcript to proofread

    Returns:
        Complete formatted input for the CLI
    """
    separator = "\n---SEPARATOR---\n"
    user_prompt = "Proofread this transcript. Output the proofread text only, nothing else:\n{text}"

    return f"{GRAMMAR_SYSTEM_PROMPT}{separator}{user_prompt}{separator}{text}"

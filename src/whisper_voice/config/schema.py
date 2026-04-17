# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Configuration schema: constants, defaults, and dataclasses.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

CONFIG_DIR = Path.home() / ".whisper"
CONFIG_FILE = CONFIG_DIR / "config.toml"

# Available grammar backends
GRAMMAR_BACKENDS = ("ollama", "apple_intelligence", "lm_studio")
GrammarBackendType = Literal["ollama", "apple_intelligence", "lm_studio"]

# Default transcription prompt. Empty by default to avoid confusing Whisper.
# Whisper's prompt parameter is meant for vocabulary hints only, not conversational context.
DEFAULT_WHISPER_PROMPT = ""

# Default configuration
DEFAULT_CONFIG = """# Local Whisper Configuration
# Edit this file to customize behavior

[hotkey]
# Key to use for recording trigger
# Options: alt_r, alt_l, ctrl_r, ctrl_l, cmd_r, cmd_l, shift_r, shift_l, caps_lock, f1-f12
key = "alt_r"

# Double-tap threshold in seconds (how fast you need to tap twice)
double_tap_threshold = 0.4

[transcription]
# Transcription engine: "qwen3_asr" (default) or "whisperkit"
engine = "qwen3_asr"

[qwen3_asr]
# Model identifier from Hugging Face
model = "mlx-community/Qwen3-ASR-1.7B-bf16"

# Language code (en, fa, es, fr, de, etc.) or "auto" for detection
language = "auto"

# Transcription timeout in seconds (0 = no limit)
timeout = 0

# MLX prefill step size (higher = faster on Apple Silicon, default 4096)
prefill_step_size = 4096

[whisper]
# WhisperKit server URL
url = "http://localhost:50060/v1/audio/transcriptions"
check_url = "http://localhost:50060/"

# Whisper model to use
model = "whisper-large-v3-v20240930"

# Language code (en, fa, es, fr, de, etc. or "auto" for detection)
language = "auto"

# Transcription timeout in seconds (no limit)
timeout = 0

# Optional vocabulary hint for transcription.
# Whisper's prompt parameter is meant for vocabulary hints (technical terms, names)
# NOT conversational context. Using conversational prompts causes truncated or empty results.
# Leave empty unless you need to hint specific vocabulary.
prompt = ""

# Decoding temperature (0.0 = greedy/deterministic, higher = more random)
temperature = 0.0

# Compression ratio threshold for fallback (higher = more tolerant of repetition)
compression_ratio_threshold = 2.4

# Probability threshold below which a segment is considered silence
no_speech_threshold = 0.6

# Log probability threshold for fallback (lower = stricter)
logprob_threshold = -1.0

# Number of temperature fallback steps before giving up
temperature_fallback_count = 5

# Prompt preset for transcription context ("none", "technical", "dictation", "custom")
prompt_preset = "none"

[grammar]
# Grammar correction backend: "apple_intelligence", "ollama", or "lm_studio"
backend = "apple_intelligence"

# Enable/disable grammar correction
enabled = false

[ollama]
# Ollama server URL
url = "http://localhost:11434/api/generate"
check_url = "http://localhost:11434/"

# Model for grammar correction
model = "gemma3:4b-it-qat"

# Maximum characters per grammar chunk (0 = no limit)
max_chars = 0

# Maximum tokens to predict (0 = no limit, uses model default)
max_predict = 0

# Context window size for grammar requests (0 = use model default)
num_ctx = 0

# Keep model hot in memory between requests (e.g. "30s", "5m", "1h", "-1" for indefinite)
keep_alive = "60m"

# Grammar correction timeout in seconds (0 = no limit)
timeout = 0

# Unload model from memory when app exits (false keeps Ollama hot for other uses)
unload_on_exit = false

[apple_intelligence]
# Maximum characters per grammar chunk (0 = no limit)
max_chars = 0

# Grammar correction timeout in seconds (0 = no limit)
timeout = 0

[lm_studio]
# LM Studio server URL (OpenAI-compatible endpoint)
url = "http://localhost:1234/v1/chat/completions"
check_url = "http://localhost:1234/"

# Model to use (recommended: google/gemma-3-4b)
model = "google/gemma-3-4b"

# Maximum characters per grammar chunk (0 = no limit)
max_chars = 0

# Maximum tokens to generate (0 = no limit, uses default 2048)
max_tokens = 0

# Grammar correction timeout in seconds (0 = no limit)
timeout = 0

[audio]
# Sample rate in Hz
sample_rate = 16000

# Minimum recording duration in seconds
min_duration = 0

# Maximum recording duration in seconds (no limit)
max_duration = 0

# Minimum RMS level to consider as speech (0.0-1.0)
min_rms = 0.005

# Enable voice activity detection to trim silence
vad_enabled = true

# Apply noise reduction before transcription
noise_reduction = true

# Normalize audio levels before transcription
normalize_audio = true

# Seconds of audio to buffer before the hotkey press (captures lead-in)
# Set to 0.0 to disable (default). Set to e.g. 0.2 to capture 200ms before the hotkey.
# Note: enabling this keeps the microphone active between recordings.
pre_buffer = 0.0

[service]
# Minutes of inactivity before unloading ML models from RAM (0 = never unload)
idle_unload_minutes = 20

[ui]
# Show floating overlay window during recording
show_overlay = true

# Overlay opacity (0.0-1.0, where 1.0 is fully opaque)
overlay_opacity = 0.92

# Play sound effects
sounds_enabled = true

# Show macOS notifications on completion/error
notifications_enabled = false

# Automatically paste transcribed text at the cursor after transcription completes
auto_paste = false

[backup]
# Backup directory
directory = "~/.whisper"

# Maximum number of history entries to keep (for both text and audio)
history_limit = 100

[shortcuts]
# Enable/disable keyboard shortcuts for text transformation
enabled = true

# Shortcut for proofreading (fix spelling, grammar, punctuation only)
# Note: Use ctrl+shift instead of alt+shift because Option+Shift+letter
# produces special characters on macOS (e.g., Opt+Shift+G types ˝)
proofread = "ctrl+shift+g"

# Shortcut for rewriting (improve readability while preserving meaning)
rewrite = "ctrl+shift+r"

# Shortcut for prompt engineering (optimize text as LLM prompt)
prompt_engineer = "ctrl+shift+p"

[tts]
# Enable Text-to-Speech (select text in any app and press the shortcut to hear it read aloud)
enabled = true

provider = "kokoro"

# Shortcut to trigger/stop speech (alt = Option key on macOS)
speak_shortcut = "alt+t"

[kokoro_tts]
# Kokoro model from mlx-community (downloaded by setup.sh, runs fully offline)
model = "mlx-community/Kokoro-82M-bf16"

# Voice preset — prefix encodes language and gender:
#   American female: af_heart, af_bella, af_nova, af_sky, af_sarah, af_nicole
#   British female:  bf_alice, bf_emma (default)
#   American male:   am_adam, am_echo, am_eric, am_liam
#   British male:    bm_daniel, bm_george
voice = "af_sky"

[replacements]
# Apply text replacements after transcription (and grammar correction if enabled).
# Useful for fixing words the model consistently gets wrong, expanding abbreviations,
# or enforcing specific spelling of names and terms.
enabled = false

# Replacement rules: "spoken form" = "replacement"
# Matching is case-insensitive and respects word boundaries.
[replacements.rules]
# "open ai" = "OpenAI"
# "chat gpt" = "ChatGPT"
# "eye phone" = "iPhone"

[dictation]
# Voice dictation commands (say "new line", "period", "comma", etc. and the
# spoken phrase is replaced with the literal punctuation or whitespace).
# Defaults: new line, new paragraph, period, comma, question mark,
# exclamation mark, colon, semicolon, dash, hyphen, ellipsis, open/close paren,
# open/close quote, scratch that, strike that.
enabled = true

# Custom overrides and additions. The value is the literal replacement,
# so use \\n for newline, "" to drop a filler word.
[dictation.commands]
# "next bullet" = "\\n- "
# "smiley" = " :)"
"""


@dataclass
class TranscriptionConfig:
    engine: str = "qwen3_asr"


@dataclass
class Qwen3ASRConfig:
    model: str = "mlx-community/Qwen3-ASR-1.7B-bf16"
    language: str = "auto"
    timeout: int = 0
    prefill_step_size: int = 4096
    temperature: float = 0.0
    top_p: float = 1.0
    top_k: int = 0
    repetition_context_size: int = 100
    repetition_penalty: float = 1.2
    chunk_duration: float = 1200.0


@dataclass
class HotkeyConfig:
    key: str = "alt_r"
    double_tap_threshold: float = 0.4


@dataclass
class WhisperConfig:
    url: str = "http://localhost:50060/v1/audio/transcriptions"
    check_url: str = "http://localhost:50060/"
    model: str = "whisper-large-v3-v20240930"
    language: str = "auto"
    timeout: int = 0
    prompt: str = DEFAULT_WHISPER_PROMPT
    temperature: float = 0.0
    compression_ratio_threshold: float = 2.4
    no_speech_threshold: float = 0.6
    logprob_threshold: float = -1.0
    temperature_fallback_count: int = 5
    prompt_preset: str = "none"


@dataclass
class GrammarConfig:
    """Grammar correction settings."""
    backend: GrammarBackendType = "apple_intelligence"
    enabled: bool = False


@dataclass
class OllamaConfig:
    """Ollama-specific grammar settings."""
    url: str = "http://localhost:11434/api/generate"
    check_url: str = "http://localhost:11434/"
    model: str = "gemma3:4b-it-qat"
    max_chars: int = 0
    max_predict: int = 0
    num_ctx: int = 0
    keep_alive: str = "60m"
    timeout: int = 0
    unload_on_exit: bool = False


@dataclass
class AppleIntelligenceConfig:
    """Apple Intelligence-specific grammar settings."""
    max_chars: int = 0
    timeout: int = 0


@dataclass
class LMStudioConfig:
    """LM Studio-specific grammar settings."""
    url: str = "http://localhost:1234/v1/chat/completions"
    check_url: str = "http://localhost:1234/"
    model: str = "google/gemma-3-4b"
    max_chars: int = 0
    max_tokens: int = 0
    timeout: int = 0


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    min_duration: float = 0
    max_duration: int = 0
    min_rms: float = 0.005
    vad_enabled: bool = True
    noise_reduction: bool = True
    normalize_audio: bool = True
    pre_buffer: float = 0.0


@dataclass
class ServiceConfig:
    """Service-level lifecycle settings."""
    idle_unload_minutes: int = 20


@dataclass
class UIConfig:
    show_overlay: bool = True
    overlay_opacity: float = 0.92
    sounds_enabled: bool = True
    notifications_enabled: bool = False
    auto_paste: bool = False


@dataclass
class BackupConfig:
    directory: str = "~/.whisper"
    history_limit: int = 100

    @property
    def path(self) -> Path:
        return Path(self.directory).expanduser()


@dataclass
class ShortcutsConfig:
    """Keyboard shortcut configuration."""
    enabled: bool = True
    proofread: str = "ctrl+shift+g"
    rewrite: str = "ctrl+shift+r"
    prompt_engineer: str = "ctrl+shift+p"


@dataclass
class TTSConfig:
    """Text-to-Speech configuration."""
    enabled: bool = True
    provider: str = "kokoro"
    speak_shortcut: str = "alt+t"


@dataclass
class KokoroTTSConfig:
    """Kokoro TTS provider configuration."""
    model: str = "mlx-community/Kokoro-82M-bf16"
    voice: str = "af_sky"


@dataclass
class ReplacementsConfig:
    """Post-transcription text replacement rules."""
    enabled: bool = False
    rules: dict = field(default_factory=dict)  # {"spoken form": "replacement"}


@dataclass
class DictationConfig:
    """Voice dictation command configuration.

    When enabled, spoken phrases like "new line", "period", "comma", etc.
    are replaced with the corresponding punctuation or whitespace before
    grammar correction runs. The full default set lives in
    ``dictation_commands.DEFAULT_COMMANDS``; entries in ``commands`` here
    add to or override those defaults.
    """
    enabled: bool = True
    commands: dict = field(default_factory=dict)


@dataclass
class Config:
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    qwen3_asr: Qwen3ASRConfig = field(default_factory=Qwen3ASRConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    grammar: GrammarConfig = field(default_factory=GrammarConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    apple_intelligence: AppleIntelligenceConfig = field(default_factory=AppleIntelligenceConfig)
    lm_studio: LMStudioConfig = field(default_factory=LMStudioConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    service: ServiceConfig = field(default_factory=ServiceConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    shortcuts: ShortcutsConfig = field(default_factory=ShortcutsConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    kokoro_tts: KokoroTTSConfig = field(default_factory=KokoroTTSConfig)
    replacements: ReplacementsConfig = field(default_factory=ReplacementsConfig)
    dictation: DictationConfig = field(default_factory=DictationConfig)

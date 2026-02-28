# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Configuration management for Local Whisper.

Loads settings from ~/.whisper/config.toml with sensible defaults.
"""

import fcntl
import os
import re
import sys
import threading
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlparse

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
    ui: UIConfig = field(default_factory=UIConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    shortcuts: ShortcutsConfig = field(default_factory=ShortcutsConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    kokoro_tts: KokoroTTSConfig = field(default_factory=KokoroTTSConfig)


def load_config() -> Config:
    """Load configuration from file, creating default if missing."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        CONFIG_DIR.chmod(0o700)
    except OSError:
        pass

    # Create default config if it doesn't exist
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(DEFAULT_CONFIG, encoding='utf-8')

    # Load and parse config
    data = {}
    try:
        with open(CONFIG_FILE, 'rb') as f:
            data = tomllib.load(f)
    except Exception as e:
        print(f"Config parse error: {e}", file=sys.stderr)

    # Build config object with defaults
    config = Config()

    # Hotkey settings
    if 'hotkey' in data:
        config.hotkey = HotkeyConfig(
            key=data['hotkey'].get('key', config.hotkey.key),
            double_tap_threshold=data['hotkey'].get('double_tap_threshold', config.hotkey.double_tap_threshold),
        )

    # Transcription settings
    if 'transcription' in data:
        config.transcription = TranscriptionConfig(
            engine=data['transcription'].get('engine', config.transcription.engine),
        )

    # Qwen3 ASR settings
    if 'qwen3_asr' in data:
        config.qwen3_asr = Qwen3ASRConfig(
            model=data['qwen3_asr'].get('model', config.qwen3_asr.model),
            language=data['qwen3_asr'].get('language', config.qwen3_asr.language),
            timeout=data['qwen3_asr'].get('timeout', config.qwen3_asr.timeout),
            prefill_step_size=data['qwen3_asr'].get('prefill_step_size', config.qwen3_asr.prefill_step_size),
            temperature=data['qwen3_asr'].get('temperature', config.qwen3_asr.temperature),
            top_p=data['qwen3_asr'].get('top_p', config.qwen3_asr.top_p),
            top_k=data['qwen3_asr'].get('top_k', config.qwen3_asr.top_k),
            repetition_context_size=data['qwen3_asr'].get('repetition_context_size', config.qwen3_asr.repetition_context_size),
            repetition_penalty=data['qwen3_asr'].get('repetition_penalty', config.qwen3_asr.repetition_penalty),
            chunk_duration=data['qwen3_asr'].get('chunk_duration', config.qwen3_asr.chunk_duration),
        )

    # Whisper settings
    if 'whisper' in data:
        config.whisper = WhisperConfig(
            url=data['whisper'].get('url', config.whisper.url),
            check_url=data['whisper'].get('check_url', config.whisper.check_url),
            model=data['whisper'].get('model', config.whisper.model),
            language=data['whisper'].get('language', config.whisper.language),
            timeout=data['whisper'].get('timeout', config.whisper.timeout),
            prompt=data['whisper'].get('prompt', config.whisper.prompt),
            temperature=data['whisper'].get('temperature', config.whisper.temperature),
            compression_ratio_threshold=data['whisper'].get('compression_ratio_threshold', config.whisper.compression_ratio_threshold),
            no_speech_threshold=data['whisper'].get('no_speech_threshold', config.whisper.no_speech_threshold),
            logprob_threshold=data['whisper'].get('logprob_threshold', config.whisper.logprob_threshold),
            temperature_fallback_count=data['whisper'].get('temperature_fallback_count', config.whisper.temperature_fallback_count),
            prompt_preset=data['whisper'].get('prompt_preset', config.whisper.prompt_preset),
        )

    # Grammar settings
    if 'grammar' in data:
        config.grammar = GrammarConfig(
            backend=data['grammar'].get('backend', config.grammar.backend),
            enabled=data['grammar'].get('enabled', config.grammar.enabled),
        )

    # Ollama settings
    if 'ollama' in data:
        config.ollama = OllamaConfig(
            url=data['ollama'].get('url', config.ollama.url),
            check_url=data['ollama'].get('check_url', config.ollama.check_url),
            model=data['ollama'].get('model', config.ollama.model),
            max_chars=data['ollama'].get('max_chars', config.ollama.max_chars),
            max_predict=data['ollama'].get('max_predict', config.ollama.max_predict),
            num_ctx=data['ollama'].get('num_ctx', config.ollama.num_ctx),
            keep_alive=data['ollama'].get('keep_alive', config.ollama.keep_alive),
            timeout=data['ollama'].get('timeout', config.ollama.timeout),
            unload_on_exit=data['ollama'].get('unload_on_exit', config.ollama.unload_on_exit),
        )

    # Apple Intelligence settings
    if 'apple_intelligence' in data:
        config.apple_intelligence = AppleIntelligenceConfig(
            max_chars=data['apple_intelligence'].get('max_chars', config.apple_intelligence.max_chars),
            timeout=data['apple_intelligence'].get('timeout', config.apple_intelligence.timeout),
        )

    # LM Studio settings
    if 'lm_studio' in data:
        config.lm_studio = LMStudioConfig(
            url=data['lm_studio'].get('url', config.lm_studio.url),
            check_url=data['lm_studio'].get('check_url', config.lm_studio.check_url),
            model=data['lm_studio'].get('model', config.lm_studio.model),
            max_chars=data['lm_studio'].get('max_chars', config.lm_studio.max_chars),
            max_tokens=data['lm_studio'].get('max_tokens', config.lm_studio.max_tokens),
            timeout=data['lm_studio'].get('timeout', config.lm_studio.timeout),
        )

    # Audio settings
    if 'audio' in data:
        config.audio = AudioConfig(
            sample_rate=data['audio'].get('sample_rate', config.audio.sample_rate),
            min_duration=data['audio'].get('min_duration', config.audio.min_duration),
            max_duration=data['audio'].get('max_duration', config.audio.max_duration),
            min_rms=data['audio'].get('min_rms', config.audio.min_rms),
            vad_enabled=data['audio'].get('vad_enabled', config.audio.vad_enabled),
            noise_reduction=data['audio'].get('noise_reduction', config.audio.noise_reduction),
            normalize_audio=data['audio'].get('normalize_audio', config.audio.normalize_audio),
            pre_buffer=data['audio'].get('pre_buffer', config.audio.pre_buffer),
        )

    # UI settings
    if 'ui' in data:
        config.ui = UIConfig(
            show_overlay=data['ui'].get('show_overlay', config.ui.show_overlay),
            overlay_opacity=data['ui'].get('overlay_opacity', config.ui.overlay_opacity),
            sounds_enabled=data['ui'].get('sounds_enabled', config.ui.sounds_enabled),
            notifications_enabled=data['ui'].get('notifications_enabled', config.ui.notifications_enabled),
            auto_paste=data['ui'].get('auto_paste', config.ui.auto_paste),
        )

    # Backup settings
    if 'backup' in data:
        config.backup = BackupConfig(
            directory=data['backup'].get('directory', config.backup.directory),
            history_limit=data['backup'].get('history_limit', config.backup.history_limit),
        )

    # Shortcuts settings
    if 'shortcuts' in data:
        config.shortcuts = ShortcutsConfig(
            enabled=data['shortcuts'].get('enabled', config.shortcuts.enabled),
            proofread=data['shortcuts'].get('proofread', config.shortcuts.proofread),
            rewrite=data['shortcuts'].get('rewrite', config.shortcuts.rewrite),
            prompt_engineer=data['shortcuts'].get('prompt_engineer', config.shortcuts.prompt_engineer),
        )

    # TTS settings
    if 'tts' in data:
        config.tts = TTSConfig(
            enabled=data['tts'].get('enabled', config.tts.enabled),
            provider=data['tts'].get('provider', config.tts.provider),
            speak_shortcut=data['tts'].get('speak_shortcut', config.tts.speak_shortcut),
        )

    # Kokoro TTS settings
    if 'kokoro_tts' in data:
        config.kokoro_tts = KokoroTTSConfig(
            model=data['kokoro_tts'].get('model', config.kokoro_tts.model),
            voice=data['kokoro_tts'].get('voice', config.kokoro_tts.voice),
        )

    # Validate and sanitize config values
    _validate_config(config)

    return config


def _is_valid_url(url: str) -> bool:
    """Check if a string is a valid HTTP/HTTPS URL."""
    try:
        result = urlparse(url)
        return result.scheme in ("http", "https") and bool(result.netloc)
    except (ValueError, AttributeError):
        return False


def _validate_config(config: Config):
    """Validate and sanitize configuration values."""
    # URL validation
    if not _is_valid_url(config.whisper.url):
        print(f"Config warning: Invalid whisper URL '{config.whisper.url}', using default", file=sys.stderr)
        config.whisper.url = "http://localhost:50060/v1/audio/transcriptions"

    if not _is_valid_url(config.whisper.check_url):
        print(f"Config warning: Invalid whisper check_url '{config.whisper.check_url}', using default", file=sys.stderr)
        config.whisper.check_url = "http://localhost:50060/"

    # Ollama URL validation
    if not _is_valid_url(config.ollama.url):
        print(f"Config warning: Invalid ollama URL '{config.ollama.url}', using default", file=sys.stderr)
        config.ollama.url = "http://localhost:11434/api/generate"

    if not _is_valid_url(config.ollama.check_url):
        print(f"Config warning: Invalid ollama check_url '{config.ollama.check_url}', using default", file=sys.stderr)
        config.ollama.check_url = "http://localhost:11434/"

    # LM Studio URL validation
    if not _is_valid_url(config.lm_studio.url):
        print(f"Config warning: Invalid lm_studio URL '{config.lm_studio.url}', using default", file=sys.stderr)
        config.lm_studio.url = "http://localhost:1234/v1/chat/completions"

    if not _is_valid_url(config.lm_studio.check_url):
        print(f"Config warning: Invalid lm_studio check_url '{config.lm_studio.check_url}', using default", file=sys.stderr)
        config.lm_studio.check_url = "http://localhost:1234/"

    # Transcription engine validation
    if config.transcription.engine not in ("qwen3_asr", "whisperkit"):
        print(f"Config warning: Invalid transcription engine '{config.transcription.engine}', using 'qwen3_asr'", file=sys.stderr)
        config.transcription.engine = "qwen3_asr"

    # Grammar backend validation
    if config.grammar.backend == "none":
        config.grammar.enabled = False
    elif config.grammar.enabled and config.grammar.backend not in GRAMMAR_BACKENDS:
        print(f"Config warning: Invalid grammar backend '{config.grammar.backend}', using 'apple_intelligence'", file=sys.stderr)
        config.grammar.backend = "apple_intelligence"

    # Hotkey validation
    valid_keys = {
        "alt_r", "alt_l", "ctrl_r", "ctrl_l", "cmd_r", "cmd_l",
        "shift_r", "shift_l", "caps_lock",
        "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12"
    }
    if config.hotkey.key not in valid_keys:
        print(f"Config warning: Invalid hotkey '{config.hotkey.key}', using 'alt_r'", file=sys.stderr)
        config.hotkey.key = "alt_r"

    if config.hotkey.double_tap_threshold <= 0:
        print("Config warning: double_tap_threshold must be positive, using 0.4", file=sys.stderr)
        config.hotkey.double_tap_threshold = 0.4

    # Audio validation
    if config.audio.sample_rate <= 0:
        print("Config warning: sample_rate must be positive, using 16000", file=sys.stderr)
        config.audio.sample_rate = 16000

    # Warn if sample rate is not Whisper-compatible (16000 Hz is standard)
    if config.audio.sample_rate != 16000:
        print(f"Config warning: sample_rate {config.audio.sample_rate} may not be compatible with Whisper (16000 recommended)", file=sys.stderr)

    if config.audio.min_duration < 0:
        config.audio.min_duration = 0

    # Ensure max_duration is non-negative and integer
    if isinstance(config.audio.max_duration, float):
        config.audio.max_duration = int(config.audio.max_duration)
    if config.audio.max_duration < 0:
        print("Config warning: max_duration cannot be negative, using 0 (unlimited)", file=sys.stderr)
        config.audio.max_duration = 0

    if not 0.0 <= config.audio.min_rms <= 1.0:
        print("Config warning: min_rms must be between 0.0 and 1.0, using 0.005", file=sys.stderr)
        config.audio.min_rms = 0.005

    # pre_buffer: clamp to 0.0-1.0
    if config.audio.pre_buffer < 0.0:
        config.audio.pre_buffer = 0.0
    elif config.audio.pre_buffer > 1.0:
        config.audio.pre_buffer = 1.0

    # Whisper decoding parameters
    if not 0.0 <= config.whisper.temperature <= 1.0:
        print("Config warning: whisper temperature must be between 0.0 and 1.0, using 0.0", file=sys.stderr)
        config.whisper.temperature = 0.0

    if config.whisper.compression_ratio_threshold <= 0:
        print("Config warning: compression_ratio_threshold must be positive, using 2.4", file=sys.stderr)
        config.whisper.compression_ratio_threshold = 2.4

    if not 0.0 <= config.whisper.no_speech_threshold <= 1.0:
        print("Config warning: no_speech_threshold must be between 0.0 and 1.0, using 0.6", file=sys.stderr)
        config.whisper.no_speech_threshold = 0.6

    if config.whisper.temperature_fallback_count < 0:
        print("Config warning: temperature_fallback_count cannot be negative, using 5", file=sys.stderr)
        config.whisper.temperature_fallback_count = 5

    _valid_prompt_presets = ("none", "technical", "dictation", "custom")
    if config.whisper.prompt_preset not in _valid_prompt_presets:
        print(f"Config warning: invalid prompt_preset '{config.whisper.prompt_preset}', using 'none'", file=sys.stderr)
        config.whisper.prompt_preset = "none"

    # Backup validation
    if not isinstance(config.backup.history_limit, int) or config.backup.history_limit < 1:
        print("Config warning: history_limit must be a positive integer, using 100", file=sys.stderr)
        config.backup.history_limit = 100
    elif config.backup.history_limit > 1000:
        print("Config warning: history_limit clamped to 1000", file=sys.stderr)
        config.backup.history_limit = 1000

    # UI validation
    if not 0.0 <= config.ui.overlay_opacity <= 1.0:
        print("Config warning: overlay_opacity must be between 0.0 and 1.0, using 0.92", file=sys.stderr)
        config.ui.overlay_opacity = 0.92


# Global config instance with thread-safe initialization
_config: Optional[Config] = None
_config_lock = threading.Lock()


def get_config() -> Config:
    """Get the global configuration instance (thread-safe)."""
    global _config
    if _config is None:
        with _config_lock:
            # Double-check locking pattern for thread safety
            if _config is None:
                _config = load_config()
    return _config


# ---------------------------------------------------------------------------
# TOML section helpers (shared by config.py and cli.py)
# ---------------------------------------------------------------------------

def _find_in_section(content: str, section: str, key: str) -> Optional[str]:
    """Find a key's value within a specific TOML section. Returns the value or None."""
    in_section = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == f"[{section}]"
            continue
        if in_section:
            m = re.match(rf'{key}\s*=\s*"([^"]*)"', stripped)
            if m:
                return m.group(1)
            # Also match unquoted booleans
            m = re.match(rf'{key}\s*=\s*(true|false)', stripped)
            if m:
                return m.group(1)
            # Also match unquoted numeric values (integer or float)
            m = re.match(rf'{key}\s*=\s*([-+]?[0-9]*\.?[0-9]+)', stripped)
            if m:
                return m.group(1)
    return None


def _replace_in_section(content: str, section: str, key: str, new_value: str) -> str:
    """Replace a key's value within a specific TOML section.

    new_value must already be serialized to its TOML string representation
    (e.g. '"quoted"' for strings, 'true'/'false' for bools, '42' for ints).

    If the key doesn't exist in the section, it is appended under the header.
    """
    lines = content.splitlines(keepends=True)
    in_section = False
    section_header_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == f"[{section}]"
            if in_section:
                section_header_idx = i
            continue
        if in_section:
            repl = r'\g<1>' + new_value
            # Match quoted string value
            new_line = re.sub(
                rf'({key}\s*=\s*)"[^"]*"',
                repl,
                line
            )
            if new_line != line:
                lines[i] = new_line
                return "".join(lines)
            # Match unquoted boolean
            new_line = re.sub(
                rf'({key}\s*=\s*)(true|false)',
                repl,
                line
            )
            if new_line != line:
                lines[i] = new_line
                return "".join(lines)
            # Match unquoted numeric (integer or float)
            new_line = re.sub(
                rf'({key}\s*=\s*)[-+]?[0-9]*\.?[0-9]+',
                repl,
                line
            )
            if new_line != line:
                lines[i] = new_line
                return "".join(lines)

    # Key not found in section - append it after the section header
    if section_header_idx is not None:
        new_line = f"{key} = {new_value}\n"
        lines.insert(section_header_idx + 1, new_line)
        return "".join(lines)

    # Section not found at all - append a new section at the end of the file
    lines.append(f"\n[{section}]\n")
    lines.append(f"{key} = {new_value}\n")
    return "".join(lines)


def update_config_backend(new_backend: str) -> bool:
    """Update grammar backend in-memory AND persist to TOML file."""
    config = get_config()
    with _config_lock:
        config.grammar.backend = new_backend
        config.grammar.enabled = (new_backend != "none")
    try:
        fd = os.open(str(CONFIG_FILE), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            content = CONFIG_FILE.read_text()
            content = _replace_in_section(content, "grammar", "backend", _serialize_toml_value(new_backend))
            enabled_val = "false" if new_backend == "none" else "true"
            content = _replace_in_section(content, "grammar", "enabled", enabled_val)
            CONFIG_FILE.write_text(content)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return True
    except Exception as e:
        print(f"Config write failed: {e}", file=sys.stderr)
        return False


def _serialize_toml_value(value) -> str:
    """Serialize a Python value to its TOML string representation."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    # String: escape backslashes and quotes, wrap in double quotes
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def update_config_field(section: str, key: str, value) -> bool:
    """Update a single config field in-memory AND persist to TOML.

    value may be a bool, int, float, or str. Serialization is handled
    automatically so callers pass Python-native values directly.
    """
    config = get_config()
    section_obj = getattr(config, section, None)
    if section_obj is not None and hasattr(section_obj, key):
        setattr(section_obj, key, value)
    try:
        fd = os.open(str(CONFIG_FILE), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            content = CONFIG_FILE.read_text()
            toml_value = _serialize_toml_value(value)
            content = _replace_in_section(content, section, key, toml_value)
            CONFIG_FILE.write_text(content)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return True
    except Exception as e:
        print(f"Config write failed: {e}", file=sys.stderr)
        return False

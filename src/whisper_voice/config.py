"""
Configuration management for Local Whisper.

Loads settings from ~/.whisper/config.toml with sensible defaults.
"""

import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

# tomllib is Python 3.11+, fall back to tomli for older versions
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None
from dataclasses import dataclass, field
from typing import Optional, Literal

CONFIG_DIR = Path.home() / ".whisper"
CONFIG_FILE = CONFIG_DIR / "config.toml"

# Available grammar backends
GRAMMAR_BACKENDS = ("ollama", "apple_intelligence", "lm_studio")
GrammarBackendType = Literal["ollama", "apple_intelligence", "lm_studio"]

# Default transcription prompt. Empty by default to avoid confusing Whisper.
# Whisper's prompt parameter is meant for vocabulary hints only, not conversational context.
DEFAULT_WHISPER_PROMPT = ""

# Default configuration
DEFAULT_CONFIG = f"""# Local Whisper Configuration
# Edit this file to customize behavior

[hotkey]
# Key to use for recording trigger
# Options: alt_r, alt_l, ctrl_r, ctrl_l, cmd_r, cmd_l, shift_r, shift_l, caps_lock, f1-f12
key = "alt_r"

# Double-tap threshold in seconds (how fast you need to tap twice)
double_tap_threshold = 0.4

[whisper]
# WhisperKit server URL
url = "http://localhost:50060/v1/audio/transcriptions"
check_url = "http://localhost:50060/"

# Whisper model to use
model = "openai_whisper-large-v3-v20240930"

# Language code (en, fa, es, fr, de, etc. or "auto" for detection)
language = "auto"

# Transcription timeout in seconds (no limit)
timeout = 0

# Optional vocabulary hint for transcription.
# Whisper's prompt parameter is meant for vocabulary hints (technical terms, names)
# NOT conversational context. Using conversational prompts causes truncated or empty results.
# Leave empty unless you need to hint specific vocabulary.
prompt = ""

[grammar]
# Grammar correction backend: "apple_intelligence", "ollama", or "lm_studio"
backend = "apple_intelligence"

# Enable/disable grammar correction
enabled = true

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

[ui]
# Show floating overlay window during recording
show_overlay = true

# Overlay opacity (0.0-1.0, where 1.0 is fully opaque)
overlay_opacity = 0.92

# Play sound effects
sounds_enabled = true

[backup]
# Backup directory
directory = "~/.whisper"

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
"""


@dataclass
class HotkeyConfig:
    key: str = "alt_r"
    double_tap_threshold: float = 0.4


@dataclass
class WhisperConfig:
    url: str = "http://localhost:50060/v1/audio/transcriptions"
    check_url: str = "http://localhost:50060/"
    model: str = "openai_whisper-large-v3-v20240930"
    language: str = "auto"
    timeout: int = 0
    prompt: str = DEFAULT_WHISPER_PROMPT


@dataclass
class GrammarConfig:
    """Grammar correction settings."""
    backend: GrammarBackendType = "apple_intelligence"
    enabled: bool = True


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


@dataclass
class UIConfig:
    show_overlay: bool = True
    overlay_opacity: float = 0.92
    sounds_enabled: bool = True


@dataclass
class BackupConfig:
    directory: str = "~/.whisper"

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
class Config:
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    grammar: GrammarConfig = field(default_factory=GrammarConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    apple_intelligence: AppleIntelligenceConfig = field(default_factory=AppleIntelligenceConfig)
    lm_studio: LMStudioConfig = field(default_factory=LMStudioConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    shortcuts: ShortcutsConfig = field(default_factory=ShortcutsConfig)


def load_config() -> Config:
    """Load configuration from file, creating default if missing."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Create default config if it doesn't exist
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(DEFAULT_CONFIG, encoding='utf-8')

    # Load and parse config
    data = {}
    if tomllib is not None:
        try:
            with open(CONFIG_FILE, 'rb') as f:
                data = tomllib.load(f)
        except Exception as e:
            print(f"Config parse error: {e}", file=sys.stderr)
    else:
        print("Config parse warning: tomli not available", file=sys.stderr)

    # Build config object with defaults
    config = Config()

    # Hotkey settings
    if 'hotkey' in data:
        config.hotkey = HotkeyConfig(
            key=data['hotkey'].get('key', config.hotkey.key),
            double_tap_threshold=data['hotkey'].get('double_tap_threshold', config.hotkey.double_tap_threshold),
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
        )

    # UI settings
    if 'ui' in data:
        config.ui = UIConfig(
            show_overlay=data['ui'].get('show_overlay', config.ui.show_overlay),
            overlay_opacity=data['ui'].get('overlay_opacity', config.ui.overlay_opacity),
            sounds_enabled=data['ui'].get('sounds_enabled', config.ui.sounds_enabled),
        )

    # Backup settings
    if 'backup' in data:
        config.backup = BackupConfig(
            directory=data['backup'].get('directory', config.backup.directory),
        )

    # Shortcuts settings
    if 'shortcuts' in data:
        config.shortcuts = ShortcutsConfig(
            enabled=data['shortcuts'].get('enabled', config.shortcuts.enabled),
            proofread=data['shortcuts'].get('proofread', config.shortcuts.proofread),
            rewrite=data['shortcuts'].get('rewrite', config.shortcuts.rewrite),
            prompt_engineer=data['shortcuts'].get('prompt_engineer', config.shortcuts.prompt_engineer),
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

    # Grammar backend validation
    if config.grammar.backend not in GRAMMAR_BACKENDS:
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

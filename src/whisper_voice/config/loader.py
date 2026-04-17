# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Configuration loader: reads config.toml and returns a Config instance.
"""

import sys
import threading
import tomllib
from typing import Optional
from urllib.parse import urlparse

from . import schema as _schema
from .schema import (
    AppleIntelligenceConfig,
    AudioConfig,
    BackupConfig,
    Config,
    DictationConfig,
    GrammarConfig,
    HotkeyConfig,
    KokoroTTSConfig,
    LMStudioConfig,
    OllamaConfig,
    Qwen3ASRConfig,
    ReplacementsConfig,
    ShortcutsConfig,
    TranscriptionConfig,
    TTSConfig,
    UIConfig,
    WhisperConfig,
)


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

    # Transcription engine validation — derive from the live registry so adding an
    # engine in engines/__init__.py alone enables it without touching the validator.
    from ..engines import ENGINE_REGISTRY
    valid_engines = tuple(ENGINE_REGISTRY.keys())
    if valid_engines and config.transcription.engine not in valid_engines:
        default_engine = "qwen3_asr" if "qwen3_asr" in valid_engines else valid_engines[0]
        print(
            f"Config warning: Invalid transcription engine '{config.transcription.engine}', using '{default_engine}'",
            file=sys.stderr,
        )
        config.transcription.engine = default_engine

    # Grammar backend validation — same pattern against BACKEND_REGISTRY.
    from ..backends import BACKEND_REGISTRY
    valid_backends = tuple(BACKEND_REGISTRY.keys())
    if config.grammar.backend == "none":
        config.grammar.enabled = False
    elif config.grammar.enabled and valid_backends and config.grammar.backend not in valid_backends:
        default_backend = "apple_intelligence" if "apple_intelligence" in valid_backends else valid_backends[0]
        print(
            f"Config warning: Invalid grammar backend '{config.grammar.backend}', using '{default_backend}'",
            file=sys.stderr,
        )
        config.grammar.backend = default_backend

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


def load_config() -> Config:
    """Load configuration from file, creating default if missing."""
    _schema.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _schema.CONFIG_DIR.chmod(0o700)
    except OSError:
        pass

    # Create default config if it doesn't exist
    if not _schema.CONFIG_FILE.exists():
        _schema.CONFIG_FILE.write_text(_schema.DEFAULT_CONFIG, encoding='utf-8')

    # Load and parse config
    data = {}
    try:
        with open(_schema.CONFIG_FILE, 'rb') as f:
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

    # Replacements settings
    if 'replacements' in data:
        rules = data['replacements'].get('rules', {})
        # Ensure rules is a flat dict of str -> str
        if isinstance(rules, dict):
            rules = {str(k): str(v) for k, v in rules.items()}
        else:
            rules = {}
        config.replacements = ReplacementsConfig(
            enabled=data['replacements'].get('enabled', config.replacements.enabled),
            rules=rules,
        )

    # Dictation commands
    if 'dictation' in data:
        commands = data['dictation'].get('commands', {})
        if isinstance(commands, dict):
            commands = {str(k): str(v) for k, v in commands.items()}
        else:
            commands = {}
        config.dictation = DictationConfig(
            enabled=data['dictation'].get('enabled', config.dictation.enabled),
            commands=commands,
        )

    # Validate and sanitize config values
    _validate_config(config)

    return config


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

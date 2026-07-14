# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""
Configuration package for Local Whisper.

Re-exports all public names so existing import paths continue to work:
  from whisper_voice.config import get_config, Config, ...
  from .config import get_config, CONFIG_FILE, ...
  from ..config import get_config, ...
  from ...config import get_config, ...
"""

from .loader import (
    _is_valid_url,
    _validate_config,
    get_config,
    load_config,
    reload_config,
)
from .mutations import (
    _read_replacements_rules,
    _write_replacements_rules,
    add_dictation_command,
    add_replacement,
    add_replacements,
    remove_dictation_command,
    remove_replacement,
    update_config_backend,
    update_config_field,
)
from .schema import (
    CONFIG_DIR,
    CONFIG_FILE,
    DEFAULT_CONFIG,
    DEFAULT_WHISPER_PROMPT,
    GRAMMAR_BACKENDS,
    AppleIntelligenceConfig,
    AppleSpeechConfig,
    AudioConfig,
    BackupConfig,
    Config,
    DictationConfig,
    GrammarBackendType,
    GrammarConfig,
    HotkeyConfig,
    KokoroTTSConfig,
    LMStudioConfig,
    OllamaConfig,
    ParakeetConfig,
    Qwen3ASRConfig,
    ReplacementsConfig,
    ServiceConfig,
    ShortcutsConfig,
    TranscriptionConfig,
    TTSConfig,
    UIConfig,
    WhisperConfig,
)
from .toml_helpers import (
    _find_in_section,
    _replace_in_section,
    _serialize_toml_value,
)

__all__ = [
    # schema
    "CONFIG_DIR",
    "CONFIG_FILE",
    "DEFAULT_CONFIG",
    "GRAMMAR_BACKENDS",
    "GrammarBackendType",
    "DEFAULT_WHISPER_PROMPT",
    "TranscriptionConfig",
    "ParakeetConfig",
    "Qwen3ASRConfig",
    "HotkeyConfig",
    "WhisperConfig",
    "GrammarConfig",
    "OllamaConfig",
    "AppleIntelligenceConfig",
    "AppleSpeechConfig",
    "LMStudioConfig",
    "AudioConfig",
    "UIConfig",
    "BackupConfig",
    "ServiceConfig",
    "ShortcutsConfig",
    "TTSConfig",
    "KokoroTTSConfig",
    "ReplacementsConfig",
    "DictationConfig",
    "Config",
    # loader
    "load_config",
    "get_config",
    "reload_config",
    "_is_valid_url",
    "_validate_config",
    # toml_helpers
    "_find_in_section",
    "_replace_in_section",
    "_serialize_toml_value",
    # mutations
    "_read_replacements_rules",
    "_write_replacements_rules",
    "add_dictation_command",
    "add_replacement",
    "add_replacements",
    "remove_dictation_command",
    "remove_replacement",
    "update_config_backend",
    "update_config_field",
]

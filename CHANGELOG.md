# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.1.0] - 2026-02-25

### Added

- Native SwiftUI interface targeting macOS 26 with Liquid Glass design throughout.
- Menu bar app with a full dropdown menu for grammar and engine selection, transcription history, and recordings.
- Floating overlay pill with glass effect showing recording duration, live audio levels, and processing status.
- Settings window with native macOS grouped forms across three tabs (General, Advanced, About).
- Real-time status updates in the menu bar and overlay during recording, processing, and transcription.
- Keyboard shortcuts in the menu bar: Cmd+R to retry, Cmd+Shift+C to copy last result, Cmd+, for settings, Cmd+Q to quit.
- Qwen3-ASR bf16 model (full precision) as the default for maximum transcription quality.
- Language auto-detection for Qwen3-ASR.
- Model warm-up during setup so the first transcription starts without delay.
- Ollama model list fetched live in settings (pulls installed models automatically).
- Engine switching with automatic rollback: if the new engine fails to start, the previous engine stays active.
- Clear error message when WhisperKit CLI is not installed.

### Changed

- Default Qwen3-ASR model upgraded from 1.7B-8bit to 1.7B-bf16 for higher quality output.
- Setup no longer installs WhisperKit by default; install it manually if needed.
- Text fields in settings save on Enter or focus loss instead of on every keystroke.
- Repetition penalty (1.2) added to Qwen3-ASR to reduce hallucination on short or silent recordings.

### Removed

- Python GUI layer (the previous rumps menu bar, AppKit recording overlay, and NSPanel settings window).
- rumps dependency.

---

## [1.0.1] - 2026-02-24

### Added

- Qwen3-ASR is now the default transcription engine, running fully in-process with no server required. It handles recordings up to 20 minutes natively.
- WhisperKit remains available as an alternative engine. Switch between engines via `wh engine <name>`, the Settings window, or by editing the config.
- Audio pre-processing pipeline applied before every transcription: voice activity detection, silence trimming, spectral noise reduction, and level normalization.
- Pre-recording buffer captures a short window of audio before the hotkey fires, so the first syllable is never clipped. Configurable via `pre_buffer` in config.
- Real-time audio level indicator in the recording overlay, color-coded by loudness.
- Engine selection and audio processing options exposed in the Settings window.
- History menu replaced with two dedicated submenus: Transcriptions shows the last 100 transcribed texts (newest first, click to copy), Recordings shows audio recordings (click to reveal in Finder). Both submenus rebuild lazily and include an "Open Folder" item.
- "Open Config File" button in Settings Advanced tab for quick access to config.toml.

### Changed

- Default transcription engine is now Qwen3-ASR instead of WhisperKit. Existing installs will continue using whichever engine is set in config; new installs default to Qwen3-ASR.
- Long recordings (over 28 seconds) are only split into segments when using WhisperKit. Qwen3-ASR handles them as a single pass.
- Completion notifications are now off by default.
- Settings window reorganized from 6 tabs to 3 (General, Advanced, About). Everyday options in General, power-user tuning in Advanced.
- Menu bar cleaned up: "Audio Files" renamed to "Recordings", "Backups" and "Config" items removed (redundant with in-app alternatives).
- Settings window now reliably opens over fullscreen apps.

---

## [1.0.0] - 2026-02-23

### Added

- Community files: Contributing guide, Code of Conduct, Security policy
- GitHub issue templates for bug reports and feature requests
- Pull request template
- GitHub config: Dependabot, CODEOWNERS, EditorConfig, FUNDING
- Writing rules for consistent documentation style
- Project metadata in `pyproject.toml` (author, URLs)

### Changed

- README rewritten with improved descriptions, requirements, and usage instructions
- Test fixtures updated to reflect new model naming conventions

---

### 2026-02-22

- In-process backend switching from the Grammar submenu (no restart needed)
- Settings window with 3 tabs (General, Advanced, About)
- `wh build` command for explicit Swift CLI rebuilds
- Notifications toggle in Settings
- macOS notifications on transcription success, failure, and errors
- Long text chunking via `max_chars` for large transcriptions across all backends
- One-step `setup.sh` with inline LaunchAgent install and WhisperKit model pre-compilation
- Hardened `setup.sh` with binary verification, accessibility re-verification, and fish shell hint
- About tab with version info, author, and credits (two-column row layout)
- Config writes now update only changed fields instead of rewriting the file
- Config writer appends missing keys instead of silently skipping them
- `overlay_opacity` added to restart-required settings

### 2026-02-21

- `wh` CLI service controller (`start`, `stop`, `restart`, `status`, `log`, `config`, `backend`, `uninstall`)
- LaunchAgent-based service deployment, replacing the `.app` bundle approach
- macOS Login Item support with single-instance lock
- Auto-start at login via LaunchAgent
- Accessibility permission prompt on startup if not granted
- `wh uninstall` for complete cleanup (service, LaunchAgent, config, logs, shell alias)
- Default Whisper model updated to `openai_whisper-large-v3-v20240930`
- Default Whisper language set to auto-detect
- Shell alias auto-added during setup
- Legacy Login Item and old LaunchAgent cleaned up on upgrade
- Fixed UTF-8 encoding on service log file

### 2026-02-18

- Microphone permission check with user-friendly error on startup
- Silent audio detection to skip empty recordings

### 2026-01-30

- Global keyboard shortcuts for text transformation (Ctrl+Shift+G for proofread, Ctrl+Shift+R for rewrite, Ctrl+Shift+P for prompt engineer)
- CGEventTap-based keyboard interception with proper event suppression
- Extensible modes system for text transformations
- Accessibility-first text retrieval with clipboard fallback
- Consolidated prompt files into `modes.py`

### 2026-01-28

- Enhanced session management with error handling and retry logic

### 2026-01-22 – 2026-01-24

- Refactored entire codebase from "proofreading" to "grammar correction" terminology
- Switched grammar backends to proofreading-only mode (no creative rewriting)
- Updated default WhisperKit model to `large-v3-v20240930_626MB`
- Added transcription prompt parameter for professional guidance
- Fixed conversational prompt that was confusing Whisper transcription output

### 2025-12-23

- Refined grammar correction prompts for consistency across all backends
- Improved output formatting instructions

### 2025-12-21

- Initial commit
- WhisperKit-based local transcription (Apple Silicon, fully on-device)
- Apple Intelligence, Ollama, and LM Studio grammar backends
- Modular backend system with registry and factory pattern
- Menu bar interface with recording overlay
- Double-tap Right Option to record, single tap to stop
- Audio backup and session history to `~/.whisper/`
- Hallucination filter for common Whisper false outputs
- Configuration via `~/.whisper/config.toml`

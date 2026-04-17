# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- Toggling "Enable grammar correction" in Settings now actually loads or unloads the backend in-process instead of only writing the flag to config and leaving the model dangling.
- `⌥T` text-to-speech no longer clobbers the clipboard when it falls back to Cmd+C for text selection. The prior clipboard contents are saved and restored.
- Dead icon constants (`ICON_*`, `OVERLAY_WAVE_FRAMES`, `ANIM_INTERVAL_*`) and the dead `hide_dock_icon()` helper in `utils.py` removed. Asset imports no longer hard-crash the entire CLI if a single bundled PNG is missing.
- WhisperKit engine no longer accumulates `atexit` handlers across engine switches, and now fails fast if the server subprocess dies during startup instead of polling a dead PID for five minutes.
- Kokoro TTS model load is serialized through a dedicated lock so two callers cannot both pay the download cost in parallel on first use.
- Transcription engine and grammar backend validation in the config loader now derives valid values from the live registries. Registering a new engine or backend works with a single registry edit.
- `wh listen` now re-arms the pre-recording monitor stream when it finishes, so a subsequent hotkey capture still gets the configured pre-buffer.
- `wh update` aborts cleanly when `git pull` or `pip install` fails and prints the exact rollback command (`git reset --hard <sha>`) so the service never restarts against half-applied changes.
- `wh config show` piped into another command now exits non-zero when the config file is missing instead of silently succeeding.
- `wh uninstall` waits up to two seconds for graceful SIGTERM shutdown before escalating to SIGKILL, and surfaces the source-install venv path so users know exactly what remains to clean up.
- `wh doctor --fix` reports a real failure if `launchctl load` returns non-zero instead of printing "loaded" regardless.
- Ollama model list fetch in Advanced settings now uses a 5-second timeout so a stopped Ollama server no longer hangs the button indefinitely.
- About tab no longer force-unwraps credit URLs; a malformed string silently no-ops instead of crashing.
- `DeferredTextField`, `DeferredIntTextField`, and `DeferredTextEditor` now pick up external `config_snapshot` updates when the field is unfocused, so settings no longer appear stale after a backend or engine switch.
- `DeferredIntTextField` resets to the last committed value when the user leaves a non-parseable value in the field (previously it stayed diverged from the service indefinitely).
- `audio_processor._istft` uses an explicit `raise` instead of `assert` so its STFT overlap invariant holds under `python -O`.

### Changed

- Command socket protocol requests now use the `action` key (`{"action": "listen", ...}`) to match response framing and documentation. Existing `wh listen / whisper / transcribe` CLI invocations are unaffected; only direct socket clients need updating.
- Apple Intelligence backend is now installed on macOS 15 and later (was gated on macOS 26+). The `.glassEffect` Swift UI still requires macOS 26.
- `./setup.sh` skips the Qwen3-ASR warm-up and the spaCy `en_core_web_sm` download when a sentinel or the already-installed module is detected, so re-running setup no longer repeats a two-minute warm-up or re-downloads models that are already present.
- Swift compiler warnings are surfaced to stderr on successful builds (previously they were deleted with the build log).

---

## [1.3.0] - 2026-02-27

### Added

- Auto-paste at cursor: when enabled in General settings (`auto_paste`), transcribed text is pasted directly at the active cursor position after transcription. Your clipboard is untouched. Disabled by default.
- Text to Speech: select text in any app and press ⌥T to hear it read aloud. Kokoro-82M synthesizes speech entirely on-device with no network required.
- Multiple voice presets with prefix-encoded language and gender. Default voice: `af_sky`. Selectable from General settings.
- Overlay shows "Generating speech..." while the model synthesizes, then "Speaking..." once audio starts playing.
- Press ⌥T again, Esc, or start a recording to stop speech at any point, including during model generation.
- Kokoro TTS model downloaded automatically during `setup.sh` and stored in `~/.whisper/models/`. Removed cleanly by `wh uninstall`.

---

## [1.2.0] - 2026-02-26

### Changed

- Apple Intelligence backend runs on-device via Apple's official Foundation Models Python SDK (`apple-fm-sdk`).

---

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

- Default Qwen3-ASR model is the 1.7B-bf16 variant for maximum transcription quality.
- WhisperKit is an optional engine. Install manually with `brew install whisperkit-cli` if needed.
- Text fields in settings save on Enter or focus loss instead of on every keystroke.
- Repetition penalty (1.2) added to Qwen3-ASR to reduce hallucination on short or silent recordings.

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

- Qwen3-ASR is the default transcription engine. New installs use it out of the box; the engine is configurable via config or Settings.
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

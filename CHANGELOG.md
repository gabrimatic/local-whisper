# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.5.0] - 2026-04-18

### Added

- **Parakeet-TDT v3 is the new default transcription engine.** NVIDIA's Parakeet-TDT-0.6B-v3 tops the HuggingFace Open ASR Leaderboard and beats Whisper-large-v3 and every 1.1B Parakeet variant. It runs fully in-process via [parakeet-mlx](https://github.com/senstella/parakeet-mlx), supports English plus 24 European languages, and handles long audio through overlapping 120s chunks. Qwen3-ASR remains available for English-only workflows via `wh engine qwen3_asr`; WhisperKit remains available as a third option.
- **Parakeet settings panel** in Transcription exposing model, chunking (`chunk_duration`, `overlap_duration`), decoding strategy (`greedy` / `beam`), beam tuning (`beam_size`, `length_penalty`, `patience`, `duration_reward`), timeout, and local-attention mode with adjustable context size.
- **`setup.sh`, `wh doctor`, and `wh update` are now engine-aware.** Only the currently-selected transcription engine's model is downloaded and warmed. Fresh installs pull Parakeet-TDT v3 (~600 MB). Switching to Qwen3-ASR later lazy-loads that model on the engine's first call; neither engine holds RAM when the other is active. Warm-up compiles the MLX graph so first inference is fast. It does not pin the model in memory.
- Dedicated warm-up sentinels at `~/.whisper/models/.parakeet_v3_warmed` and `~/.whisper/models/.qwen3_warmed` so re-running setup skips the one-time graph compile.

### Changed

- New installs default to `engine = "parakeet_v3"` in `config.toml`. Existing installs keep their current engine; switch anytime via Settings or `wh engine parakeet_v3`.
- Menu bar engine submenu now lists Parakeet-TDT v3 first, followed by Qwen3-ASR (English) and WhisperKit.
- **Text-to-Speech is opt-in.** Turn it on from the menu bar or Settings -> Voice; the first ⌥T then downloads the Kokoro-82M voice model (~170 MB) and loads the spaCy `en_core_web_sm` dictionary. `setup.sh`, `wh doctor`, and `wh update` skip the Kokoro model and spaCy dictionary while TTS is off and surface them as informational notes instead of failures. Run `./setup.sh` with TTS enabled to pre-fetch everything so the first speak is instant.

## [1.4.1] - 2026-04-18

### Fixed

- **Overlay no longer freezes mid-transcription.** The waveform stacked 28 overlapping animations per RMS sample, which could back up the SwiftUI render pipeline until the pill stopped animating entirely. RMS updates are now throttled to 30 Hz and drive a single animation transaction. The phase transition (recording → processing → done) no longer tears down the view subtree, so in-flight animations and state survive the handover cleanly.
- **Service can no longer stall on a slow overlay.** The IPC sender used `sendall()` with no total-time cap; if the Swift UI was briefly busy, the pipeline thread could block indefinitely on the socket. Writes now use `MSG_DONTWAIT` with a 5-second cap and drop snapshot updates rather than queue them under contention. A stalled consumer drops the connection and reconnects instead of freezing the service.
- **Transcription heartbeat.** Long transcriptions sent exactly one "Transcribing…" state update and then nothing until completion. A 2-second heartbeat now keeps the overlay and service visibly in sync for any recording length.

### Changed

- **Overlay shadow redesign.** The drop shadow is now a crisp capsule-shaped halo that matches the pill exactly and adapts to light/dark mode. Light mode uses a subtle 8% black halo; dark mode uses a stronger 28%. The previous shadow was too heavy on white backgrounds and read as rectangular instead of rounded.

## [1.4.0] - 2026-04-18

### Added

- **Settings auto-fetch**: opening Advanced Settings now probes Ollama and LM Studio immediately for their model lists and shows an Apple Intelligence availability row. No more manual "Fetch Models" tap before the Model picker populates. Per-URL caching prevents network storms on tab switching; changing a Check URL clears the cache and re-probes.
- **Crash-recovery pipeline**: the service writes a marker at `~/.whisper/processing.marker` before heavy work and clears it on completion. On boot the service replays any interrupted transcription in the background and surfaces a `Recovered transcription` notification. A forced restart, panic, or power loss no longer silently drops a recording.
- **Chunked long-session pipeline**: recordings longer than five minutes run through a dedicated pipeline that transcribes, grammar-corrects and persists each VAD segment to `~/.whisper/current_session.jsonl` before the next segment. If the service crashes mid-lecture, whatever chunks completed are committed as a `[Interrupted]`-tagged history entry on the next boot instead of vanishing.
- **Pipeline watchdog**: per-stage timeouts (transcribe 20 min, grammar 90 s, paste 8 s) prevent a single wedged backend from freezing the service. On a transcription timeout the engine is force-reloaded to clear any half-committed MLX/decoder state.
- **LaunchAgent self-healing**: the plist now uses `KeepAlive={SuccessfulExit=false}` with a 10-second `ThrottleInterval` and 30-second `ExitTimeOut`, plus a separate `service.err.log`. Crashes auto-restart; clean stops don't. User-error exits (mic permission denied) exit 0 so launchd does not hot-loop.
- **Sleep/wake resilience**: the Swift app observes `NSWorkspace.didWakeNotification` and sends a `resync_audio` IPC action on wake. The service also runs a 60-second audio-monitor heartbeat so a dead CoreAudio stream from sleep/wake or a mic swap is reaped and rebuilt without user action.
- **Quieter-voice support**: VAD now adds a 210 ms trailing-edge hangover so soft word tails aren't clipped, and normalization adds an adaptive second-stage gain (up to +16 dB total, clip-guarded) for recordings that the primary 10 dB cap can't raise to a usable level.
- **Low-confidence transcription retry**: when Qwen3-ASR returns an empty result on a short clip, the engine retries once with `temperature=0.2`, `top_p=0.95` before returning "No speech" — avoiding the common case where greedy decoding gets stuck on valid audio.
- **Expanded `wh status`**: shows uptime, RSS, and any pending recovery work (interrupted transcriptions, partial long sessions) so users can see why the service just did something at boot.
- **Voice dictation commands**: speak "new line", "new paragraph", "period", "comma", "question mark", "exclamation mark", "colon", "semicolon", "dash", "scratch that", and more, and Local Whisper replaces the phrase with the literal punctuation or whitespace. Runs before grammar correction so the grammar pass sees well-punctuated sentences. Toggle in `~/.whisper/config.toml` under `[dictation]`; add custom commands under `[dictation.commands]`.
- **`wh export`** writes the full transcription history to Markdown, plain text, or JSON in one command. Defaults: `~/Desktop/local-whisper-history.md`. Supports `--format`, `--out`, and `--limit`.
- **`wh stats`** prints local usage statistics: total sessions, total words and characters, average words per session, counts for today/7d/30d, first and last session timestamps, top words (stopwords filtered), and top replacement rules triggered.
- **`wh doctor --report [PATH]`** writes a shareable diagnostic report (macOS version, architecture, Python version, install method, service state, configured engine and backend, installed package versions, last 60 log lines). Safe to paste into a GitHub issue; never includes config contents, recorded audio, or transcription text.
- **`wh replace import <file>`** bulk-imports vocabulary rules from CSV, TSV, TOML-style (`"spoken" = "replacement"`), or arrow-style (`spoken -> replacement`) files. Duplicate keys in the input are surfaced in the summary.

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

- Command socket protocol requests now use the `action` key (`{"action": "listen", ...}`) to match response framing and documentation. Both the CLI client and the service were updated in lockstep, so a normal `wh update` (which pulls code, upgrades deps, and restarts the service) moves both sides at once. Direct socket clients that used the previous `type` key must be updated.
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

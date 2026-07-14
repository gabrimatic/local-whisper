# Changelog

This changelog tracks notable Local Whisper changes.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.8.0] - 2026-07-14

### Added

- Added Apple SpeechTranscriber as a first-class on-device transcription engine on supported macOS 26 and iOS 26 hardware, using Apple's final-transcription preset and an explicit locale for highest-quality completed recordings.
- Added a shared native Swift speech core plus a bundled macOS helper, so the Python service can use SpeechAnalyzer without a cloud service or a second model server while preserving lazy loading.
- Added real Apple language-asset management through `AssetInventory`: Settings and model management report support, availability, download progress, installation state, and Local Whisper's reservation release instead of inferring readiness from files.
- Added Apple Speech settings and status across the CLI, config, IPC, macOS app, Flutter model library, and native iOS bridge, with locale-aware model preparation and clear unsupported-device guidance.
- Added native Swift unit coverage, Python engine/config/switching/IPC tests, Flutter model tests, and an iOS integration path for Apple SpeechTranscriber capability and transcription behavior.

### Changed

- Engine switching now prepares the selected Apple locale before unloading the current transcription engine and preserves the exact installation error when preparation fails.
- iOS refreshes Apple speech asset state when the selected locale changes; Android hides the Apple-only engine while retaining the existing on-device sherpa-onnx path.
- Updated product, architecture, privacy, configuration, testing, CLI, mobile, and troubleshooting documentation for Apple's managed on-device speech assets and supported-platform boundaries.

## [1.7.0] - 2026-07-14

### Added

- Rebindable shortcuts: the proofread, rewrite, prompt-engineer, and read-aloud shortcuts are now editable in Settings → Shortcuts through a click-and-press recorder (and via `wh config`), with live validation, conflict detection that names the clashing action, reset-to-default, and the option to disable an action entirely. Keys accept ctrl/alt/shift/cmd plus a-z, 0-9, f1-f12, or common punctuation, and changes rebind the running service with no restart.
- Paste transform results in place: proofread, rewrite, and prompt-engineer results now replace the selected text where it sits by default and are still copied to the clipboard as a backup (`[shortcuts] paste_result`); set it to false for copy-only.
- Hold-to-record threshold (`[hotkey] hold_threshold`): a separate knob, with a slider in Settings → Recording, for how long the trigger must be held before hold-to-record engages; 0 keeps the historic behavior of following the double-tap window.
- Editable dictation commands: the Voice panel gained a full editor to add, override, or remove spoken commands (previously a read-only list), showing the real merged command set; commands are also managed from the CLI.
- `[dictation] strip_fillers` toggle: turn off English filler removal ("um", "uh", "ah", "er") when dictating in languages where those are real words, such as German.
- Live testers in Settings: "Try it out" boxes in the Vocabulary and Voice panels run your sample text through the real replacement and dictation engines in the service and show input to output, including which rule fired or that none matched.
- Inline dictionary editing: edit an existing replacement rule in place, and set an empty replacement to delete a word from transcripts entirely (with the surrounding spacing and punctuation tidied up).
- `wh replace export <file>` and `wh replace test "..."`: export your dictionary to round-trippable CSV, and dry-run a sentence to see exactly what the current rules would produce.

### Changed

- Settings now apply immediately instead of prompting for a restart: the trigger key, transform shortcuts, read-aloud shortcut, and replacement/dictation edits (from the app, `wh config`, or `wh replace`) all hot-reload the running service, and engine and grammar-backend switches happen in place and roll back to the previous working state if the new one fails to start.
- Rewrote the vocabulary replacement engine: all-lowercase replacements now mirror the matched casing ("gonna" to "Going to", "GONNA" to "GOING TO") while replacements containing any uppercase stay literal, longer phrases win over shorter overlapping ones, rules anchor on word edges so terms like "c++", ".net", and "e.g." match, and extra spaces between words are tolerated.
- The completion status now reports what actually happened — "Replaced!" or "Pasted!" with a character delta — instead of always saying "Copied!".
- Your clipboard is saved and restored as a full snapshot across all types, so images, files, and rich text survive a transform or read-aloud instead of being replaced with plain text.
- Esc during read-aloud is only intercepted while audio is actually playing; during the potentially long preparation phase it now goes to your frontmost app.
- Shortcut hints throughout the app (menu bar, onboarding, and the cheatsheet) now show your actual configured combos and hide any action you have turned off, instead of hardcoded defaults.
- Bulk dictionary import is now a single atomic write with a stronger CSV/TSV parser (Excel BOM and CRLF handling, quoted fields, format detected once from the first line) and reports how many rules were added versus updated.
- Config edits made while the service is down or restarting now queue and replay on reconnect instead of silently vanishing, and slider drags commit once on release rather than rewriting config.toml dozens of times per second.

### Fixed

- A corrupt `config.toml` no longer wipes your settings: on a parse error the file is backed up to `config.toml.broken-<timestamp>`, the service runs on defaults, and writes are refused until it parses again so a later save cannot overwrite your real file. Replacement values containing newlines, tabs, or control characters are now escaped instead of corrupting the file on the next read.
- Concurrent config edits no longer clobber each other — writes merge under a lock against the current file rather than a stale in-memory snapshot — and a refused write now rolls back the in-memory value and re-syncs the UI instead of leaving a phantom edit on screen.
- Text transforms no longer damage the surrounding text: a double-clicked word's trailing space, a triple-clicked paragraph's newline, and leading indentation are preserved, and long proofread jobs keep bullet lists and line breaks instead of collapsing them.
- The grammar cleaner no longer deletes your own words when a sentence legitimately begins like "Sure, ..." or "Result: ...", or when the input was itself quoted or fenced.
- Fixed nothing-selected transforms and read-aloud acting on stale clipboard contents, and the trigger combo (for example Opt+T) typing a stray character like "†" into your document when pressed while the app was busy.
- A transform shortcut such as Ctrl+Shift+G no longer also fires when extra modifiers are held (Ctrl+Shift+Cmd+G), so it stops colliding with other apps' shortcuts, and two actions can now share a key with different modifiers.
- Fixed dictation commands corrupting one another: one command's output is no longer re-matched by another (a macro containing the word "period" stays literal), paired open/close quote commands produce "hi" rather than " hi ", "scratch that" also removes a just-dictated terminator, a newline from "new paragraph" survives the following punctuation command, and a custom "Period" override now replaces the built-in "period" instead of losing to it.
- A grammar backend started after Local Whisper (for example launching Ollama later) no longer stays dead for the whole session — it reconnects on its own and the transform shortcuts light up when it appears.
- Fixed the dictation hotkey going permanently silent: a watchdog restarts the key listener if it dies, and an error in a key callback no longer kills it for good.
- The Ollama and LM Studio model probes no longer silently overwrite your configured model when it is missing from the server; they keep your choice, list it first, and warn you to pull it.
- A wedged local model can no longer permanently disable every shortcut and TTS: transform calls run under a length-scaled timeout, and oversize selections are rejected (over 30,000 characters for transforms, 20,000 for read-aloud) so an accidental Select-All cannot pin the model for minutes.
- Fixed a function-key or other non-modifier recording trigger typing its own keystroke into the app you were dictating into; the trigger key is now suppressed while configured, and `wh config` now lists function keys as trigger options.

## [1.6.15] - 2026-07-06

### Fixed

- Fixed macOS asking for Accessibility/Microphone again after every Homebrew Python upgrade: the service now runs through a frozen interpreter copy (`.venv/bin/local-whisper`) with a stable TCC identity, permission dialogs show "local-whisper" instead of "python3.x", and `wh doctor` reports whether the runtime identity is stable.
- Fixed changing the Parakeet model from Settings only taking effect after a service restart: the `[parakeet_v3]` config section now syncs the in-memory config, and a failed engine switch no longer writes the literal string "None" into `config.toml` during rollback.
- Fixed `wh stop`/restart hanging forever when a transcription or grammar call wedged past its watchdog timeout: abandoned watchdog workers no longer block process exit.
- Fixed hotkey suppression, shortcuts, and TTS going silently dead until restart when macOS disables the keyboard event tap under load: the tap now re-enables itself.
- Fixed `config.toml` corruption on crash mid-write: all config rewrites now land atomically via a temp file and rename.
- Fixed a race where cancelling with Esc at the moment a hold-recording was released could still send the discarded audio through transcription.

## [1.6.14] - 2026-06-16

### Fixed

- Fixed Dependabot handling for Pydantic by letting `pydantic` declare its exact `pydantic-core` ABI dependency instead of tracking incompatible standalone core bumps.

## [1.6.13] - 2026-06-16

### Added

- Added WhisperKit large-v3 `large-v3-v20240930_626MB` as the best-accuracy desktop and mobile WhisperKit preset.
- Added managed WhisperKit CLI discovery and doctor repair so `wh doctor --fix` can install the local WhisperKit runtime dependency.

### Changed

- Updated dependencies across Python, Flutter, iOS, and Android, including Pydantic 2.13.4, Parakeet MLX 0.5.2, PyObjC 12.2, SoundFile 0.14.0, Apple Foundation Models SDK 0.2.0, Sherpa ONNX 1.13.3, Android Gradle Plugin 8.13.2, and Kotlin 2.4.0.
- Updated Flutter model validation so stale WhisperKit snapshot folders are rejected and redownloaded instead of being treated as installed.

### Fixed

- Fixed post-sleep and stale microphone recovery by resetting the audio host on wake resync and closing a warmup event race that could miss the first live input signal.
- Fixed source/Homebrew LaunchAgent conflicts that could make macOS ask for permissions on multiple Python runtime identities.
- Fixed engine switching so managed model downloads and active model edits roll back instead of leaving `config.toml` pointing at a failed engine or model.
- Fixed `wh engine` so it waits for the restarted service to become ready and rolls back if the new engine cannot start.
- Fixed `wh transcribe` with WhisperKit by normalizing CLI string paths before engine invocation.
- Fixed WhisperKit runtime startup to use installed local CLI paths without adding `mlx-audio` or cloud transcription fallbacks.

## [1.6.12] - 2026-05-29

### Added

- Added a deterministic speech-filler filter for live dictation and `wh listen`, removing high-confidence fillers such as "um", "uh", "ah", "er", and pause-like "oh" before grammar correction.

### Fixed

- Kept meaningful phrases such as "uh oh" and "oh no" intact while filtering fillers.
- Made Retry Last run through the same dictation cleanup pass as normal recordings while preserving the original raw transcript in history.

## [1.6.11] - 2026-05-29

### Added

- Added inline Settings download progress and cancellation for managed MLX models and Kokoro preload without opening the dictation overlay.
- Added Settings and onboarding actions that request Microphone and Accessibility permissions directly, with System Settings fallback when macOS cannot show the prompt again.

### Fixed

- Fixed model cache truth in Settings so partial Hugging Face snapshots are shown as partial/resumable instead of downloaded.
- Fixed Settings model switching so failed or canceled downloads keep the current working engine loaded.
- Fixed stale macOS input recovery by adding retry backoff and a CoreAudio device-list refresh after PortAudio reset.
- Fixed microphone permission checks by shipping AVFoundation support instead of treating a missing permission framework as success.
- Fixed all-zero microphone failures to name the current input device, including virtual inputs such as BlackHole, instead of surfacing a generic model or mic error.
- Improved Settings light-mode contrast and removed selected-looking styling from external About links.

## [1.6.10] - 2026-05-27

### Fixed

- Kept idle-unloaded models from making the service report unhealthy, so setup, update, restart, and status readiness checks no longer wait on a resident model.
- Bounded model preparation checks during setup/update so a stuck local model check fails or skips instead of hanging indefinitely.
- Return a clear reload error if an on-demand model reload fails before transcription starts.

## [1.6.9] - 2026-05-26

### Fixed

- Fixed hold-to-record output so releasing the trigger key preserves hold mode and pastes the transcription at the active cursor.

## [1.6.8] - 2026-05-26

### Added

- Added hold-to-record paste output: holding the trigger key records until release and pastes the transcription at the active cursor, while double-tap recordings keep the normal clipboard output unless auto-paste is enabled.

## [1.6.7] - 2026-05-17

### Fixed

- Kept Homebrew self-updates from deleting the running Cellar before the updater finishes, then prepared models through the newly linked `wh` binary.
- Fixed Homebrew service PID detection for `/opt/homebrew/opt/local-whisper/bin/wh _run` launch paths so `wh status` and duplicate cleanup see the real process.

## [1.6.6] - 2026-05-17

### Fixed

- Made the menu bar update action use the same Homebrew/source-aware path as `wh update`, including model preparation, Swift UI rebuilds when needed, service restart, and a service-ready check before reporting success.
- Kept the recording overlay visible during live recording updates by repairing the panel when repeated `state_update` snapshots arrive, not only when the phase changes.
- Enforced one Local Whisper service per macOS user with a global per-user lock that is independent of `HOME`, and cleaned up legacy duplicate `wh _run` processes from older HOME-scoped lock paths.
- Added clearer top-level service control docs for `wh status`, `wh start`, `wh stop`, `wh restart`, `wh log`, `wh doctor`, and `wh update`.

## [1.6.5] - 2026-05-16

### Added

- Added a one-command installer (`install.sh`) that installs the Homebrew formula and runs guided first-time setup from Terminal.
- Added `wh setup` as the first-time setup command for Homebrew installs, covering config creation, model preparation, macOS permissions, and service startup.
- Added a dedicated installation guide with recommended, manual Homebrew, source, update, permission, and uninstall paths.

### Changed

- Made the README and `setup.sh` setup copy calmer and more direct while keeping the local model, privacy, and permission details explicit.

## [1.6.4] - 2026-05-12

### Changed

- Updated the Qwen3-ASR and Kokoro MLX package requirements to the current published releases.
- Let Qwen3-ASR use model-side language detection instead of forcing English.

## [1.6.3] - 2026-05-12

### Fixed

- Reset stale macOS input streams when the first recording after sleep, wake, or a long idle period opens with a PortAudio/CoreAudio error or returns all-zero audio, so hotkey recording and `wh listen` recover the microphone before surfacing a failed transcription.

## [1.6.2] - 2026-05-12

### Added

- Added mobile history ownership controls: export local transcript history as Markdown to the clipboard, delete individual transcripts, clear all history with confirmation, and see saved entry, audio-duration, and storage estimates in the History tab.

### Changed

- Aligned public docs, setup/onboarding copy, issue templates, and mobile guides with the project voice: local-first, concrete about runtime boundaries, and specific about the macOS, iOS, and Android surfaces.

### Fixed

- Brought the Android keyboard closer to the iOS keyboard surface: the app's Keyboard quick insert toggle now controls Android mode and punctuation shortcuts, and the Android keyboard includes Clean, Message, Notes, Prompt, punctuation, Space, New line, and Delete actions.
- Made mobile model-pack installs more resilient: Hugging Face snapshot manifests and model files now retry transient network, 408, 429, and 5xx failures before surfacing an install error, and downloaded files are still verified against the local manifest before a pack is marked ready.
- Added Flutter mobile analyze and widget-test coverage to CI, plus Dependabot coverage for the Flutter `pubspec.yaml`, so the iOS/Android surface is protected alongside Python and Swift.
- Made the service lifecycle setting real end-to-end: `[service].idle_unload_minutes` now loads from `config.toml`, appears in `wh config` and macOS Advanced settings, and macOS changes reschedule the running service without restart. The macOS app also now receives and exposes the English engine's `max_tokens`, and `wh config show` uses the current engine and speech defaults.
- Kept Apple Intelligence requirement handling consistent across setup, docs, CLI metadata, and the macOS UI: public surfaces now state macOS 26+ with Apple Intelligence enabled, and setup/doctor only install the optional SDK extra on supported systems.
- Tightened privacy wording in the package metadata and macOS onboarding/about panels so setup/model downloads are not implied to be network-free.
- Aligned the generated default TOML and full configuration reference, including service lifecycle settings, dictation commands, and Qwen3-ASR decoding tunables.
- Updated CI to Node 24-ready GitHub Actions and added weekly Dependabot coverage for workflow actions.
- Changed project licensing from MIT to PolyForm Noncommercial 1.0.0, with required notices preserving the Local Whisper name and copyright attribution.
- Pinned `pydantic` and `pydantic-core` together so Kokoro, misaki, and spaCy cannot install an ABI-mismatched core wheel that prevents TTS model loading.

## [1.6.1] - 2026-04-20

### Fixed

- **Fresh installs now get ffmpeg.** Parakeet-TDT (the default transcription engine since 1.5.0) shells out to `ffmpeg` for audio decoding, but `setup.sh` only installed `espeak-ng`. A clean machine would hit a cryptic "ffmpeg not installed" error on the first transcription. `setup.sh`, the Homebrew formula, and `wh doctor --fix` now install ffmpeg alongside espeak-ng.
- **Overlay pill is now visible over fullscreen apps.** The pill's window level was too low for an accessory app, so fullscreen windows sometimes occluded it; switching spaces was the only way to see the recording state. The overlay now sits at the screen-saver level while still keeping the menu bar accessible.
- **Overlay no longer drifts to the left edge on certain displays.** Positioning now picks the screen under the cursor (falling back to the main screen, then the first screen) and skips the move entirely if the chosen display reports a degenerate frame during sleep/wake or hot-plug. The one-off "pill jumped to the left side" glitch traced to `NSScreen.main` returning a secondary display on the logical left of the primary.

## [1.6.0] - 2026-04-20

### Added

- **Inline download progress bars.** Switching to an un-downloaded engine or turning on Text-to-Speech now shows a real progress bar with megabytes, total, and percent under the triggering section, driven by a byte count polled from the HF cache directory. No modal dialogs and no overlay takeover; the bar lives inside the card that started the download.
- **Merged "Speech-to-text model" panel.** Transcription settings now show one card per engine that acts as both the picker and the status readout. Active card is accent-tinted with an "In use" marker; inactive cards offer Use, Use & download, or trash in place. The previous separate engine picker has been retired. Per-engine tuning knobs render below the active card.
- **Eager Kokoro preload.** Flipping Text-to-Speech on immediately downloads the Kokoro voice model with visible progress instead of deferring to the first ⌥T press. First speak after enabling is instant.

### Fixed

- **Engine switching now works even when a model is not yet on disk.** The LaunchAgent plist no longer hard-pins `HF_HUB_OFFLINE=1`, and the running service clears any stale value on startup, so switching to a fresh engine mid-session downloads its weights. Previous versions failed with a generic "Switch failed" on the first attempt.
- **Text-to-Speech toggle no longer only flips the config.** Turning TTS off from the menu bar or Settings tears down the processor and unbinds ⌥T; turning it on now spins them up without a service restart. Toggle state in the UI matches reality.
- **Clearer error messages** when a download fails: offline / network failures surface as "needs internet" or "network error" instead of raw exception text.

## [1.5.0] - 2026-04-18

### Added

- **Parakeet-TDT v3 is the new default transcription engine.** NVIDIA's Parakeet-TDT-0.6B-v3 ships as the default because it is accurate, multilingual, and practical on Apple Silicon. It runs in-process via [parakeet-mlx](https://github.com/senstella/parakeet-mlx), supports English plus 24 European languages, and handles long audio through overlapping 120s chunks. Qwen3-ASR remains available for English-only workflows via `wh engine qwen3_asr`; WhisperKit remains available as a third option.
- **Parakeet settings panel** in Transcription shows model, chunking (`chunk_duration`, `overlap_duration`), decoding strategy (`greedy` / `beam`), beam tuning (`beam_size`, `length_penalty`, `patience`, `duration_reward`), timeout, and local-attention mode with adjustable context size.
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
- **LaunchAgent self-healing**: the plist now uses `KeepAlive={SuccessfulExit=false}` with a 10-second `ThrottleInterval` and 30-second `ExitTimeOut`, plus a separate `service.err.log`. Crashes auto-restart; clean stops don't. Expected permission exits (mic permission denied) exit 0 so launchd does not hot-loop.
- **Sleep/wake resilience**: the Swift app observes `NSWorkspace.didWakeNotification` and sends a `resync_audio` IPC action on wake. The service also runs a 60-second audio-monitor heartbeat so a dead CoreAudio stream from sleep/wake or a mic swap is reaped and rebuilt without manual action.
- **Quieter-voice support**: VAD now adds a 210 ms trailing-edge hangover so soft word tails aren't clipped, and normalization adds an adaptive second-stage gain (up to +16 dB total, clip-guarded) for recordings that the primary 10 dB cap can't raise to a usable level.
- **Low-confidence transcription retry**: when Qwen3-ASR returns an empty result on a short clip, the engine retries once with `temperature=0.2`, `top_p=0.95` before returning "No speech"; this avoids the common case where greedy decoding gets stuck on valid audio.
- **Expanded `wh status`**: shows uptime, RSS, and any pending recovery work (interrupted transcriptions, partial long sessions) so you can see why the service did something at boot.
- **Voice dictation commands**: speak "new line", "new paragraph", "period", "comma", "question mark", "exclamation mark", "colon", "semicolon", "dash", "scratch that", and more, and Local Whisper replaces the phrase with the literal punctuation or whitespace. Runs before grammar correction so the grammar pass sees well-punctuated sentences. Toggle in `~/.whisper/config.toml` under `[dictation]`; add custom commands under `[dictation.commands]`.
- **`wh export`** writes the full transcription history to Markdown, plain text, or JSON in one command. Defaults: `~/Desktop/local-whisper-history.md`. Supports `--format`, `--out`, and `--limit`.
- **`wh stats`** prints local usage statistics: total sessions, total words and characters, average words per session, counts for today/7d/30d, first and last session timestamps, top words (stopwords filtered), and top replacement rules triggered.
- **`wh doctor --report [PATH]`** writes a shareable diagnostic report (macOS version, architecture, Python version, install method, service state, configured engine and backend, installed package versions, last 60 log lines). Safe to paste into a GitHub issue; never includes config contents, recorded audio, or transcription text.
- **`wh replace import <file>`** bulk-imports vocabulary rules from CSV, TSV, TOML-style (`"spoken" = "replacement"`), or arrow-style (`spoken -> replacement`) files. Duplicate keys in the input are surfaced in the summary.

### Fixed

- Toggling "Enable grammar correction" in Settings now loads or unloads the backend in-process instead of only writing the flag to config and leaving the model dangling.
- `⌥T` text-to-speech no longer clobbers the clipboard when it falls back to Cmd+C for text selection. The prior clipboard contents are saved and restored.
- Dead icon constants (`ICON_*`, `OVERLAY_WAVE_FRAMES`, `ANIM_INTERVAL_*`) and the dead `hide_dock_icon()` helper in `utils.py` removed. Asset imports no longer hard-crash the entire CLI if a single bundled PNG is missing.
- WhisperKit engine no longer accumulates `atexit` handlers across engine switches, and now fails fast if the server subprocess dies during startup instead of polling a dead PID for five minutes.
- Kokoro TTS model load is serialized through a dedicated lock so two callers cannot both pay the download cost in parallel on first use.
- Transcription engine and grammar backend validation in the config loader now derives valid values from the live registries. Registering a new engine or backend works with a single registry edit.
- `wh listen` now re-arms the pre-recording monitor stream when it finishes, so a subsequent hotkey capture still gets the configured pre-buffer.
- `wh update` aborts cleanly when `git pull` or `pip install` fails and prints the exact rollback command (`git reset --hard <sha>`) so the service never restarts against half-applied changes.
- `wh config show` piped into another command now exits non-zero when the config file is missing instead of silently succeeding.
- `wh uninstall` waits up to two seconds for graceful SIGTERM shutdown before escalating to SIGKILL, and surfaces the source-install venv path so you know exactly what remains to clean up.
- `wh doctor --fix` reports a real failure if `launchctl load` returns non-zero instead of printing "loaded" regardless.
- Ollama model list fetch in Advanced settings now uses a 5-second timeout so a stopped Ollama server no longer hangs the button indefinitely.
- About tab no longer force-unwraps credit URLs; a malformed string silently no-ops instead of crashing.
- `DeferredTextField`, `DeferredIntTextField`, and `DeferredTextEditor` now pick up external `config_snapshot` updates when the field is unfocused, so settings no longer appear stale after a backend or engine switch.
- `DeferredIntTextField` resets to the last committed value when you leave a non-parseable value in the field (previously it stayed diverged from the service indefinitely).
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
- Text to Speech: select text in any app and press ⌥T to hear it read aloud. Kokoro-82M synthesizes speech on-device after the model is downloaded.
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
- Qwen3-ASR bf16 model (full precision) as the default transcription model.
- Language auto-detection for Qwen3-ASR.
- Model warm-up during setup so the first transcription starts without delay.
- Ollama model list fetched live in settings (pulls installed models automatically).
- Engine switching with automatic rollback: if the new engine fails to start, the previous engine stays active.
- Clear error message when WhisperKit CLI is not installed.

### Changed

- Default Qwen3-ASR model is the 1.7B-bf16 variant.
- WhisperKit is an optional engine. Install manually with `brew install whisperkit-cli` if needed.
- Text fields in settings save on Enter or focus loss instead of on every keystroke.
- Repetition penalty (1.2) added to Qwen3-ASR to reduce hallucination on short or silent recordings.

---

## [1.0.1] - 2026-02-24

### Added

- Qwen3-ASR is now the default transcription engine, running fully in-process with no server. It handles recordings up to 20 minutes natively.
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
- Settings window reorganized from 6 tabs to 3 (General, Advanced, About). Everyday options in General, advanced tuning in Advanced.
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

- Microphone permission check with clear error on startup
- Silent audio detection to skip empty recordings

### 2026-01-30

- Global keyboard shortcuts for text transformation (Ctrl+Shift+G for proofread, Ctrl+Shift+R for rewrite, Ctrl+Shift+P for prompt engineer)
- CGEventTap-based keyboard interception with proper event suppression
- Extensible modes system for text transformations
- Accessibility-first text retrieval with clipboard fallback
- Consolidated prompt files into `modes.py`

### 2026-01-28

- Enhanced session management with error handling and retry logic

### 2026-01-22 to 2026-01-24

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

# Contributing

Bug fixes, new grammar backends, new engines, better docs. Here's how to get involved.

## Dev Setup

```bash
git clone https://github.com/gabrimatic/local-whisper.git
cd local-whisper
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
wh build   # builds the Swift UI app
```

Run the service for development:

```bash
wh start
wh log     # tail live output in another terminal
```

You need Accessibility permission for the `wh` process (System Settings opens on first run) and Microphone access.

## Architecture

Python runs as a headless LaunchAgent service. Swift owns all UI (menu bar, overlay, settings). They communicate over a Unix socket with newline-delimited JSON.

```
src/whisper_voice/
├── app.py              # Headless service, state machine, IPC, hotkeys
├── cli.py              # wh CLI controller
├── ipc_server.py       # IPC server (Swift UI communication)
├── cmd_server.py       # Command server (CLI commands)
├── audio.py            # Recording and pre-buffer
├── audio_processor.py  # VAD, noise reduction, normalization
├── backup.py           # History persistence
├── config.py           # Config management
├── grammar.py          # Grammar backend factory
├── transcriber.py      # Engine routing
├── utils.py            # Helpers
├── shortcuts.py        # Text transformation shortcuts
├── key_interceptor.py  # CGEvent tap
├── tts_processor.py    # TTS shortcut handler (⌥T)
├── tts/
│   ├── base.py         # TTSProvider base
│   └── kokoro_tts.py   # Kokoro provider (MLX)
├── engines/
│   ├── base.py         # TranscriptionEngine base
│   ├── qwen3_asr.py    # Qwen3-ASR (default, MLX)
│   └── whisperkit.py   # WhisperKit (alternative)
└── backends/
    ├── base.py         # Backend base
    ├── modes.py        # Transformation modes
    ├── ollama/
    ├── lm_studio/
    └── apple_intelligence/
```

```
LocalWhisperUI/Sources/LocalWhisperUI/
├── AppMain.swift               # Menu bar + settings scenes
├── AppState.swift              # Observable state, IPC message handling
├── IPCClient.swift             # Unix socket connection
├── IPCMessages.swift           # Codable message types
├── MenuBarView.swift           # Menu bar dropdown
├── OverlayWindowController.swift  # Floating overlay panel
├── OverlayView.swift           # Recording/processing/speaking pill
├── GeneralSettingsView.swift   # Engine, grammar, TTS, UI toggles
├── AdvancedSettingsView.swift   # Audio, engine params, shortcuts
├── AboutView.swift             # Version and credits
├── SettingsView.swift          # Tab container
├── SharedViews.swift           # Reusable components
└── Constants.swift             # App-wide constants
```

Key constraint: **lazy loading**. Backends, engines, and models initialize only when selected. Non-selected components stay completely uninitialized. If your change touches initialization paths, verify startup memory footprint hasn't increased.

## New Grammar Backend

1. Create a folder under `src/whisper_voice/backends/<name>/` with `__init__.py` and `backend.py`.
2. Implement the `GrammarBackend` abstract class from `backends/base.py`.
3. Add an entry to `BACKEND_REGISTRY` in `backends/__init__.py`.
4. Done. The Grammar submenu, CLI, and Settings window all generate from the registry automatically.

See `backends/ollama/` for a minimal reference implementation.

## New Transcription Engine

1. Create a file under `src/whisper_voice/engines/` implementing `TranscriptionEngine` from `engines/base.py`.
2. Add an entry to `ENGINE_REGISTRY` in `engines/__init__.py`.
3. Done. The Engine submenu, CLI, and Settings window all generate from the registry automatically.

See `engines/whisperkit.py` for a reference implementation.

## New TTS Provider

1. Create a file under `src/whisper_voice/tts/` implementing `TTSProvider` from `tts/base.py`.
2. Add an entry to `TTS_REGISTRY` in `tts/__init__.py`.
3. Done. The TTS voice picker and CLI generate from the registry automatically.

See `tts/kokoro_tts.py` for the reference implementation.

## Testing

```bash
python tests/test_flow.py   # end-to-end (requires a grammar backend)
```

Manual verification flow:

1. Run `wh` and select a grammar backend from Settings
2. Double-tap Right Option to record
3. Speak a sentence with filler words ("um", "like", etc.)
4. Single-tap to stop
5. Verify the clipboard contains cleaned text
6. Check overlay showed the correct status transitions (recording, processing, copied)

If your change affects keyboard shortcuts, also test Ctrl+Shift+G/R/P on selected text.

If your change affects TTS, also test ⌥T on selected text.

## PR Checklist

- One feature or fix per PR. Keep scope tight.
- Test end-to-end before opening.
- Update `README.md` if user-facing behavior changes.
- No breaking config changes without migration notes in the PR description.
- Match existing code style. No reformatting unrelated files.
- Preserve lazy loading. Eager backend/model initialization gets flagged in review.
- Tested TTS if applicable (⌥T on selected text).

## Reporting Issues

Use the [bug report template](https://github.com/gabrimatic/local-whisper/issues/new?template=bug_report.yml). Include:

- Output of `wh version` and `wh status`
- macOS version and chip (e.g., macOS 26.0, M4)
- Which grammar backend you're using
- Steps to reproduce, expected vs. actual behavior
- Relevant lines from `wh log` if the issue involves processing or crashes

## Vulnerability Reporting

See [SECURITY.md](SECURITY.md). Do **not** open public issues for security vulnerabilities. Use GitHub's private vulnerability reporting.

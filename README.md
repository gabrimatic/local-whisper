# Local Whisper

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)]()
[![Apple Silicon](https://img.shields.io/badge/Apple_Silicon-required-blue.svg)]()
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)]()

**On-device voice transcription, grammar correction, and text-to-speech for macOS. Private, fast, runs on MLX.**

Double-tap, speak, tap to stop. Text is ready. Multiple engines, pluggable grammar, TTS with 14 voices. All MLX-native on Apple Silicon. Nothing leaves your Mac.

<p align="center">
  <img src="assets/hero.png" width="600" alt="Local Whisper recording in Notes">
</p>

---

## Quick Start

**Apple Silicon required.** Microphone and Accessibility permissions needed.

```bash
git clone https://github.com/gabrimatic/local-whisper.git
cd local-whisper
./setup.sh
```

One command. Installs deps, downloads models, builds the UI, sets up auto-start, creates the `wh` alias.

| Action | Key |
|--------|-----|
| Start recording | Double-tap **Right Option** |
| Hold to record | Hold **Right Option** past double-tap threshold |
| Stop and transcribe | Tap **Right Option** or **Space** |
| Cancel | **Esc** |
| Read selected text aloud | **⌥T** |
| Stop speech | **⌥T** again or **Esc** |

---

## What It Does

- **On-device transcription** via MLX. Multiple engines, up to 20 minutes per recording.
- **Grammar correction** with pluggable backends: Apple Intelligence, Ollama, LM Studio. Or disable it.
- **Text-to-speech** on any selected text. 14 on-device voice presets via Kokoro MLX.
- **Text replacements** for custom spoken-to-correct mappings.
- **Audio processing**: VAD, silence trimming, noise reduction, normalization.
- **Keyboard shortcuts** for proofreading, rewriting, prompt engineering on selected text.
- **CLI**: `wh whisper`, `wh listen`, `wh transcribe` for scripting and automation.
- **Native macOS UI**: menu bar, Liquid Glass overlay, settings window.
- **Auto-backup** of every recording and transcription.

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **⌥T** | Read selected text aloud (again or Esc to stop) |
| **Ctrl+Shift+G** | Proofread selected text |
| **Ctrl+Shift+R** | Rewrite selected text |
| **Ctrl+Shift+P** | Optimize selected text as an LLM prompt |

Results go to clipboard. TTS plays through speakers.

### Feedback

- **Sounds**: Pop on start, Glass on success, Basso on failure
- **Menu bar**: animated waveform (recording), speaker icon (speech)
- **Overlay**: `0.0` recording · `···` processing · `Copied` done · `Failed` error · `Speaking...`

<p align="center">
  <img src="assets/overlay-recording.png" width="280" alt="Floating overlay during recording">
</p>

---

## Transcription Engines

Switch via Settings, `wh engine <name>`, or config.

### Qwen3-ASR (default)

In-process MLX. No server, no network. Long audio native.

| Setting | Default | Notes |
|---------|---------|-------|
| `model` | `mlx-community/Qwen3-ASR-1.7B-bf16` | Downloaded by `setup.sh` |
| `language` | `auto` | Force with `en`, `fa`, etc. |
| `timeout` | `0` | No limit |
| `prefill_step_size` | `4096` | Higher = faster on Apple Silicon |

### WhisperKit (alternative)

Whisper on Apple Neural Engine via [Argmax](https://github.com/argmaxinc/WhisperKit). Install with `brew install whisperkit-cli`, switch with `wh engine whisperkit`.

| Model | Notes |
|-------|-------|
| `tiny` / `tiny.en` | Fastest, lowest accuracy |
| `base` / `base.en` | |
| `small` / `small.en` | |
| `whisper-large-v3-v20240930` | Best accuracy (default) |

---

## Grammar Backends

Optional. Pick a grammar backend or disable it:

| Backend | Requirements | Notes |
|---------|-------------|-------|
| **Apple Intelligence** | macOS 15+, Apple Silicon, Apple Intelligence enabled | Fastest, best quality |
| **Ollama** | [Ollama](https://ollama.com) installed and running | Works on any Mac |
| **LM Studio** | [LM Studio](https://lmstudio.ai) with a model loaded and the local server started | Works on any Mac |
| **Disabled** | None | Transcription only |

Switch from menu bar (instant), `wh backend <name>` (restarts), or Settings.

<details>
<summary><strong>Ollama setup</strong></summary>

1. Download from [ollama.com](https://ollama.com)
2. Pull a model and start the server:

```bash
ollama pull gemma3:4b-it-qat
ollama serve
```

</details>

<details>
<summary><strong>LM Studio setup</strong></summary>

1. Download from [lmstudio.ai](https://lmstudio.ai)
2. Download and load a model (e.g., `google/gemma-3-4b`)
3. **Start the local server**: Developer tab > Start Server

> Loading a model does **not** start the server. Start it from Developer tab.

</details>

---

## Usage

### CLI

`wh` controls everything:

```bash
wh                  # Status and help
wh status           # Service status, PID, grammar backend
wh start            # Launch the service
wh stop             # Stop the service
wh restart          # Restart (rebuilds Swift UI if sources changed)
wh build            # Rebuild Swift UI app

wh engine           # Show current engine and list available
wh engine whisperkit  # Switch transcription engine
wh backend          # Show current grammar backend and list available
wh backend ollama   # Switch grammar backend

wh replace          # Show text replacement rules
wh replace add "gonna" "going to"
wh replace remove "gonna"
wh replace on|off   # Enable or disable replacements

wh whisper "text"   # Speak text aloud via Kokoro TTS
wh whisper --voice af_bella "text"
echo "hello" | wh whisper

wh listen           # Record until silence, output transcription
wh listen 30        # Record up to 30 seconds
wh listen --raw     # Raw transcription, no grammar

wh transcribe recording.wav
wh transcribe --raw audio.wav

wh config           # Interactive config editor (static summary when piped)
wh config edit      # Open config.toml in $EDITOR
wh config path      # Print config file path
wh doctor           # Check system health
wh doctor --fix     # Auto-repair issues
wh log              # Tail service log
wh update           # Pull, upgrade deps, warm up models, rebuild, restart
wh version          # Show version
wh uninstall        # Completely remove Local Whisper
```

### Menu Bar

<p align="center">
  <img src="assets/menu-bar.png" width="380" alt="Local Whisper menu bar">
</p>

| Item | What it does |
|------|-------------|
| Status | Current state |
| Grammar | Switch grammar backend in-place |
| Replacements | Toggle, shows rule count |
| Retry Last / Copy Last | Re-transcribe or re-copy |
| Transcriptions | Last 20, click to copy |
| Recordings | Audio files, click to reveal in Finder |
| Settings... | Full GUI |
| Restart Service | Restart background service |
| Check for Updates | Pull, rebuild, restart |
| Quit | Exit |

### Settings

Three tabs: General (engine, grammar, TTS, shortcuts, UI), Advanced (audio, params, backends), About.

<p align="center">
  <img src="assets/settings.png" width="480" alt="Settings window">
</p>

Saves to `~/.whisper/config.toml`. Restart-required fields warn and offer immediate restart.

---

## Configuration

`~/.whisper/config.toml`. Edit via Settings, `wh config`, or directly.

<details>
<summary><strong>Full config reference</strong></summary>

```toml
[hotkey]
key = "alt_r"              # alt_r, alt_l, ctrl_r, ctrl_l, cmd_r, cmd_l,
                           # shift_r, shift_l, caps_lock, f1-f12
double_tap_threshold = 0.4 # seconds

[transcription]
engine = "qwen3_asr"      # "qwen3_asr" (default) or "whisperkit"

[qwen3_asr]
model = "mlx-community/Qwen3-ASR-1.7B-bf16"
language = "auto"          # "en", "fa", etc. or "auto"
timeout = 0                # 0 = no limit
prefill_step_size = 4096   # higher = faster on Apple Silicon
temperature = 0.0
top_p = 1.0
top_k = 0
repetition_context_size = 100
repetition_penalty = 1.2
chunk_duration = 1200.0    # max chunk length in seconds

[whisper]
model = "whisper-large-v3-v20240930"
language = "auto"
url = "http://localhost:50060/v1/audio/transcriptions"
check_url = "http://localhost:50060/"
timeout = 0
temperature = 0.0
compression_ratio_threshold = 2.4
no_speech_threshold = 0.6
logprob_threshold = -1.0
temperature_fallback_count = 5
prompt_preset = "none"     # "none", "technical", "dictation", or "custom"
prompt = ""                # used only when prompt_preset = "custom"

[grammar]
backend = "apple_intelligence"  # "apple_intelligence", "ollama", or "lm_studio"
enabled = false

[ollama]
url = "http://localhost:11434/api/generate"
check_url = "http://localhost:11434/"
model = "gemma3:4b-it-qat"
keep_alive = "60m"
timeout = 0
max_chars = 0
max_predict = 0
num_ctx = 0
unload_on_exit = false

[apple_intelligence]
max_chars = 0
timeout = 0

[lm_studio]
url = "http://localhost:1234/v1/chat/completions"
check_url = "http://localhost:1234/"
model = "google/gemma-3-4b"
max_chars = 0
max_tokens = 0
timeout = 0

[replacements]
enabled = false

[replacements.rules]
# "gonna" = "going to"
# "wanna" = "want to"

[audio]
sample_rate = 16000
min_duration = 0
max_duration = 0           # 0 = no limit
min_rms = 0.005            # silence threshold (0.0-1.0)
vad_enabled = true
noise_reduction = true
normalize_audio = true
pre_buffer = 0.0           # seconds before hotkey (0.0 = disabled)

[backup]
directory = "~/.whisper"
history_limit = 100        # max entries for text and audio history (1-1000)

[ui]
show_overlay = true
overlay_opacity = 0.92
sounds_enabled = true
notifications_enabled = false
auto_paste = false         # paste at cursor, preserving clipboard

[shortcuts]
enabled = true
proofread = "ctrl+shift+g"
rewrite = "ctrl+shift+r"
prompt_engineer = "ctrl+shift+p"

[tts]
enabled = true
provider = "kokoro"
speak_shortcut = "alt+t"

[kokoro_tts]
model = "mlx-community/Kokoro-82M-bf16"
voice = "af_sky"           # American female: af_heart, af_bella, af_nova, af_sky, af_sarah, af_nicole
                           # British female:  bf_alice, bf_emma
                           # American male:   am_adam, am_echo, am_eric, am_liam
                           # British male:    bm_daniel, bm_george
```

</details>

---

## Privacy

Zero network calls. Every component runs on-device or localhost.

| Component | Runs at |
|-----------|---------|
| Qwen3-ASR | In-process MLX |
| Kokoro TTS | In-process MLX |
| WhisperKit | localhost:50060 |
| Apple Intelligence | On-device |
| Ollama | localhost:11434 |
| LM Studio | localhost:1234 |

Models cached at `~/.whisper/models/`. Config and backups at `~/.whisper/`.

---

## Architecture

Python headless service (LaunchAgent). Swift owns all UI.

```
Python (LaunchAgent, headless)
  ├── Recording, transcription, grammar, replacements, clipboard, hotkeys
  ├── Text-to-Speech (Kokoro-82M, in-process)
  ├── IPC server at ~/.whisper/ipc.sock (Swift UI communication)
  └── Command server at ~/.whisper/cmd.sock (CLI commands)

Swift (subprocess, all UI)
  ├── Menu bar with grammar submenus and transcription history
  ├── Floating overlay pill (recording, processing, speaking states)
  └── Settings window (General, Advanced, About)
```

<details>
<summary><strong>Data flow</strong></summary>

```
┌───────────────────────────────────────────────────────────┐
│  Microphone → pre-buffer (ring) + live capture            │
└──────────────────────────┬────────────────────────────────┘
                           ▼
┌───────────────────────────────────────────────────────────┐
│  Audio Processing                                         │
│  VAD → silence trim → noise reduction → normalize         │
└──────────────────────────┬────────────────────────────────┘
                           ▼
┌───────────────────────────────────────────────────────────┐
│  Transcription Engine                                     │
│                                                           │
│  Qwen3-ASR (default)       │  WhisperKit (alternative)   │
│  In-process MLX            │  localhost:50060             │
│  Long audio native         │  Split at 28s gaps          │
└──────────────────────────┬────────────────────────────────┘
                           ▼
┌───────────────────────────────────────────────────────────┐
│  Grammar Correction                                       │
│                                                           │
│  Apple Intelligence  │  Ollama        │  LM Studio        │
│  On-device           │  localhost LLM │  OpenAI-compatible │
└──────────────────────────┬────────────────────────────────┘
                           ▼
┌───────────────────────────────────────────────────────────┐
│  Text Replacements                                        │
│  Case-insensitive, word-boundary-aware regex              │
└──────────────────────────┬────────────────────────────────┘
                           ▼
┌───────────────────────────────────────────────────────────┐
│  Clipboard · Saved to ~/.whisper/                         │
│  (auto_paste: pasted at cursor, clipboard preserved)      │
└───────────────────────────────────────────────────────────┘
```

</details>

---

## Troubleshooting

<details>
<summary><strong>"This process is not trusted"</strong></summary>

Grant Accessibility to the `wh` process, **not** your terminal app. System Settings opens automatically on first run.

If it didn't:
```bash
open x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility
```

Enable `wh`, then `wh restart`.

</details>

<details>
<summary><strong>Double-tap not working</strong></summary>

Tap twice within 0.4s (default). Adjust `double_tap_threshold` in config.

</details>

<details>
<summary><strong>Apple Intelligence not working</strong></summary>

Verify:
1. **macOS 15** (Sequoia) or later
2. **Apple Silicon** (M1/M2/M3/M4)
3. **Apple Intelligence** enabled in System Settings > Apple Intelligence & Siri

</details>

<details>
<summary><strong>Ollama not working</strong></summary>

Verify:
1. Ollama installed: [ollama.com](https://ollama.com)
2. Model pulled: `ollama pull gemma3:4b-it-qat`
3. Server running: `ollama serve`

</details>

<details>
<summary><strong>LM Studio not working</strong></summary>

Verify:
1. LM Studio installed: [lmstudio.ai](https://lmstudio.ai)
2. A model is downloaded and loaded
3. **Local server is running** (most common issue): Developer tab > Start Server
4. Confirm with: `curl http://localhost:1234/v1/models`

Loading a model does **not** start the server.

</details>

<details>
<summary><strong>Slow first transcription</strong></summary>

`setup.sh` pre-downloads and warms models. Skip setup and the first transcription pulls them. After that, loaded from disk.

</details>

<details>
<summary><strong>Empty transcription</strong></summary>

- Speak clearly, close to the microphone
- Check microphone permissions in System Settings
- Confirm the correct input device is selected

</details>

<details>
<summary><strong>Overlay not showing</strong></summary>

Check `show_overlay = true` in `~/.whisper/config.toml`.

</details>

---

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

wh build              # Build Swift UI (one-time)
wh                    # Run the service
python tests/test_flow.py  # Run tests (requires a grammar backend)
```

### Adding an Engine or Grammar Backend

Engines: implement `TranscriptionEngine` in `engines/`, register in `ENGINE_REGISTRY`.
Grammar backends: implement `GrammarBackend` in `backends/`, register in `BACKEND_REGISTRY`.

Menu, CLI, and Settings auto-generate from the registries.

<details>
<summary><strong>Project structure</strong></summary>

```
local-whisper/
├── pyproject.toml
├── setup.sh
├── tests/
│   ├── test_flow.py
│   └── fixtures/
├── LocalWhisperUI/                  # Swift UI app
│   ├── Package.swift
│   └── Sources/LocalWhisperUI/
│       ├── AppMain.swift            # @main entry point
│       ├── AppState.swift           # Observable state, IPC handler
│       ├── IPCClient.swift          # Unix socket client
│       ├── IPCMessages.swift        # Codable message types
│       ├── MenuBarView.swift        # Menu bar dropdown
│       ├── OverlayWindowController.swift
│       ├── OverlayView.swift        # Floating pill overlay
│       ├── GeneralSettingsView.swift
│       ├── AdvancedSettingsView.swift
│       ├── SettingsView.swift
│       ├── SharedViews.swift
│       ├── AboutView.swift
│       └── Constants.swift
└── src/whisper_voice/
    ├── app.py              # Headless service, state machine, IPC
    ├── cli.py              # CLI controller (wh)
    ├── ipc_server.py       # IPC server (Swift UI)
    ├── cmd_server.py       # Command server (CLI)
    ├── audio.py            # Recording and pre-buffer
    ├── audio_processor.py  # VAD, noise reduction, normalization
    ├── backup.py           # History persistence
    ├── config.py           # Config management
    ├── grammar.py          # Grammar backend factory
    ├── transcriber.py      # Engine routing
    ├── utils.py            # Helpers
    ├── shortcuts.py        # Text transformation shortcuts
    ├── key_interceptor.py  # CGEvent tap
    ├── tts_processor.py    # TTS shortcut handler
    ├── tts/
    │   ├── base.py         # TTSProvider base
    │   └── kokoro_tts.py   # Kokoro provider (MLX)
    ├── engines/
    │   ├── base.py         # TranscriptionEngine base
    │   ├── qwen3_asr.py    # Qwen3-ASR (MLX)
    │   └── whisperkit.py   # WhisperKit (localhost)
    └── backends/
        ├── base.py         # Backend base
        ├── modes.py        # Transformation modes
        ├── ollama/
        ├── lm_studio/
        └── apple_intelligence/
```

Data stored in `~/.whisper/`:
```
~/.whisper/
├── config.toml             # Settings
├── ipc.sock                # Python/Swift IPC
├── cmd.sock                # CLI commands
├── LocalWhisperUI.app      # Swift UI (built by setup.sh)
├── last_recording.wav
├── last_raw.txt            # Before grammar
├── last_transcription.txt  # Final text
├── audio_history/
├── history/                # Last 100 transcriptions
└── models/                 # Qwen3-ASR, Kokoro TTS
```

</details>

---

## Credits

[Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) by [Qwen Team](https://qwen.ai) · [Kokoro-82M](https://github.com/remsky/Kokoro-FastAPI) · [WhisperKit](https://github.com/argmaxinc/WhisperKit) by [Argmax](https://www.argmaxinc.com) · [Apple Intelligence](https://www.apple.com/apple-intelligence/) · [Apple FM SDK](https://github.com/apple/python-apple-fm-sdk) · [Ollama](https://ollama.com) · [LM Studio](https://lmstudio.ai) · [SwiftUI](https://developer.apple.com/swiftui/)

<details>
<summary><strong>Legal notices</strong></summary>

### Trademarks

"Whisper" is a trademark of OpenAI. "Apple Intelligence" is a trademark of Apple Inc. "WhisperKit" is a trademark of Argmax, Inc. "Qwen" is a trademark of Alibaba Cloud. "Ollama" and "LM Studio" are trademarks of their respective owners.

This project is not affiliated with, endorsed by, or sponsored by OpenAI, Apple, Argmax, Alibaba Cloud, or any other trademark holder. All trademark names are used solely to describe compatibility with their respective technologies.

### Third-Party Licenses

This project depends on [pynput](https://github.com/moses-palmer/pynput), licensed under LGPL-3.0. When installed via pip (the default), pynput is dynamically linked and fully compatible with this project's MIT license.

All other dependencies use MIT, BSD, or Apache 2.0 licenses. See each package for details.

</details>

## License

MIT License. See [LICENSE](LICENSE) for details.

---

Created by [Soroush Yousefpour](https://gabrimatic.info)

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/gabrimatic)

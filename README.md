# Local Whisper

[![License: PolyForm Noncommercial](https://img.shields.io/badge/license-PolyForm%20Noncommercial-lightgrey.svg)](LICENSE)
[![Platform: macOS | iOS | Android](https://img.shields.io/badge/platform-macOS%20%7C%20iOS%20%7C%20Android-lightgrey.svg)]()
[![Apple Silicon](https://img.shields.io/badge/Apple_Silicon-required-blue.svg)]()
[![Python 3.11-3.12](https://img.shields.io/badge/Python-3.11--3.12-blue.svg)]()
[![Local-first](https://img.shields.io/badge/local--first-on--device-green.svg)]()

Local Whisper is a local-first speech-to-text app and dictation service for macOS, iOS, and Android. You use it where you already type: press a shortcut on macOS, speak, and get cleaned text copied or pasted without sending audio to a hosted speech API.

On mobile, Local Whisper is both the recorder app and the keyboard. Record in the app, keep model packs and history on the device, then use the keyboard to bring modes, punctuation, and Local Whisper actions into other text fields. Large model-pack installs retry transient download failures and verify files before a pack is marked ready.

iOS transcribes locally with WhisperKit/Core ML. Android records local WAV audio and transcribes on-device through `sherpa_onnx`; Parakeet-TDT v3 INT8 ONNX is the default Android pack, and Qwen3-ASR 0.6B INT8 ONNX is the broader multilingual pack. There is no cloud speech fallback.

Download the models once, then run them locally. Built-in runtime paths stay on-device or localhost. Configure LM Studio with a private LAN server only when you want that setup. No hosted speech API. No account. No telemetry. No transcript upload.

Double-tap Right Option from any app to start recording, tap Right Option or Space to stop, and press Esc to cancel.

Use the menu bar for status, engine and grammar switching, history, settings, updates, and service controls. Parakeet-TDT v3 is the default macOS transcription engine.

Full documentation lives at [gabrimatic.github.io/local-whisper](https://gabrimatic.github.io/local-whisper/).

<p align="center">
  <img src="assets/hero.png" width="860" alt="Local Whisper macOS settings with Parakeet-TDT v3 active">
</p>

## Local Runtime

Local Whisper uses the network for setup, model downloads, and updates. After that, audio and transcript processing stays on-device, localhost, or a private LAN server you configure. The product does not include a hosted speech fallback.

| Runtime path | Where it runs |
|--------------|---------------|
| Recording and audio cleanup | On device |
| Parakeet-TDT v3 and Qwen3-ASR transcription | In-process MLX |
| Android Parakeet-TDT v3 and Qwen3-ASR transcription | On-device sherpa-onnx |
| WhisperKit transcription | Localhost |
| Grammar cleanup | Apple Intelligence on-device; Ollama or LM Studio on localhost or private LAN |
| Text-to-speech | In-process Kokoro MLX |
| History and backups | `~/.whisper/` |

## At a Glance

Local Whisper is speech-to-text for the places you already type. Start recording with a global shortcut on macOS, clean the transcript locally, paste into any app, replay history, and use the mobile recorder plus keyboard for the same local workflow on iOS and Android.

| Surface | Runtime scope | Status |
|---------|---------------|--------|
| macOS global dictation | System-wide hotkey recording from any app, local transcription, grammar cleanup, replacements, selected-text shortcuts, Kokoro TTS, clipboard, and auto-paste output. | Ready. Parakeet-TDT v3 is the default engine. |
| macOS menu bar and overlay | Live status, engine and backend switching, history, saved audio, settings, updates, service controls, and recording and processing feedback. | Ready. |
| Flutter iOS app + keyboard | Record and transcribe in the app with WhisperKit/Core ML. Keep model packs and history on the device, then use the native keyboard for modes, punctuation, and text-field workflows. | Native local transcription wired through `AVAudioEngine` plus WhisperKit/Core ML. |
| Flutter Android app + keyboard | Record locally in the app, transcribe on-device with sherpa-onnx model packs, and use the native input method in text fields. The Android app keeps the same local history, modes, setup, and model-pack flow. | Parakeet-TDT v3 INT8 ONNX wired first. Qwen3-ASR 0.6B INT8 ONNX wired as the broader multilingual pack. |

<p align="center">
  <img src="assets/ios-important-screens.png" width="760" alt="Local Whisper iOS record, history, and modes screens">
</p>

## macOS Quick Start

Requirements: **Apple Silicon**, Microphone permission, and Accessibility permission.

Recommended setup:

```bash
curl -fsSL https://gabrimatic.github.io/local-whisper/install.sh | bash
```

Manual Homebrew setup:

```bash
brew install gabrimatic/local-whisper/local-whisper
wh setup
```

The Homebrew path installs Local Whisper, downloads and warms the default Parakeet model, checks macOS permissions, starts the background service, and keeps updates simple.

Source setup for development:

```bash
git clone https://github.com/gabrimatic/local-whisper.git
cd local-whisper
./setup.sh
```

The source setup script installs dependencies, downloads and warms the active transcription model (Parakeet by default), builds the Swift UI, configures auto-start, and creates the `wh` alias. Other engines download when you switch to them. Kokoro downloads when text-to-speech is enabled.

Details: [Installation](https://gabrimatic.github.io/local-whisper/reference/installation/).

| Action | Key |
|--------|-----|
| Start recording | Double-tap **Right Option** |
| Hold to record | Hold **Right Option** past double-tap threshold |
| Stop and transcribe | Tap **Right Option** or **Space** |
| Cancel | **Esc** |
| Read selected text aloud | **⌥T** |
| Stop speech | **⌥T** again or **Esc** |

---

## Features

- **Global dictation hotkey**: start recording from any app without focusing a Local Whisper window. Stop with Right Option or Space; the final text lands on the clipboard or pastes at the cursor.
- **Local transcription** via in-process MLX for Parakeet-TDT v3 and Qwen3-ASR. WhisperKit is available through a local server.
- **Local grammar correction** via Apple Intelligence, Ollama, or LM Studio; optional.
- **Text-to-speech** reads selected text aloud in any app with multiple voices and streaming playback through Kokoro MLX.
- **Text replacements** for spoken-to-corrected mappings.
- **Audio processing**: VAD, silence trimming, noise reduction, normalization.
- **Keyboard shortcuts** for proofreading, rewriting, and prompt engineering on selected text.
- **CLI**: `wh whisper`, `wh listen`, `wh transcribe` for scripting and automation.
- **Native macOS UI**: menu bar status/control, floating overlay, and settings window.
- **Mobile app and keyboards**: iOS and Android include the Flutter app plus native keyboard surfaces. Mobile manages model packs, local history export/delete controls, modes, settings, clipboard output, and setup replay.
- **Mobile local models**: iOS uses WhisperKit/Core ML today. Android uses sherpa-onnx with Parakeet-TDT v3 INT8 ONNX first and Qwen3-ASR 0.6B INT8 ONNX for broader multilingual coverage. These are local model packs, not hosted APIs.
- **No cloud speech fallback**: no hosted speech API, no account, no telemetry, no transcript upload.
- **Automatic backup** for every recording and transcription.

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **⌥T** | Read selected text aloud (again or Esc to stop) |
| **Ctrl+Shift+G** | Proofread selected text |
| **Ctrl+Shift+R** | Rewrite selected text |
| **Ctrl+Shift+P** | Optimize selected text as an LLM prompt |

Results go to clipboard. Text-transform shortcuts require grammar correction to be enabled with a working backend. TTS plays through speakers after Read selected text aloud is enabled.

### Feedback

- **Sounds**: Pop on start, Glass on success, Basso on failure
- **Menu bar**: state icon for idle, recording, processing, done, error, and speaking
- **Overlay**: live duration and waveform while recording, progress/status while processing, copied or pasted result, error text, and speaking state

<p align="center">
  <img src="assets/macos-dictation-overlay.png" width="780" alt="Local Whisper recording overlay while dictating into notes">
</p>

---

## Transcription Engines

Switch via Settings, `wh engine <name>`, or config.

### Parakeet-TDT v3 (default)

In-process via [parakeet-mlx](https://github.com/senstella/parakeet-mlx). No server. Multilingual: English plus 24 European languages. The default checkpoint is NVIDIA Parakeet-TDT 0.6B v3, served through the `mlx-community/parakeet-tdt-0.6b-v3` MLX snapshot. Long audio is handled via overlapping chunks.

| Setting | Default | Notes |
|---------|---------|-------|
| `model` | `mlx-community/parakeet-tdt-0.6b-v3` | Downloaded by `setup.sh` |
| `timeout` | `0` | No limit |
| `chunk_duration` | `120.0` | Seconds per chunk for long audio. `0` disables chunking (pair with local attention). |
| `overlap_duration` | `15.0` | Overlap between consecutive chunks. |
| `decoding` | `"greedy"` | Or `"beam"` for a small quality bump at higher cost. |
| `beam_size` / `length_penalty` / `patience` / `duration_reward` | `5` / `0.013` / `3.5` / `0.67` | Beam-only tuning knobs. |
| `local_attention` | `false` | Reduces peak RAM for unchunked long audio. |

### Qwen3-ASR

In-process via [qwen3-asr-mlx](https://github.com/gabrimatic/qwen3-asr-mlx). No local server. Native long-audio support, up to 20 minutes in a single pass. Qwen3-ASR detects language from the audio. Switch with `wh engine qwen3_asr`.

| Setting | Default | Notes |
|---------|---------|-------|
| `model` | `mlx-community/Qwen3-ASR-1.7B-bf16` | Downloaded by `setup.sh` |
| `timeout` | `0` | No limit |
| `repetition_penalty` | `1.2` | Higher suppresses repetition loops |
| `repetition_context_size` | `100` | Tokens considered for repetition penalty |
| `chunk_duration` | `1200` | Seconds per internal chunk for long audio |
| `max_tokens` | `0` | `0` = auto-scale from duration. Cap for faster short-clip decode. |

### WhisperKit

Whisper on Apple Neural Engine via [Argmax](https://github.com/argmaxinc/WhisperKit). Install with `brew install whisperkit-cli`, switch with `wh engine whisperkit`.

| Model | Notes |
|-------|-------|
| `tiny` / `tiny.en` | Fastest, lowest accuracy |
| `base` / `base.en` | |
| `small` / `small.en` | |
| `whisper-large-v3-v20240930` | Accuracy-focused default |

---

## Text-to-Speech

Kokoro-82M via [kokoro-mlx](https://github.com/gabrimatic/kokoro-mlx). Runs in-process after install. No local server. Streaming playback starts before full synthesis completes.

Toggle from the menu bar or Settings -> Voice. Turning it on downloads the Kokoro voice model (~170 MB) and uses the spaCy `en_core_web_sm` dictionary plus system `espeak-ng`. Run `./setup.sh` while the toggle is on to pre-fetch the assets before the first speak.

Use it from the keyboard or CLI:

- **⌥T** on selected text in any app. Press ⌥T again, Esc, or start a recording to stop.
- **CLI:** `wh whisper "text"`, `wh whisper --voice af_bella "text"`, or pipe stdin with `echo "hello" | wh whisper`.

The overlay shows "Generating speech..." during synthesis, then "Speaking..." during playback. The shortcut is configurable via `tts.speak_shortcut` in config.

### Voices

Multiple presets available. Default is Sky (`af_sky`).

| Voice | ID | Type |
|-------|-----|------|
| Heart | `af_heart` | American female |
| Bella | `af_bella` | American female |
| Nova | `af_nova` | American female |
| Sky | `af_sky` (default) | American female |
| Sarah | `af_sarah` | American female |
| Nicole | `af_nicole` | American female |
| Alice | `bf_alice` | British female |
| Emma | `bf_emma` | British female |
| Adam | `am_adam` | American male |
| Echo | `am_echo` | American male |
| Eric | `am_eric` | American male |
| Liam | `am_liam` | American male |
| Daniel | `bm_daniel` | British male |
| George | `bm_george` | British male |

---

## Grammar Backends

Grammar cleanup is optional. Pick a backend or keep transcription-only mode:

| Backend | Requirements | Notes |
|---------|-------------|-------|
| **Apple Intelligence** | macOS 26+, Apple Silicon, Apple Intelligence enabled | On-device Foundation Models |
| **Ollama** | [Ollama](https://ollama.com) installed and running | Works on any Mac |
| **LM Studio** | [LM Studio](https://lmstudio.ai) with a model loaded and the local server started | Works on any Mac |
| **Disabled** | None | Transcription only |

Switch from the menu bar, Settings, or `wh backend <name>`. The menu bar switch is instant; the CLI switch restarts the service.

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

Note: Loading a model does **not** start the server. Start it from Developer tab.

</details>

---

## Usage

### CLI

`wh` controls the service and local utilities:

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
wh replace import rules.csv   # Bulk-import rules (CSV, TSV, "a"="b", or a -> b)

wh whisper "text"   # Speak text aloud via Kokoro TTS
wh whisper --voice af_bella "text"
echo "hello" | wh whisper

wh listen           # Record until silence, output transcription
wh listen 30        # Record up to 30 seconds
wh listen --raw     # Raw transcription, no grammar

wh transcribe recording.wav
wh transcribe --raw audio.wav

wh stats            # Show usage statistics computed from history
wh export           # Export history to ~/Desktop/local-whisper-history.md
wh export --format json --out ~/Downloads/history.json
wh export --format txt --limit 50

wh config           # Interactive config editor (static summary when piped)
wh config edit      # Open config.toml in $EDITOR
wh config path      # Print config file path
wh doctor           # Check system health
wh doctor --fix     # Auto-repair issues
wh doctor --report  # Write a shareable diagnostic report
wh setup            # Finish first-time setup after Homebrew install
wh log              # Tail service log
wh update           # Pull, upgrade deps, warm up models, rebuild, restart
wh version          # Show version
wh uninstall        # Remove Local Whisper
```

### Dictation Commands

Speak these phrases anywhere in a dictation and Local Whisper replaces them with the literal punctuation or whitespace:

| Spoken | Inserted |
|--------|----------|
| "new line" | newline |
| "new paragraph" | blank line |
| "period" | . |
| "comma" | , |
| "question mark" | ? |
| "exclamation mark" | ! |
| "colon" | : |
| "semicolon" | ; |
| "dash" | ` - ` (space, hyphen, space) |
| "open paren" / "close paren" | ( / ) |
| "scratch that" | deletes the current sentence fragment |

Custom commands go under `[dictation.commands]` in `~/.whisper/config.toml`. The pass runs before grammar correction, so grammar sees well-punctuated sentences.

### Menu Bar Controls

The menu bar does not drive normal dictation. The global hotkey does. Use the menu bar for state and controls:

| Item | What it does |
|------|-------------|
| Status | Current state with active engine and backend subtitle |
| Engine | Switch transcription engine in-place |
| Grammar | Switch grammar backend in-place |
| Replacements | Toggle, shows rule count |
| Retry Last / Copy Last | Re-transcribe or re-copy |
| Transcriptions | Recent entries, click to copy |
| Recordings | Audio files, click to reveal in Finder |
| Settings… | Full sidebar settings window |
| Service | Restart, Check for Updates, Open Service Log |
| Quit Local Whisper | Exit |

### Settings

Sidebar layout with focused panels:

<p align="center">
  <img src="assets/macos-settings-recording.png" width="760" alt="Local Whisper macOS settings">
</p>

| Panel | Covers |
|-------|--------|
| Recording | Trigger key, double-tap window, audio cleanup, duration limits |
| Transcription | Engine picker plus per-engine sampling and decoding parameters |
| Grammar | Master toggle, backend picker, per-backend connection and limits |
| Voice | Text-to-speech voice and shortcut, dictation command help |
| Vocabulary | Searchable replacement editor with import / export |
| Output | Overlay, sounds, notifications, paste-at-cursor, history limit |
| Shortcuts | Proofread / rewrite / prompt-engineer keybindings, full cheatsheet |
| Activity | Sessions, words, 30-day chart, top words, top replacement triggers |
| Advanced | Storage paths, model idle unload, service log, doctor, restart, update |
| About | Version, credits, replay tutorial |

Settings save to `~/.whisper/config.toml`. Restart-required fields warn and offer immediate restart.

---

## Configuration

Settings are stored in `~/.whisper/config.toml`. Edit them from the app, with `wh config`, or directly.

Common fields:

| Section | What to change |
|---------|----------------|
| `[hotkey]` | Trigger key and double-tap timing |
| `[transcription]` | Active engine: `parakeet_v3`, `qwen3_asr`, or `whisperkit` |
| `[grammar]` | Grammar backend and enable/disable state |
| `[audio]` | VAD, noise reduction, normalization, pre-buffer, and duration limits |
| `[service]` | Idle model unload timing for memory versus next-dictation latency |
| `[ui]` | Overlay, sounds, notifications, and auto-paste |
| `[tts]` | Text-to-speech toggle and shortcut |

See [Configuration reference](https://gabrimatic.github.io/local-whisper/reference/configuration/) for the full TOML reference.

---

## Privacy

Audio recording, transcription, replacements, and text-to-speech run on-device or against localhost services. Grammar correction runs on-device, localhost, or a private LAN server when you configure LM Studio that way. Setup, model downloads, `wh update`, and `wh doctor --fix` use the network to install packages, fetch models, or update the checkout.

| Component | Runs at |
|-----------|---------|
| Parakeet-TDT v3 | In-process MLX |
| Qwen3-ASR | In-process MLX |
| Kokoro TTS | In-process MLX |
| WhisperKit | localhost:50060 |
| Apple Intelligence | On-device |
| Ollama | localhost:11434 |
| LM Studio | localhost:1234 by default; private LAN IPs allowed |

Models cache at `~/.whisper/models/`. Config, history, and backups live under `~/.whisper/`.

After models and optional local services are installed, dictation and cleanup do not send audio or transcript text to cloud APIs.

---

## Architecture

Local Whisper splits runtime and UI. Python runs the headless LaunchAgent service; Swift owns the macOS UI.

```
Python (LaunchAgent, headless)
  ├── Recording, transcription, grammar, replacements, clipboard, hotkeys
  ├── Text-to-Speech (Kokoro-82M, in-process)
  ├── IPC server at ~/.whisper/ipc.sock (Swift UI communication)
  ├── Command server at ~/.whisper/cmd.sock (CLI commands)
  ├── Pipeline watchdog (per-stage timeouts, skip-don't-freeze)
  └── Crash recovery (~/.whisper/processing.marker + current_session.jsonl)

Swift (subprocess, all UI)
  ├── Menu bar with grammar submenus and transcription history
  ├── Floating overlay pill (recording, processing, speaking states)
  ├── NSWorkspace sleep/wake observer → resync_audio IPC
  └── Settings window (lists Ollama / LM Studio models when local servers are reachable)
```

The LaunchAgent uses `KeepAlive={SuccessfulExit=false}` with `ThrottleInterval=10`. Real crashes auto-restart; clean stops (`wh stop`, `wh restart`, expected permission exits) do not relaunch.

Recordings longer than five minutes use the chunked pipeline. Each VAD segment is transcribed, grammar-corrected, and persisted to `~/.whisper/current_session.jsonl` before the next chunk runs, so a crash mid-lecture recovers completed chunks on next boot.

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
│  Parakeet-TDT v3 (default) │ Qwen3-ASR  │ WhisperKit     │
│  Multilingual, MLX         │ English, MLX│ localhost:50060│
│  120s chunked              │ Long audio  │ Split at 28s   │
└──────────────────────────┬────────────────────────────────┘
                           ▼
┌───────────────────────────────────────────────────────────┐
│  Grammar Correction                                       │
│                                                           │
│  Apple Intelligence  │  Ollama        │  LM Studio        │
│  On-device           │  localhost LLM │  localhost/LAN API  │
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

Tap twice within 0.4s (default). Adjust `double_tap_threshold` in config when you want a wider or tighter window.

</details>

<details>
<summary><strong>Apple Intelligence not working</strong></summary>

Verify:
1. **macOS 26** or later
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

`setup.sh` downloads and warms the active transcription engine. Fresh installs use Parakeet by default. Qwen3-ASR downloads when you switch to it, WhisperKit manages its own models, and Kokoro downloads only after text-to-speech is enabled. After a model is cached, later runs load it from disk.

</details>

<details>
<summary><strong>Empty transcription</strong></summary>

- Speak clearly, close to the microphone
- Check microphone permissions in System Settings
- Confirm the correct input device is selected
- If the first recording after sleep, wake, or a long idle period is empty, try once more. Local Whisper now resets stale macOS input streams when it sees all-zero audio or a PortAudio input error.

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
pytest tests/         # Run the full test suite
```

### Mobile Apps

The Flutter app lives in `src/flutter/local_whisper`.

| Surface | Status | Notes |
|---------|--------|-------|
| Flutter iOS app | Native transcription wired | Uses `AVAudioEngine` plus WhisperKit/Core ML through the native Swift bridge. |
| Flutter Android app + keyboard | Native transcription wired | Uses local WAV recording plus sherpa-onnx. Parakeet-TDT v3 INT8 ONNX is the default Android model, with Qwen3-ASR 0.6B INT8 ONNX available for broader language coverage. |

See [Mobile apps](https://gabrimatic.github.io/local-whisper/product/mobile/) for setup flow, keyboard behavior, model packs, Android notes, and mobile checks.

### Adding an Engine or Grammar Backend

Engines: implement `TranscriptionEngine` in `engines/`, register in `ENGINE_REGISTRY`.
Grammar backends: implement `GrammarBackend` in `backends/`, register in `BACKEND_REGISTRY`.

Menu, CLI, and Settings entries come from the registries.

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
│       ├── AppState.swift           # Observable state, IPC handler, ConnectionState
│       ├── IPCClient.swift          # Unix socket client + connection-state publishing
│       ├── IPCMessages.swift        # Codable message types
│       ├── Theme.swift              # Typography, spacing, radii, tones, accents
│       ├── MenuBarView.swift        # Menu bar dropdown (status + connection state)
│       ├── OverlayWindowController.swift
│       ├── OverlayView.swift        # Floating pill: waveform + state
│       ├── OnboardingView.swift     # First-launch + replay tutorial
│       ├── SettingsView.swift       # Sidebar root + section enum
│       ├── RecordingPanel.swift     # Trigger key + audio cleanup
│       ├── TranscriptionPanel.swift # Engine picker + per-engine params
│       ├── GrammarPanel.swift       # Backend picker + Ollama / LM Studio / AI
│       ├── VoicePanel.swift         # TTS + dictation commands
│       ├── VocabularyPanel.swift    # Replacements editor (search, import / export)
│       ├── OutputPanel.swift        # Overlay, sounds, notifications, paste, history
│       ├── ShortcutsPanel.swift     # Text-transform keybindings + cheatsheet
│       ├── ActivityPanel.swift      # Usage stats with 30-day chart
│       ├── AdvancedPanel.swift      # Live status, storage, diagnostics, service control
│       ├── AboutView.swift          # Hero, credits, links, replay tutorial
│       ├── SharedViews.swift        # DeferredText fields, StatusPill, InlineNotice, headers
│       └── Constants.swift
├── src/flutter/local_whisper/        # Flutter iOS and Android app
│   ├── lib/
│   │   ├── main.dart
│   │   └── src/
│   │       ├── app.dart              # Tabs, record/history/modes/models/settings UI
│   │       ├── native_speech_service.dart
│   │       ├── model_store.dart      # Local model catalog/install state
│   │       ├── text_polisher.dart    # Local cleanup and modes
│   │       ├── history_store.dart    # Local persistence
│   │       └── models.dart
│   ├── ios/Runner/
│   │   ├── LocalSpeechBridge.swift   # AVAudioEngine + WhisperKit bridge
│   │   ├── AppDelegate.swift
│   │   └── SceneDelegate.swift
│   ├── ios/LocalWhisperKeyboard/     # Native keyboard extension
│   ├── android/app/src/main/
│   │   ├── AndroidManifest.xml       # App identity, microphone, haptics, input method
│   │   ├── kotlin/info/gabrimatic/localwhisper/
│   │   │   ├── MainActivity.kt       # Method/event channels for recording and setup
│   │   │   └── LocalWhisperInputMethodService.kt
│   │   └── res/                      # Launch theme, keyboard XML, launcher icons
│   └── test/
└── src/whisper_voice/
    ├── app.py              # App class + service_main (imports mixins)
    ├── app_ipc.py          # IPCMixin: IPC send/receive
    ├── app_recording.py    # RecordingMixin: keyboard + recording lifecycle
    ├── app_pipeline.py     # PipelineMixin: transcription pipeline
    ├── app_commands.py     # CommandsMixin: CLI command handlers
    ├── app_switching.py    # SwitchingMixin: engine/backend switching
    ├── cli/                # CLI package (wh)
    │   ├── constants.py    # Colors, path constants
    │   ├── lifecycle.py    # start/stop/status
    │   ├── build.py        # Swift UI build, restart
    │   ├── settings.py     # engine/backend/replace commands
    │   ├── editor.py       # Interactive config TUI
    │   ├── client.py       # whisper/listen/transcribe socket client
    │   ├── doctor.py       # wh doctor + wh update
    │   └── main.py         # help, version, cli_main dispatcher
    ├── config/             # Config package
    │   ├── schema.py       # Dataclasses + DEFAULT_CONFIG
    │   ├── loader.py       # load_config, get_config, singleton
    │   ├── toml_helpers.py # _find/_replace_in_section, _serialize_toml_value
    │   └── mutations.py    # add/remove_replacement, update_config_field
    ├── ipc_server.py       # IPC server (Swift UI)
    ├── cmd_server.py       # Command server (CLI)
    ├── audio.py            # Recording and pre-buffer
    ├── audio_processor.py  # VAD, noise reduction, normalization
    ├── backup.py           # History persistence
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
    │   ├── base.py             # TranscriptionEngine base
    │   ├── parakeet.py         # Parakeet-TDT v3 (MLX, default)
    │   ├── qwen3_asr.py        # Qwen3-ASR (MLX)
    │   ├── whisperkit.py       # WhisperKit (localhost)
    │   ├── status.py           # Cache status + on-disk size reporting
    │   └── download_progress.py # HF preflight + inline progress bar IPC
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
└── models/                 # Parakeet-TDT, Qwen3-ASR, Kokoro TTS
```

</details>

---

## Credits

[parakeet-mlx](https://github.com/senstella/parakeet-mlx) (MLX port of NVIDIA Parakeet) · [Parakeet-TDT](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) by [NVIDIA NeMo](https://github.com/NVIDIA/NeMo) · [qwen3-asr-mlx](https://github.com/gabrimatic/qwen3-asr-mlx) (MLX port of Qwen3-ASR) · [kokoro-mlx](https://github.com/gabrimatic/kokoro-mlx) (MLX port of Kokoro-82M) · [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) by [Qwen Team](https://qwen.ai) · [Kokoro-82M](https://github.com/remsky/Kokoro-FastAPI) · [WhisperKit](https://github.com/argmaxinc/WhisperKit) by [Argmax](https://www.argmaxinc.com) · [Apple Intelligence](https://www.apple.com/apple-intelligence/) · [Apple FM SDK](https://github.com/apple/python-apple-fm-sdk) · [Ollama](https://ollama.com) · [LM Studio](https://lmstudio.ai) · [SwiftUI](https://developer.apple.com/swiftui/)

<details>
<summary><strong>Legal notices</strong></summary>

### Trademarks

"Whisper" is a trademark of OpenAI. "Apple Intelligence" is a trademark of Apple Inc. "WhisperKit" is a trademark of Argmax, Inc. "Qwen" is a trademark of Alibaba Cloud. "Parakeet" and "NeMo" are trademarks of NVIDIA Corporation. "Ollama" and "LM Studio" are trademarks of their respective owners.

This project is not affiliated with, endorsed by, or sponsored by OpenAI, Apple, Argmax, Alibaba Cloud, NVIDIA, or any other trademark holder. All trademark names are used solely to describe compatibility with their respective technologies.

### Third-Party Licenses

This project depends on [pynput](https://github.com/moses-palmer/pynput), licensed under LGPL-3.0. It remains under its own license.

Other dependencies keep their own licenses. See each package for details.

</details>

## License

Source-available under the PolyForm Noncommercial License 1.0.0. Noncommercial use, modification, and redistribution are allowed when the license and required notices stay with the software. Commercial use requires written permission from Soroush Yousefpour. See [LICENSE](LICENSE).

---

[Soroush Yousefpour](https://gabrimatic.info)

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/gabrimatic)

# Local Whisper

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)]()
[![Apple Silicon](https://img.shields.io/badge/Apple_Silicon-required-blue.svg)]()
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)]()

**Local voice transcription with grammar correction for macOS.**

Double-tap a key, speak, tap to stop. Polished text lands in your clipboard. No cloud, no internet, no tracking.

## What It Does

1. **App runs as background service** (configure via `wh backend`)
2. **Double-tap Right Option** to start recording
3. **Speak** naturally (filler words like "um", "uh", "like" are OK)
4. **Tap once** (Right Option or Space) to stop
5. **Press Esc** to cancel recording (no save, no transcription)
6. **WhisperKit** transcribes your speech locally
7. **Grammar backend** fixes grammar and removes filler words
8. **Text copied** to clipboard, paste anywhere

## Grammar Backends

Pick a grammar correction engine:

| Backend | Requirements | Description |
|---------|--------------|-------------|
| **Apple Intelligence** | macOS 26+, Apple Silicon, Apple Intelligence enabled | On-device, fastest, best quality |
| **Ollama** | Ollama installed and running | Local LLM server, works on any Mac |
| **LM Studio** | LM Studio with model loaded + server started | OpenAI-compatible, works on any Mac |
| **None** | - | Transcription only, no grammar correction |

## Privacy

Everything runs on your Mac:

| Component | Purpose | Location |
|-----------|---------|----------|
| WhisperKit | Speech-to-text | localhost:50060 |
| Apple Intelligence | Grammar correction | On-device (built-in) |
| Ollama | Grammar correction | localhost:11434 |
| LM Studio | Grammar correction | localhost:1234 |
| Config file | Your settings | ~/.whisper/config.toml |
| Audio backup | Recovery if needed | ~/.whisper/ |

**Zero data leaves your machine.**

## Requirements

### Apple Intelligence
- macOS 26+ (Tahoe) with Foundation Models
- Apple Silicon (M1/M2/M3/M4)
- Apple Intelligence enabled in System Settings

### Ollama
- Ollama installed ([ollama.ai](https://ollama.ai))
- A grammar model pulled (e.g., `ollama pull gemma3:4b-it-qat`)
- Ollama server running (`ollama serve`)

### LM Studio
- LM Studio installed ([lmstudio.ai](https://lmstudio.ai))
- A model loaded in LM Studio
- Local server running (Developer > Start Server)

### All backends
- ~4GB disk space for models
- Microphone access
- Accessibility permission (for the global hotkey)

## Installation

```bash
git clone https://github.com/gabrimatic/local-whisper.git
cd local-whisper
./setup.sh
```

`setup.sh` handles everything:
- Creates a Python virtual environment
- Installs Homebrew (if missing), Python 3.9+, and WhisperKit CLI
- Downloads and pre-compiles the WhisperKit model (~1.5GB, 5-15 min on first run)
- Builds the Apple Intelligence Swift CLI helper
- Installs all Python dependencies
- Installs a LaunchAgent for auto-start at login
- Requests Accessibility permission (System Settings opens automatically)
- Sets up the `wh` shell alias

### Installing Ollama (optional)

If you want Ollama as your grammar backend:

1. Download and install from [ollama.ai](https://ollama.ai)
2. Pull a grammar model and start the server:

```bash
# Pull a grammar model
ollama pull gemma3:4b-it-qat

# Start the server (keep running in background)
ollama serve
```

### Installing LM Studio (optional)

If you want LM Studio as your grammar backend:

1. Download from [lmstudio.ai](https://lmstudio.ai)
2. Install and open LM Studio
3. Search for and download a model (e.g., `google/gemma-3-4b`)
4. Load the model
5. **Start the local server** (required, easy to miss):
   - Go to the **Developer** tab in the left sidebar
   - Click **Start Server**
   - Confirm you see "Server running on port 1234"

> Loading a model does **not** start the API server automatically. Start it from the Developer tab, or the app reports "LM Studio not running".

## Usage

### Background Service

Local Whisper runs as a background service via a LaunchAgent. It starts automatically at login. `setup.sh` handles the full install.

### CLI Management

Use `wh` to manage the service:

```bash
# Activate venv first (or use .venv/bin/wh directly)
source .venv/bin/activate

wh                  # Status + help
wh status           # Service status, PID, backend
wh start            # Launch the service
wh stop             # Stop the service
wh restart          # Restart (auto-rebuilds Swift CLI if sources changed)
wh build            # Rebuild the Apple Intelligence Swift CLI
wh backend          # Show current backend + list available
wh backend ollama   # Switch grammar backend
wh config           # Show key config values
wh config edit      # Open config in editor
wh config path      # Print path to config file
wh log              # Tail service log
wh version          # Show version
wh uninstall        # Completely remove Local Whisper (service, config, alias)
```

### Record

| Action | Result |
|--------|--------|
| **Double-tap Right Option** | Start recording |
| **Tap Right Option or Space** | Stop and process |
| **Tap Esc** | Cancel recording |

A floating overlay window shows recording status and duration.

### Menu Bar Options

| Menu Item | Description |
|-----------|-------------|
| Status | Current state (Ready, Recording, etc.) |
| Grammar: [Backend] | Active backend; open submenu to switch backend in-place |
| Retry Last | Re-transcribe the last recording |
| Copy Last | Copy last transcription again |
| History | Open all saved session transcripts |
| Backups | Open backup folder |
| Config | Open configuration file |
| Settings... | Open the Settings window (all config options) |
| Quit | Exit the app |

### Grammar Submenu

The **Grammar** menu item expands into a submenu of all available backends. The active one has a checkmark. Select a different entry to switch instantly (no restart).

### Settings Window

**Settings...** opens a native panel with six tabs:

| Tab | What you can configure |
|-----|----------------------|
| Recording | Trigger key, double-tap window, min/max duration, silence threshold |
| Transcription | Whisper model, language, vocabulary hint prompt, timeout |
| Grammar | Grammar correction toggle, Ollama/Apple Intelligence/LM Studio settings, keyboard shortcuts |
| Interface | Overlay visibility, overlay opacity, sounds, notifications |
| Advanced | Backup directory, WhisperKit server URLs |
| About | Version, author, open source credits |

Changes are written to `~/.whisper/config.toml` on Save. Fields that require a restart (hotkey, model, server URLs, overlay opacity, shortcuts) show a warning and offer to restart immediately.

## Features

### Core
- **Backend selection**: switch from the Grammar submenu (in-place, no restart) or with `wh backend <name>` (restarts service)
- **Settings window**: full GUI for all config options (Settings... in the menu bar)
- **Double-tap to record**: no accidental triggers
- **Tap to stop**: Right Option or Space for precise control
- **Real-time duration** display while recording
- **Floating overlay**: minimal pill showing status (recording, processing, copied)
- **Automatic grammar correction**: removes filler words, fixes punctuation
- **Clipboard integration**: text ready to paste immediately

### Keyboard Shortcuts
Transform selected text with global shortcuts:

| Shortcut | Mode | Description |
|----------|------|-------------|
| **Ctrl+Shift+G** | Proofread | Fix spelling, grammar, and punctuation only |
| **Ctrl+Shift+R** | Rewrite | Improve readability while preserving meaning |
| **Ctrl+Shift+P** | Prompt Engineer | Optimize text as an LLM prompt |

**How to use:**
1. Select text in any app
2. Press the shortcut
3. Overlay shows the mode name while processing, then Done
4. Result lands in your clipboard
5. Paste the transformed text

### Reliability
- **Auto-backup** of every recording and transcription
- **Retry function** if transcription fails
- **Unlimited** recording duration
- **Silence detection**: rejects empty recordings
- **Hallucination filter**: blocks Whisper's common false outputs

### Feedback
- **Sound effects**: "Pop" on record start, "Glass" on success, "Basso" on failure
- **Status icons**: Animated waveform in menu bar and overlay
- **Overlay states**: `0.0` recording, `···` processing, `Copied` done, `Failed` error
- **Console logging** with timestamps and colors

## Configuration

Settings live in `~/.whisper/config.toml`. Edit via the Settings window, the Config menu item (opens in your editor), or directly:

```toml
[hotkey]
# Key options: alt_r, alt_l, ctrl_r, ctrl_l, cmd_r, cmd_l, shift_r, shift_l, caps_lock, f1-f12
key = "alt_r"
double_tap_threshold = 0.4  # seconds

[whisper]
model = "whisper-large-v3-v20240930"
language = "auto"  # e.g. "en", or "auto" for detection
url = "http://localhost:50060/v1/audio/transcriptions"
check_url = "http://localhost:50060/"
timeout = 0  # no limit
# Context prompt guides transcription style and vocabulary (professional/technical default)
# Default prompt is English and only applied when language is "en".
# Set to empty string ("") to disable, or set your own prompt for other languages.
prompt = ""  # Optional vocabulary hint (technical terms, names). Leave empty unless needed.

[grammar]
# Backend: "apple_intelligence", "ollama", or "lm_studio"
backend = "apple_intelligence"
# Enable grammar correction (overridden by startup selection)
enabled = true

[ollama]
url = "http://localhost:11434/api/generate"
check_url = "http://localhost:11434/"
model = "gemma3:4b-it-qat"
keep_alive = "60m"  # keep model hot
timeout = 0  # no limit
max_chars = 0  # no limit
max_predict = 0  # no limit
num_ctx = 0  # no limit
unload_on_exit = false

[apple_intelligence]
max_chars = 0  # no limit (for chunking long texts)
timeout = 0  # no limit

[lm_studio]
url = "http://localhost:1234/v1/chat/completions"
check_url = "http://localhost:1234/"
model = "google/gemma-3-4b"
max_chars = 0  # no limit
max_tokens = 0  # no limit
timeout = 0  # no limit

[backup]
directory = "~/.whisper"

[audio]
sample_rate = 16000
min_duration = 0
max_duration = 0  # no limit
min_rms = 0.005  # silence threshold (0.0-1.0)

[ui]
show_overlay = true
overlay_opacity = 0.92
sounds_enabled = true
notifications_enabled = true

[shortcuts]
enabled = true  # Enable/disable all keyboard shortcuts
proofread = "ctrl+shift+g"  # Fix spelling, grammar, punctuation
rewrite = "ctrl+shift+r"  # Improve readability
prompt_engineer = "ctrl+shift+p"  # Optimize as LLM prompt
```

## How It Works

```
┌───────────────────────────────────────────────────────────┐
│                       Your Voice                          │
└───────────────────────────────────────────────────────────┘
                             │
                             ▼
┌───────────────────────────────────────────────────────────┐
│  Microphone → WAV file (16kHz mono)                       │
│  Saved to ~/.whisper/last_recording.wav                   │
└───────────────────────────────────────────────────────────┘
                             │
                             ▼
┌───────────────────────────────────────────────────────────┐
│  WhisperKit (localhost:50060)                             │
│  OpenAI-compatible API, runs on Apple Neural Engine       │
│  Output: Raw transcription                                │
└───────────────────────────────────────────────────────────┘
                             │
                             ▼
┌───────────────────────────────────────────────────────────┐
│  Grammar Backend (selected at startup)                    │
│                                                           │
│  Apple Intelligence  │  Ollama       │  LM Studio         │
│  On-device Swift     │  Local LLM    │  OpenAI-compatible │
│                                                           │
│  Removes: um, uh, like, you know, basically               │
│  Fixes: grammar, punctuation, capitalization              │
└───────────────────────────────────────────────────────────┘
                             │
                             ▼
┌───────────────────────────────────────────────────────────┐
│  Clipboard (pbcopy)                                       │
│  Ready to paste with Cmd+V                                │
└───────────────────────────────────────────────────────────┘
```

## Project Structure

```
local-whisper/
├── pyproject.toml              # Python package configuration
├── setup.sh                    # Installation script
├── README.md                   # This file
├── AGENTS.md                   # Developer guidelines
├── tests/
│   ├── test_flow.py            # End-to-end integration test
│   └── fixtures/               # Test audio and expected outputs
└── src/
    └── whisper_voice/
        ├── __init__.py         # Package initialization
        ├── __main__.py         # Entry point for python -m
        ├── app.py              # Main menu bar application
        ├── audio.py            # Audio recording
        ├── backup.py           # File backup manager
        ├── config.py           # Configuration management
        ├── cli.py              # CLI service controller (wh command)
        ├── grammar.py          # Grammar backend factory
        ├── overlay.py          # Floating window UI
        ├── settings.py         # Settings window (6-tab NSPanel)
        ├── transcriber.py      # WhisperKit integration
        ├── utils.py            # Logging and helpers
        ├── shortcuts.py        # Global keyboard shortcuts
        ├── key_interceptor.py  # Low-level CGEvent tap for keyboard shortcuts
        └── backends/           # Grammar correction backends
            ├── __init__.py     # Backend registry
            ├── base.py         # Abstract base class
            ├── modes.py        # Text transformation mode prompts
            ├── ollama/         # Ollama backend
            ├── lm_studio/      # LM Studio backend
            └── apple_intelligence/
                ├── backend.py  # Apple Intelligence backend
                └── cli/        # Swift CLI helper
```

Data is stored in `~/.whisper/`:
```
~/.whisper/
├── config.toml           # Your settings
├── last_recording.wav    # Audio file
├── last_raw.txt          # Before grammar fix
├── last_transcription.txt # Final text
└── history/              # All session transcripts (RAW + FIXED)
```

## Development

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in editable mode
pip install -e .

# Build the Swift CLI (one-time, required for Apple Intelligence)
cd src/whisper_voice/backends/apple_intelligence/cli
swift build -c release
cd -

# Run the app
wh

# Or run as module
python -m whisper_voice

# Run tests (requires WhisperKit + grammar backend)
python tests/test_flow.py
```

### New Grammar Backend

1. Create a folder under `backends/` with `__init__.py` and `backend.py`
2. Implement the `GrammarBackend` abstract class
3. Add an entry to `BACKEND_REGISTRY` in `backends/__init__.py`
4. Done. The menu, CLI, and Settings window generate from the registry automatically

## Troubleshooting

### "This process is not trusted"

The `wh` Python process (the LaunchAgent) needs Accessibility permission, not your terminal app.

On first run, System Settings opens automatically showing the exact process to approve. Enable it there.

> **Do not grant Accessibility to Terminal, iTerm2, Warp, or any other terminal app.** The service runs as its own standalone Python process via LaunchAgent. Granting permission to a terminal has no effect.

If System Settings didn't open automatically:
```bash
open x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility
```

Locate the `wh` process in the list, enable it, and restart (`wh restart`).

### Double-tap not working

Tap twice quickly (within 0.4s by default). Adjust `double_tap_threshold` in the config if needed.

### Apple Intelligence not working

Verify:
1. You're on **macOS 26** (Tahoe) or later
2. You have **Apple Silicon** (M1/M2/M3/M4)
3. **Apple Intelligence** is enabled in System Settings > Apple Intelligence & Siri
4. The Swift CLI is built (`./setup.sh` or `wh build`)

### Ollama not working

Verify:
1. Ollama is installed ([ollama.ai](https://ollama.ai))
2. A model is pulled: `ollama pull gemma3:4b-it-qat`
3. Server is running: `ollama serve`

### LM Studio not working

Verify:
1. LM Studio is installed ([lmstudio.ai](https://lmstudio.ai))
2. A model is downloaded and loaded
3. **The local server is running** (most common issue):
   - Developer tab > click "Start Server"
   - Confirm "Server running on port 1234" in LM Studio
   - Loading a model does **not** start the server automatically
4. Server is accessible at `http://localhost:1234`

Test the server:
```bash
curl http://localhost:1234/v1/models
```

### "CLI not built" error

Compile the Swift CLI once:
```bash
wh build
```

`./setup.sh` does this automatically.

### Transcription slow

First run downloads the Whisper model (~1.5GB for default model). Subsequent runs are faster.

### Empty transcription

- Speak clearly, close to the microphone
- Check microphone permissions in System Settings
- Confirm the correct input device is selected

### Floating overlay not showing

Check `show_overlay = true` in your config file (`~/.whisper/config.toml`).

## Available WhisperKit Models

All models by [Argmax](https://github.com/argmaxinc/WhisperKit), running locally on Apple Neural Engine.

| Model | Size | Notes |
|-------|------|-------|
| `tiny` | ~39MB | Fastest, lowest accuracy |
| `tiny.en` | ~39MB | English-only |
| `base` | ~74MB | |
| `base.en` | ~74MB | English-only |
| `small` | ~244MB | |
| `small.en` | ~244MB | English-only |
| `whisper-large-v3-v20240930` | ~1.5GB | **Recommended** (default) |

Set the model name in your config: `model = "whisper-large-v3-v20240930"`.

## Credits

| Project | Role |
|---------|------|
| [WhisperKit](https://github.com/argmaxinc/WhisperKit) by [Argmax](https://www.argmaxinc.com) | On-device speech recognition |
| [Apple Intelligence](https://www.apple.com/apple-intelligence/) | On-device language models |
| [Ollama](https://ollama.ai) | Local LLM server |
| [rumps](https://github.com/jaredks/rumps) | macOS menu bar apps in Python |
| [LM Studio](https://lmstudio.ai) | Local LLM interface |

## License

MIT License. See [LICENSE](LICENSE) for details.

---

Created by [Soroush Yousefpour](https://gabrimatic.info)

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/gabrimatic)

# Local Whisper

**Local voice transcription with grammar correction for macOS**

Double-tap a key, speak, tap to stop (Esc cancels) — polished text copied to clipboard. No cloud. No internet. No tracking.

## What It Does

1. **App runs as background service** — configure via `wh backend`
2. **Double-tap Right Option** to start recording
3. **Speak** naturally (filler words like "um", "uh", "like" are OK)
4. **Tap once** (Right Option or Space) to stop
5. **Press Esc** to cancel recording (no save, no transcription)
6. **WhisperKit** transcribes your speech locally
7. **Grammar backend** fixes grammar and removes filler words
8. **Text copied** to clipboard — just paste anywhere

## Grammar Backends

Choose your preferred grammar correction engine at startup:

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

### For Apple Intelligence backend:
- **macOS 26+** (Tahoe) for Foundation Models
- **Apple Silicon** (M1/M2/M3/M4)
- **Apple Intelligence enabled** in System Settings

### For Ollama backend:
- **Ollama** installed (download from [ollama.ai](https://ollama.ai))
- A grammar model pulled (e.g., `ollama pull gemma3:4b-it-qat`)
- Ollama server running (`ollama serve`)

### For LM Studio backend:
- **LM Studio** installed (download from [lmstudio.ai](https://lmstudio.ai))
- A model loaded in LM Studio
- LM Studio server running (Developer > Start Server)

### Common requirements:
- ~4GB disk space for models
- Microphone access
- Accessibility permission (for global hotkey)

## Installation

```bash
git clone https://github.com/gabrimatic/local-whisper.git
cd local-whisper
./setup.sh
```

The setup script automatically:
- Installs Homebrew (if needed)
- Installs Python 3.9+ and WhisperKit CLI
- **Builds the Apple Intelligence CLI helper** (one-time, ~2 seconds)
- Installs all Python dependencies

### Installing Ollama (optional)

If you want to use Ollama as your grammar backend:

1. Download and install Ollama from [ollama.ai](https://ollama.ai)
2. Pull a grammar model and start the server:

```bash
# Pull a grammar model
ollama pull gemma3:4b-it-qat

# Start the server (keep running in background)
ollama serve
```

### Installing LM Studio (optional)

If you want to use LM Studio as your grammar backend:

1. Download LM Studio from [lmstudio.ai](https://lmstudio.ai)
2. Install and open LM Studio
3. Search for and download a model (e.g., `google/gemma-3-4b`)
4. Load the model
5. **Start the local server** (this step is required!):
   - Go to the **Developer** tab in the left sidebar
   - Click **Start Server**
   - You should see "Server running on port 1234"

> ⚠️ **Important**: Loading a model in LM Studio does NOT automatically start the API server. You must explicitly start it from the Developer tab, or the app will report "LM Studio not running".

## Usage

### Background Service

Local Whisper runs as a background service via a LaunchAgent. It starts automatically at login after `wh install`.

### CLI Management

Use `wh` to manage the service:

```bash
# Activate venv first (or use .venv/bin/wh directly)
source .venv/bin/activate

wh                  # Status + help
wh status           # Service status, PID, backend
wh start            # Launch the service
wh stop             # Stop the service
wh restart          # Restart the service
wh backend          # Show current backend + list available
wh backend ollama   # Switch grammar backend
wh config           # Show key config values
wh config edit      # Open config in editor
wh log              # Tail service log
wh version          # Show version
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
| Grammar: [Backend] | Shows active grammar backend |
| Retry Last | Re-transcribe the last recording |
| Copy Last | Copy last transcription again |
| History | Open all saved session transcripts |
| Backups | Open backup folder |
| Config | Open configuration file |
| Quit | Exit the app |

## Features

### Core
- **Backend selection** — switch with `wh backend <name>`
- **Double-tap to record** — no accidental triggers
- **Tap to stop** — Right Option or Space for precise control
- **Real-time duration** display while recording
- **Floating overlay** — minimal pill showing status (recording, processing, copied)
- **Automatic grammar correction** — removes filler words, fixes punctuation
- **Clipboard integration** — text ready to paste immediately

### Keyboard Shortcuts for Text Transformation
Transform any selected text instantly with global keyboard shortcuts:

| Shortcut | Mode | Description |
|----------|------|-------------|
| **Ctrl+Shift+G** | Proofread | Fix spelling, grammar, and punctuation only |
| **Ctrl+Shift+R** | Rewrite | Improve readability while preserving meaning |
| **Ctrl+Shift+P** | Prompt Engineer | Optimize text as an LLM prompt |

**How to use:**
1. Select text in any application
2. Press the shortcut
3. Overlay shows status (Copying, Processing, Done)
4. Result is copied to clipboard
5. Paste the transformed text

### Reliability
- **Auto-backup** of every recording and transcription
- **Retry function** if transcription fails
- **Unlimited** recording duration
- **Silence detection** — rejects empty recordings
- **Hallucination filter** — blocks Whisper's common false outputs

### Feedback
- **Sound effects** — "Pop" on record start, "Glass" on success, "Basso" on failure
- **Status icons** — Animated waveform in menu bar and overlay
- **Overlay states** — `0.0` recording, `...` processing, `Copied` done, `Failed` error
- **Console logging** with timestamps and colors

## Configuration

Settings are stored in `~/.whisper/config.toml`. Edit via menu bar (Config) or directly:

```toml
[hotkey]
# Key options: alt_r, alt_l, ctrl_r, ctrl_l, cmd_r, cmd_l, shift_r, shift_l, caps_lock, f1-f12
key = "alt_r"
double_tap_threshold = 0.4  # seconds

[whisper]
model = "large-v3-v20240930_626MB"
language = "en"  # e.g. "fa" or "auto" for detection
timeout = 0  # no limit
# Context prompt guides transcription style and vocabulary (professional/technical default)
# Default prompt is English and only applied when language is "en".
# Set to empty string ("") to disable, or set your own prompt for other languages.
prompt = "Okay, let's review the API endpoints, database schema, and deployment plan. We'll check logs, metrics, and error reports."

[grammar]
# Backend: "apple_intelligence", "ollama", or "lm_studio"
backend = "apple_intelligence"
# Enable grammar correction (overridden by startup selection)
enabled = true

[ollama]
url = "http://localhost:11434/api/generate"
model = "gemma3:4b-it-qat"
keep_alive = "60m"  # keep model hot
timeout = 0  # no limit

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

[audio]
sample_rate = 16000
min_duration = 0
max_duration = 0  # no limit
min_rms = 0.005  # silence threshold (0.0-1.0)

[ui]
show_overlay = true
overlay_opacity = 0.92
sounds_enabled = true

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
        ├── grammar.py          # Grammar backend factory
        ├── overlay.py          # Floating window UI
        ├── transcriber.py      # WhisperKit integration
        ├── utils.py            # Logging and helpers
        ├── shortcuts.py        # Global keyboard shortcuts
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

### Adding a New Grammar Backend

1. Create folder under `backends/` with `__init__.py` and `backend.py`
2. Implement `GrammarBackend` abstract class
3. Add entry to `BACKEND_REGISTRY` in `backends/__init__.py`
4. The startup menu auto-generates from the registry

## Troubleshooting

### "This process is not trusted"

Grant Accessibility permission to your terminal app (not to a .app bundle):
1. Open **System Settings**
2. Go to **Privacy & Security -> Accessibility**
3. Add your terminal app (Terminal, iTerm2, Warp, VS Code, etc.)
4. Restart the service (`wh restart`)

Or run: `open x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility`

### Double-tap not working

Make sure you tap twice quickly (within 0.4 seconds by default). You can adjust `double_tap_threshold` in the config file.

### Apple Intelligence not working

Make sure:
1. You're running **macOS 26** (Tahoe) or later
2. You have **Apple Silicon** (M1/M2/M3/M4)
3. **Apple Intelligence** is enabled in System Settings -> Apple Intelligence & Siri
4. The Swift CLI is built (run `./setup.sh` or build manually)

### Ollama not working

Make sure:
1. Ollama is installed (download from [ollama.ai](https://ollama.ai))
2. A model is pulled: `ollama pull gemma3:4b-it-qat`
3. Server is running: `ollama serve`

### LM Studio not working

Make sure:
1. LM Studio is installed from [lmstudio.ai](https://lmstudio.ai)
2. A model is downloaded and loaded in LM Studio
3. **The local server is running** (most common issue):
   - Go to Developer tab → click "Start Server"
   - Look for "Server running on port 1234" in LM Studio
   - Loading a model does NOT start the server automatically
4. Server is accessible at `http://localhost:1234`

You can test the server manually:
```bash
curl http://localhost:1234/v1/models
```

### "CLI not built" error

The Swift CLI needs to be compiled once:
```bash
cd src/whisper_voice/backends/apple_intelligence/cli
swift build -c release
```

This is done automatically by `./setup.sh`.

### Transcription slow

First run downloads the Whisper model (~632MB for default model). Subsequent runs are faster.

### Empty transcription

- Speak clearly and close to the microphone
- Check microphone permissions in System Settings
- Verify the correct input device is selected

### Floating overlay not showing

Check `show_overlay = true` in your config file (`~/.whisper/config.toml`).

## Available WhisperKit Models

Models are provided by [Argmax](https://github.com/argmaxinc/WhisperKit) and run locally on Apple Neural Engine.

| Model | Size | Notes |
|-------|------|-------|
| `tiny` | ~39MB | Fastest, lowest accuracy |
| `tiny.en` | ~39MB | English-only |
| `base` | ~74MB | |
| `base.en` | ~74MB | English-only |
| `small` | ~244MB | |
| `small.en` | ~244MB | English-only |
| `large-v3-v20240930_626MB` | ~626MB | **Recommended** (default) |

Use the model name in your config (e.g., `model = "large-v3-v20240930_626MB"`).

## Credits

- [WhisperKit](https://github.com/argmaxinc/WhisperKit) by [Argmax](https://www.argmaxinc.com) — On-device speech recognition
- [Apple Intelligence](https://www.apple.com/apple-intelligence/) — On-device language models
- [Ollama](https://ollama.ai) — Local LLM server
- [rumps](https://github.com/jaredks/rumps) — macOS menu bar apps in Python
- [LM Studio](https://lmstudio.ai) — Local LLM interface

## License

MIT License. See [LICENSE](LICENSE) for details.

---

Created by [Soroush Yousefpour](https://gabrimatic.info)

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/gabrimatic)

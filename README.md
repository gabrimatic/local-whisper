# Local Whisper

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)]()
[![Apple Silicon](https://img.shields.io/badge/Apple_Silicon-required-blue.svg)]()
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)]()

**Local voice transcription with grammar correction for macOS.**

Double-tap a key, speak, tap to stop. Polished text lands in your clipboard. No cloud, no internet, no tracking.

<p align="center">
  <img src="assets/hero.png" width="600" alt="Local Whisper recording in Notes">
</p>

---

## Quick Start

**Apple Silicon required.** ~4GB disk space for models, microphone access, Accessibility permission.

```bash
git clone https://github.com/gabrimatic/local-whisper.git
cd local-whisper
./setup.sh
```

`setup.sh` handles everything: Python venv, Homebrew, WhisperKit CLI, model download (~1.5GB), Swift CLI build, dependencies, LaunchAgent for auto-start, Accessibility permission, and the `wh` shell alias.

| Action | Key |
|--------|-----|
| Start recording | Double-tap **Right Option** |
| Stop and process | Tap **Right Option** or **Space** |
| Cancel | Tap **Esc** |

A floating overlay shows status and duration while you record.

---

## Grammar Backends

Pick a grammar correction engine (or skip grammar entirely):

| Backend | Requirements | Notes |
|---------|-------------|-------|
| **Apple Intelligence** | macOS 26+, Apple Silicon, Apple Intelligence enabled | Fastest, best quality |
| **Ollama** | [Ollama](https://ollama.ai) installed and running | Works on any Mac |
| **LM Studio** | [LM Studio](https://lmstudio.ai) with model loaded + local server started | Works on any Mac |
| **Disabled** | (none) | Transcription only |

Switch backends from the **Grammar** submenu in the menu bar (instant, no restart), with `wh backend <name>` (restarts service), or in the Settings window.

<details>
<summary><strong>Ollama setup</strong> (optional)</summary>

1. Download from [ollama.ai](https://ollama.ai)
2. Pull a model and start the server:

```bash
ollama pull gemma3:4b-it-qat
ollama serve
```

</details>

<details>
<summary><strong>LM Studio setup</strong> (optional)</summary>

1. Download from [lmstudio.ai](https://lmstudio.ai)
2. Download and load a model (e.g., `google/gemma-3-4b`)
3. **Start the local server**: Developer tab > Start Server

> Loading a model does **not** start the API server automatically. Start it from the Developer tab, or the app reports "LM Studio not running".

</details>

---

## Features

- **Double-tap to record** with no accidental triggers
- **Real-time duration** display while recording
- **Floating overlay** showing status (recording, processing, copied)
- **Automatic grammar correction** that removes filler words and fixes punctuation
- **Clipboard integration** for immediate paste
- **Settings window** with full GUI for all config options
- **Auto-backup** of every recording and transcription
- **Silence detection** that rejects empty recordings
- **Hallucination filter** that blocks Whisper's common false outputs
- **Retry function** if transcription fails

### Keyboard Shortcuts

Transform selected text in any app with global shortcuts:

| Shortcut | Mode | What it does |
|----------|------|-------------|
| **Ctrl+Shift+G** | Proofread | Fix spelling, grammar, and punctuation |
| **Ctrl+Shift+R** | Rewrite | Improve readability while preserving meaning |
| **Ctrl+Shift+P** | Prompt Engineer | Optimize text as an LLM prompt |

Select text, press the shortcut, result lands in your clipboard.

### Feedback

- **Sounds**: Pop on record start, Glass on success, Basso on failure
- **Menu bar icon**: Animated waveform during recording
- **Overlay states**: `0.0` recording · `···` processing · `Copied` done · `Failed` error

<p align="center">
  <img src="assets/overlay-recording.png" width="280" alt="Floating overlay during recording">
</p>

---

## Usage

### CLI

`wh` manages the background service:

```bash
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
wh uninstall        # Completely remove Local Whisper
```

### Menu Bar

<p align="center">
  <img src="assets/menu-bar.png" width="380" alt="Local Whisper menu bar">
</p>

| Item | Description |
|------|-------------|
| Status | Current state (Ready, Recording, etc.) |
| Grammar: [Backend] | Active backend; submenu to switch in-place |
| Retry Last | Re-transcribe the last recording |
| Copy Last | Copy last transcription again |
| History | Open saved session transcripts |
| Backups | Open backup folder |
| Config | Open configuration file |
| Settings... | Full settings GUI |
| Quit | Exit |

### Settings Window

**Settings...** in the menu bar opens a native panel with six tabs:

| Tab | What you configure |
|-----|-------------------|
| Recording | Trigger key, double-tap window, min/max duration, silence threshold |
| Transcription | Whisper model, language, vocabulary hint, timeout |
| Grammar | Backend selection, per-backend settings, keyboard shortcuts |
| Interface | Overlay visibility/opacity, sounds, notifications |
| Advanced | Backup directory, WhisperKit server URLs |
| About | Version, author, credits |

<p align="center">
  <img src="assets/settings.png" width="480" alt="Settings window">
</p>

Changes save to `~/.whisper/config.toml`. Fields that require a restart show a warning and offer to restart immediately.

---

## Configuration

Settings live in `~/.whisper/config.toml`. Edit via the Settings window, the Config menu item, `wh config edit`, or directly.

<details>
<summary><strong>Full config reference</strong></summary>

```toml
[hotkey]
# Key options: alt_r, alt_l, ctrl_r, ctrl_l, cmd_r, cmd_l, shift_r, shift_l,
#              caps_lock, f1-f12
key = "alt_r"
double_tap_threshold = 0.4  # seconds

[whisper]
model = "whisper-large-v3-v20240930"
language = "auto"  # e.g. "en", or "auto" for detection
url = "http://localhost:50060/v1/audio/transcriptions"
check_url = "http://localhost:50060/"
timeout = 0  # no limit
# Optional vocabulary hint for transcription (technical terms, names).
prompt = ""

[grammar]
# Backend: "apple_intelligence", "ollama", or "lm_studio"
backend = "apple_intelligence"
enabled = true

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

[audio]
sample_rate = 16000
min_duration = 0
max_duration = 0  # no limit
min_rms = 0.005   # silence threshold (0.0-1.0)

[backup]
directory = "~/.whisper"

[ui]
show_overlay = true
overlay_opacity = 0.92
sounds_enabled = true
notifications_enabled = true

[shortcuts]
enabled = true
proofread = "ctrl+shift+g"
rewrite = "ctrl+shift+r"
prompt_engineer = "ctrl+shift+p"
```

</details>

---

## Privacy

Everything runs on your Mac. Zero data leaves your machine.

| Component | Location |
|-----------|----------|
| WhisperKit | localhost:50060 |
| Apple Intelligence | On-device |
| Ollama | localhost:11434 |
| LM Studio | localhost:1234 |
| Config + backups | ~/.whisper/ |

---

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│  Microphone → WAV (16kHz mono) → ~/.whisper/              │
└──────────────────────────┬────────────────────────────────┘
                           ▼
┌───────────────────────────────────────────────────────────┐
│  WhisperKit (localhost:50060)                              │
│  Runs on Apple Neural Engine · OpenAI-compatible API      │
└──────────────────────────┬────────────────────────────────┘
                           ▼
┌───────────────────────────────────────────────────────────┐
│  Grammar Backend                                          │
│                                                           │
│  Apple Intelligence  │  Ollama        │  LM Studio        │
│  On-device Swift     │  localhost LLM │  OpenAI-compatible │
│                                                           │
│  Removes filler words · Fixes grammar and punctuation     │
└──────────────────────────┬────────────────────────────────┘
                           ▼
┌───────────────────────────────────────────────────────────┐
│  Clipboard (⌘V to paste)                                  │
└───────────────────────────────────────────────────────────┘
```

---

## WhisperKit Models

Models by [Argmax](https://github.com/argmaxinc/WhisperKit), running locally on Apple Neural Engine.

| Model | Size | Notes |
|-------|------|-------|
| `tiny` / `tiny.en` | ~39MB | Fastest, lowest accuracy |
| `base` / `base.en` | ~74MB | |
| `small` / `small.en` | ~244MB | |
| `whisper-large-v3-v20240930` | ~1.5GB | **Default**, best accuracy |

Set `model` in the `[whisper]` section of your config.

---

## Troubleshooting

<details>
<summary><strong>"This process is not trusted"</strong></summary>

The `wh` Python process (the LaunchAgent) needs Accessibility permission, not your terminal app.

On first run, System Settings opens automatically showing the exact process to approve. Enable it there.

**Do not grant Accessibility to Terminal, iTerm2, Warp, or any other terminal app.** The service runs as its own standalone Python process via LaunchAgent. Granting permission to a terminal has no effect.

If System Settings didn't open automatically:
```bash
open x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility
```

Locate the `wh` process, enable it, and restart: `wh restart`.

</details>

<details>
<summary><strong>Double-tap not working</strong></summary>

Tap twice quickly (within 0.4s by default). Adjust `double_tap_threshold` in the config if needed.

</details>

<details>
<summary><strong>Apple Intelligence not working</strong></summary>

Verify:
1. You're on **macOS 26** (Tahoe) or later
2. You have **Apple Silicon** (M1/M2/M3/M4)
3. **Apple Intelligence** is enabled in System Settings > Apple Intelligence & Siri
4. The Swift CLI is built (`./setup.sh` or `wh build`)

</details>

<details>
<summary><strong>Ollama not working</strong></summary>

Verify:
1. Ollama is installed ([ollama.ai](https://ollama.ai))
2. A model is pulled: `ollama pull gemma3:4b-it-qat`
3. Server is running: `ollama serve`

</details>

<details>
<summary><strong>LM Studio not working</strong></summary>

Verify:
1. LM Studio is installed ([lmstudio.ai](https://lmstudio.ai))
2. A model is downloaded and loaded
3. **The local server is running** (most common issue):
   - Developer tab > click "Start Server"
   - Confirm "Server running on port 1234" in LM Studio
   - Loading a model does **not** start the server automatically
4. Server is accessible: `curl http://localhost:1234/v1/models`

</details>

<details>
<summary><strong>"CLI not built" error</strong></summary>

Build the Swift CLI: `wh build`. `setup.sh` does this automatically.

</details>

<details>
<summary><strong>Transcription slow</strong></summary>

First run downloads the Whisper model (~1.5GB). Subsequent runs are faster.

</details>

<details>
<summary><strong>Empty transcription</strong></summary>

- Speak clearly, close to the microphone
- Check microphone permissions in System Settings
- Confirm the correct input device is selected

</details>

<details>
<summary><strong>Floating overlay not showing</strong></summary>

Check `show_overlay = true` in `~/.whisper/config.toml`.

</details>

---

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Build Swift CLI (one-time, for Apple Intelligence)
wh build

# Run
wh
# or: python -m whisper_voice

# Test (requires WhisperKit + grammar backend)
python tests/test_flow.py
```

### Adding a Backend

1. Create a folder under `backends/` with `__init__.py` and `backend.py`
2. Implement the `GrammarBackend` abstract class
3. Add an entry to `BACKEND_REGISTRY` in `backends/__init__.py`
4. Menu, CLI, and Settings auto-generate from the registry

<details>
<summary><strong>Project structure</strong></summary>

```
local-whisper/
├── pyproject.toml
├── setup.sh
├── tests/
│   ├── test_flow.py
│   └── fixtures/
└── src/whisper_voice/
    ├── app.py              # Menu bar application
    ├── cli.py              # CLI controller (wh)
    ├── audio.py            # Audio recording
    ├── backup.py           # File backup
    ├── config.py           # Config management
    ├── grammar.py          # Backend factory
    ├── overlay.py          # Floating UI
    ├── settings.py         # Settings window (6-tab NSPanel)
    ├── transcriber.py      # WhisperKit client
    ├── utils.py            # Helpers
    ├── shortcuts.py        # Keyboard shortcuts
    ├── key_interceptor.py  # CGEvent tap
    └── backends/
        ├── base.py         # Abstract base
        ├── modes.py        # Transformation modes
        ├── ollama/
        ├── lm_studio/
        └── apple_intelligence/
            ├── backend.py
            └── cli/        # Swift CLI helper
```

Data stored in `~/.whisper/`:
```
~/.whisper/
├── config.toml             # Settings
├── last_recording.wav      # Audio file
├── last_raw.txt            # Before grammar fix
├── last_transcription.txt  # Final text
└── history/                # All session transcripts
```

</details>

---

## Credits

[WhisperKit](https://github.com/argmaxinc/WhisperKit) by [Argmax](https://www.argmaxinc.com) · [Apple Intelligence](https://www.apple.com/apple-intelligence/) · [Ollama](https://ollama.ai) · [rumps](https://github.com/jaredks/rumps) · [LM Studio](https://lmstudio.ai)

<details>
<summary><strong>Legal notices</strong></summary>

### Trademarks

"Whisper" is a trademark of OpenAI. "Apple Intelligence" is a trademark of Apple Inc. "WhisperKit" is a trademark of Argmax, Inc. "Ollama" and "LM Studio" are trademarks of their respective owners.

This project is not affiliated with, endorsed by, or sponsored by OpenAI, Apple, Argmax, or any other trademark holder. All trademark names are used solely to describe compatibility with their respective technologies.

### Third-Party Licenses

This project depends on [pynput](https://github.com/moses-palmer/pynput), licensed under LGPL-3.0. When installed via pip (the default), pynput is dynamically linked and fully compatible with this project's MIT license. If you redistribute the py2app bundle (`scripts/build_app.sh`), pynput is statically bundled; LGPL-3.0 requires that you allow end users to re-link against their own version of pynput. The complete source of this project (including build scripts) satisfies this requirement.

All other dependencies use MIT, BSD, or Apache 2.0 licenses. See each package for details.

</details>

## License

MIT License. See [LICENSE](LICENSE) for details.

---

Created by [Soroush Yousefpour](https://gabrimatic.info)

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/gabrimatic)

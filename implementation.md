# Wake Word Detection Implementation

## Overview

Added hands-free wake word activation to Local Whisper, enabling voice-triggered recording alongside the existing hotkey activation.

**Phase 1 Scope:** Pre-trained wake word ("hey jarvis") with manual stop (tap/space/esc)
**Future:** Custom "hey whisper" model + voice stop phrase

---

## What Was Implemented

### New Module: `src/whisper_voice/wakeword/`

```
wakeword/
├── __init__.py              # Factory function + module exports
├── base.py                  # WakeWordEngine abstract base class
├── detector.py              # WakeWordDetector (streaming + coordination)
└── openwakeword/
    ├── __init__.py          # Package init
    └── engine.py            # OpenWakeWord implementation
```

### Modified Files

| File | Changes |
|------|---------|
| `app.py` | Wake word init, callbacks, pause/resume coordination |
| `config.py` | Added `WakeWordConfig` dataclass + TOML parsing |
| `overlay.py` | Added "listening" status state (light blue color) |
| `setup.sh` | Added openwakeword dependency check |
| `pyproject.toml` | Added `openwakeword>=0.6.0` dependency |
| `README.md` | Documented wake word feature |
| `CLAUDE.md` | Updated architecture diagram + config reference |
| `AGENTS.md` | Mirrored CLAUDE.md changes |

### Configuration

```toml
[wakeword]
enabled = false                    # Off by default
wake_phrase = "hey_jarvis"         # Pre-trained model name
stop_phrase = ""                   # Empty = disabled (manual stop)
stop_detection_enabled = false     # Future: voice stop
sensitivity = 0.5                  # 0.0-1.0
threshold = 0.8                    # Activation probability
cooldown = 2.0                     # Seconds between activations
buffer_seconds = 3.0               # Circular buffer size
```

---

## Why These Decisions

### Engine Choice: OpenWakeWord

| Considered | Decision | Reasoning |
|------------|----------|-----------|
| OpenWakeWord | ✓ Selected | 100% open source, custom training possible, low CPU (<1%), Python native |
| Picovoice Porcupine | Rejected | Requires API key, proprietary |
| Snowboy | Rejected | Deprecated, no longer maintained |
| Vosk | Rejected | Full ASR overkill for wake word |

### Separate Audio Streams

**Decision:** Wake word uses its own sounddevice stream, separate from the recording stream.

**Why:**
- Avoids mic conflicts during recording
- Can pause/resume independently
- Buffer management isolated from main recording
- Simpler state management

### Pause During Recording (Not Stop)

**Decision:** Wake detection pauses during recording, then resumes.

**Why:**
- `pause()` preserves detector state, faster resume
- `stop()` would require full re-initialization
- No risk of wake word triggering during recording
- Seamless user experience

### Manual Stop for Phase 1

**Decision:** Voice stop phrase disabled by default, use tap/space/esc.

**Why:**
- Pre-trained "whisper stop" model doesn't exist
- Custom model training requires architecture validation first
- Manual stop already works reliably
- Reduces false positive risk during recording

### Cooldown Mechanism

**Decision:** 2-second cooldown between activations.

**Why:**
- Prevents rapid-fire triggers from echo/reverb
- Allows user to correct false positive before re-trigger
- Configurable for different environments

### Graceful Degradation

**Decision:** App works without openwakeword installed.

**Why:**
- Wake word is optional enhancement, not core feature
- Users without need don't carry dependency weight
- Clear logging explains missing feature
- No crashes from missing optional dependency

---

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  LISTENING MODE (always-on when enabled)                        │
│                                                                 │
│    sounddevice ──► Circular Buffer ──► OpenWakeWord.predict()   │
│    (separate stream)   (3 sec)              │                   │
│                                             ▼                   │
│                                    "Hey Jarvis" detected        │
│                                             │                   │
│                                             ▼                   │
│                                    Pause wake, start recording  │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. App starts → `_init_wake_word()` called if `wakeword.enabled = true`
2. `create_engine("openwakeword")` → returns `OpenWakeWordEngine`
3. Engine loads pre-trained model (downloads on first run)
4. `WakeWordDetector` created with engine + config params
5. `detector.start()` → sounddevice stream + prediction thread
6. Audio callback feeds circular buffer (3 sec, 16kHz mono)
7. Prediction loop extracts 80ms frames, runs inference
8. Detection probability > threshold → `_on_wake_detected()` callback
9. Callback pauses wake stream, plays sound, calls `_start_recording()`
10. Recording proceeds normally (existing flow)
11. After processing completes → `detector.resume()`

### Threading Model

| Thread | Purpose | Lifetime |
|--------|---------|----------|
| Main | rumps + AppKit UI | App lifetime |
| Hotkey listener | pynput callbacks | App lifetime |
| Wake audio stream | sounddevice callback | While listening |
| Wake predictor | OpenWakeWord inference | While listening |
| Recording | Audio capture | Per recording |
| Processing | Transcription + grammar | Per recording |

### Key Classes

**`WakeWordEngine` (ABC)**
- Abstract interface for wake word engines
- Methods: `load_model()`, `predict()`, `reset()`, `unload()`
- Allows swapping engines without app changes

**`OpenWakeWordEngine`**
- Wraps openwakeword library
- Handles float32→int16 conversion (with clip for overflow)
- Auto-downloads pre-trained models

**`WakeWordDetector`**
- Manages audio stream lifecycle
- Circular buffer with thread-safe access
- Background prediction loop
- Cooldown enforcement
- Pause/resume coordination

### Thread Safety

```python
# Buffer access protected
self._buffer_lock = threading.Lock()

# Stream state protected
self._stream_lock = threading.Lock()

# Listening state signaled
self._listening = threading.Event()

# Prediction thread shutdown
self._stop_predict = threading.Event()
```

### Error Handling

| Scenario | Handling |
|----------|----------|
| openwakeword not installed | Warning logged, feature disabled |
| Model load failure | Warning logged, feature disabled |
| Stream start failure | Error logged, cleanup called |
| Prediction error | Error logged, loop continues |
| Callback exception | Error logged, doesn't crash app |

---

## Testing

### Manual Test Flow

1. Enable: Set `enabled = true` in `~/.whisper/config.toml`
2. Run: `wh`
3. Say "Hey Jarvis" → should hear start sound, see "Recording"
4. Speak your message
5. Tap Space/Option → should process and copy to clipboard
6. Repeat → wake word should work again after cooldown

### Verification Points

- [ ] Wake word triggers recording
- [ ] Hotkey still works alongside wake word
- [ ] Wake detection pauses during recording
- [ ] Wake detection resumes after processing
- [ ] Cooldown prevents rapid triggers
- [ ] CPU stays low during listening (~1%)
- [ ] App works without openwakeword installed
- [ ] Menu shows wake word status when enabled

---

## Future Work

### Phase 2: Custom Wake Word

1. Train "hey whisper" model using OpenWakeWord's synthetic data pipeline
2. Add model to `wakeword/models/hey_whisper.onnx`
3. Update default `wake_phrase` config

### Phase 3: Voice Stop

1. Train "whisper stop" model
2. Implement stop detection during recording (every 500ms)
3. Require trailing silence (300ms) after phrase
4. Enable `stop_detection_enabled` by default

### Phase 4: Multiple Wake Words

1. Support array of wake phrases in config
2. Load multiple models simultaneously
3. Report which phrase triggered

---

## Files Changed Summary

```
Created:
  src/whisper_voice/wakeword/__init__.py
  src/whisper_voice/wakeword/base.py
  src/whisper_voice/wakeword/detector.py
  src/whisper_voice/wakeword/openwakeword/__init__.py
  src/whisper_voice/wakeword/openwakeword/engine.py

Modified:
  src/whisper_voice/app.py
  src/whisper_voice/config.py
  src/whisper_voice/overlay.py
  setup.sh
  pyproject.toml
  README.md
  CLAUDE.md
  AGENTS.md
```

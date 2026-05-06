# Mobile Apps

The Flutter mobile app lives in `src/flutter/local_whisper`. It brings Local Whisper's private recording flow, local history, modes, model management, and keyboard setup to iOS and Android.

<p align="center">
  <img src="../assets/ios-hero-record.png" width="760" alt="Local Whisper iOS record screen">
</p>

<p align="center">
  <img src="../assets/ios-important-screens.png" width="860" alt="Local Whisper iOS record, history, and modes screens">
</p>

## Status

| Surface | Status | Notes |
|---------|--------|-------|
| Flutter iOS app | Native transcription wired | Uses `AVAudioEngine` plus WhisperKit/Core ML through the native Swift bridge. |
| Flutter Android app | Native shell ready | Recording bridge, input method, setup flow, model management, history, modes, and QA seeding are in place. Production ASR adapter is still pending. |

## Product Flow

First launch shows setup before the tab shell:

1. Welcome
2. Recommended model install
3. Microphone permission
4. Keyboard setup and practice
5. Finish

The setup can be replayed from Settings. The progress indicator is read-only; users move with explicit actions. Optional model choices open in place instead of sending the user to another tab.

<p align="center">
  <img src="../assets/ios-setup-settings.png" width="760" alt="Local Whisper iOS setup and settings screens">
</p>

## Architecture

Flutter owns the app shell, local history, model management, modes, settings, clipboard output, and deterministic cleanup.

Native iOS uses:

- `ios/Runner/LocalSpeechBridge.swift`: microphone recording plus WhisperKit/Core ML bridge.
- `ios/LocalWhisperKeyboard/`: native keyboard extension with mode buttons, punctuation, haptics, and Verify.

Native Android uses:

- `android/app/src/main/kotlin/info/gabrimatic/localwhisper/MainActivity.kt`: microphone status, recording, levels, app settings, input-method settings, keyboard status, keyboard verification, and keyboard preference sync.
- `android/app/src/main/kotlin/info/gabrimatic/localwhisper/LocalWhisperInputMethodService.kt`: Verify, punctuation, space, new-line, settings, and haptics.
- `android/app/src/main/AndroidManifest.xml`: microphone, haptics, app identity, launcher identity, and input-method service.

## Model Packs

The model manager installs Local Whisper model families from Hugging Face snapshots and verifies installed files against a local manifest before treating a pack as installed.

| Pack | Approx size | Notes |
|------|-------------|-------|
| Qwen3-ASR | 3.8 GB | Offline ASR model family. |
| Parakeet-TDT v3 | 2.3 GB | Offline ASR model family. |
| Kokoro-82M TTS | 371 MB | Local text-to-speech model. |
| WhisperKit Large v3 | 550 MB | Wired iOS Core ML folder. |

## Android Notes

Android debug QA can seed a recommended pack and interaction data:

```bash
flutter run --dart-define=LOCAL_WHISPER_QA_SEED=true
```

Production Android still needs an Android-native offline ASR adapter before downloaded model families can transcribe. Do not add cloud speech fallback.

## Checks

Run from `src/flutter/local_whisper`:

```bash
flutter pub get
flutter analyze
flutter test
flutter build ios --simulator --debug
flutter build apk --debug

# after a WhisperKit pack is installed in the simulator:
flutter test integration_test/native_transcription_test.dart -d <simulator-id> --dart-define=LOCAL_WHISPER_MODEL_PATH=<installed-model-folder>
```

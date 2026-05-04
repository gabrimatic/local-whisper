# Local Whisper

iOS-first Flutter implementation of Local Whisper.

The app is offline by construction once the selected model pack is installed. Flutter handles the product flow, local history, model management, modes, settings, clipboard output, and deterministic cleanup. Native Swift handles microphone capture through `AVAudioEngine` and local transcription through WhisperKit/Core ML. There is no Apple Speech framework path and no cloud fallback.

## Run

```bash
flutter pub get
flutter analyze
flutter test
flutter build ios --simulator --debug
# after WhisperKit is installed on a simulator:
flutter test integration_test/native_transcription_test.dart -d <simulator-id> --dart-define=LOCAL_WHISPER_MODEL_PATH=<installed-model-folder>
```

## Structure

- `lib/src/app.dart`: app shell, tabs, recording flow, error handling, history, modes, settings.
- `lib/src/native_speech_service.dart`: Flutter method/event channel client.
- `lib/src/text_polisher.dart`: local grammar cleanup, spoken punctuation, filler removal, built-in modes.
- `lib/src/history_store.dart`: on-device settings/history/mode persistence.
- `lib/src/model_store.dart`: Local Whisper model catalog, cancelable Hugging Face snapshot installer, manifest verification, and install/remove state.
- `ios/Runner/LocalSpeechBridge.swift`: native iOS recording plus WhisperKit bridge.
- `ios/LocalWhisperKeyboard/`: native Local Whisper keyboard extension.
- `assets/app_icon/app_icon_1024.png`: shared source icon used for the Flutter iOS app icon and mirrored to the macOS app assets.

## Current iOS Flow

1. On first launch, hold the shell behind a branded loading state until stored setup state is known.
2. Run the full-screen setup flow: welcome, inline model-pack install, microphone permission, keyboard extension handoff, and practice.
3. Open the iOS app Settings page for keyboard setup and app permissions when the user asks, then let the user verify the keyboard by switching to it in the practice field and tapping Verify on the keyboard.
4. Check the selected local model state before requesting microphone permission.
5. Start native recording through `AVAudioEngine`.
6. Stop recording and transcribe the file with the selected wired local engine.
7. Return the raw transcript to Flutter.
8. Apply local cleanup and the selected dictation mode.
9. Copy the result, show it in the app, and save searchable local history.

## Model Families

- Qwen3-ASR: `mlx-community/Qwen3-ASR-1.7B-bf16` (~3.8 GB snapshot).
- Parakeet-TDT v3: `mlx-community/parakeet-tdt-0.6b-v3` (~2.3 GB snapshot).
- Kokoro-82M TTS: `mlx-community/Kokoro-82M-bf16` (~371 MB snapshot).
- WhisperKit Large v3: `argmaxinc/whisperkit-coreml`, wired to `openai_whisper-large-v3-v20240930_547MB`.
- Bundled deterministic cleanup engine.

The setup model step shows the recommended WhisperKit pack inline with install progress. The optional model list opens as an in-place sheet, so first-run setup never detours to the Models tab.

## Brand System

- Shared graphite background: `#091013`.
- Shared panel color: `#121821`.
- Shared mint accent: `#75E3BE`.
- Shared violet accent: `#AFA2FF`.
- Flutter iOS, the iOS keyboard extension, and the macOS Swift UI use the same accent palette and app-icon source.

## Setup and Settings

- First-run setup is linear and repeatable from Settings.
- Setup does not allow step jumping from the progress indicator.
- The keyboard step opens the app's iOS Settings page, explains the keyboard path, verifies the extension through the keyboard's Open button, and supports finishing without the keyboard when the user chooses that path.
- Record keeps the primary action obvious: `Start talking` begins recording when the selected WhisperKit model is installed; `Install model` opens Models when it is not. Recording shows elapsed time, a stop button, and the level meter.
- Settings groups powerful controls into focused sections for status, recording, cleanup, keyboard behavior, privacy, and onboarding replay.

## Supported Edge Cases

- Permission denied or not yet granted.
- First-run bootstrap before stored setup state loads.
- Selected model not installed.
- Model choices shown during setup without leaving setup.
- Keyboard extension not enabled, not opened yet, or blocked in secure text fields.
- Duplicate start/stop taps.
- App backgrounding during recording.
- Short recordings.
- Empty transcript or no detected speech.
- Max-duration auto-stop.
- Local persistence decode failures.
- Missing installed model files.
- Corrupt or incomplete installed model files.
- Partial model download cleanup.
- User-canceled model downloads.
- Copy/retry from history.

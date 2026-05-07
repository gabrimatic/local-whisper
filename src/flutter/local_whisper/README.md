# Local Whisper

Flutter mobile implementation of Local Whisper for iOS and Android.

Mobile is the app plus the keyboard. Record in the app, keep local model packs and history on the device, and use modes to shape the finished text. The iOS keyboard extension and Android input method bring Local Whisper actions into other text fields.

iOS records with `AVAudioEngine` and transcribes locally with WhisperKit/Core ML. Android records 16 kHz mono WAV audio, transcribes on-device with `sherpa_onnx`, and owns the native input method and setup path. There is no Apple Speech framework path and no cloud fallback.

## Run

```bash
flutter pub get
flutter analyze
flutter test
flutter build ios --simulator --debug
flutter build apk --debug
# after WhisperKit is installed on a simulator:
flutter test integration_test/native_transcription_test.dart -d <simulator-id> --dart-define=LOCAL_WHISPER_MODEL_PATH=<installed-model-folder>
# Android emulator QA seed:
flutter build apk --debug --dart-define=LOCAL_WHISPER_QA_SEED=true
```

## Structure

- `lib/src/app.dart`: app shell, tabs, recording flow, error handling, history, modes, settings.
- `lib/src/native_speech_service.dart`: Flutter method/event channel client.
- `lib/src/text_polisher.dart`: local grammar cleanup, spoken punctuation, filler removal, built-in modes.
- `lib/src/history_store.dart`: on-device settings/history/mode persistence.
- `lib/src/model_store.dart`: Local Whisper model catalog, cancelable Hugging Face snapshot installer, manifest verification, and install/remove state.
- `ios/Runner/LocalSpeechBridge.swift`: native iOS recording plus WhisperKit bridge.
- `ios/LocalWhisperKeyboard/`: native Local Whisper keyboard extension.
- `android/app/src/main/kotlin/info/gabrimatic/localwhisper/MainActivity.kt`: native Android method/event channel bridge.
- `android/app/src/main/kotlin/info/gabrimatic/localwhisper/LocalWhisperInputMethodService.kt`: native Android Local Whisper input method.
- `lib/src/sherpa_speech_service.dart`: Flutter-side Android sherpa-onnx transcription runtime.
- `assets/app_icon/app_icon_1024.png`: shared source icon used for Flutter iOS, Android launcher icons, and mirrored macOS app assets.

## Current Mobile Flow

1. On first launch, hold the shell behind a branded loading state until stored setup state is known.
2. Run the full-screen setup flow: welcome, inline model-pack install, microphone permission, keyboard/input-method handoff, and practice.
3. Open the platform settings page for keyboard setup and app permissions when the user asks, then let the user verify the keyboard by switching to Local Whisper Keyboard in the practice field and tapping Verify on the keyboard/input method.
4. Check the selected local model state before requesting microphone permission.
5. Start native recording through the platform bridge.
6. Stop recording and transcribe the file with the selected wired local engine where that production runtime exists.
7. Return the raw transcript to Flutter.
8. Apply local cleanup and the selected dictation mode.
9. Copy the result, show it in the app, and save searchable local history.

## Model Packs

- Parakeet-TDT v3 Android: `csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8` (~640 MB ONNX snapshot).
- Qwen3-ASR 0.6B Android: `pantinor/sherpa-onnx-qwen3-asr-0.6b-int8` (~940 MB ONNX snapshot).
- Qwen3-ASR MLX: `mlx-community/Qwen3-ASR-1.7B-bf16` (~3.8 GB snapshot).
- Parakeet-TDT v3 MLX: `mlx-community/parakeet-tdt-0.6b-v3` (~2.3 GB snapshot).
- Kokoro-82M TTS: `mlx-community/Kokoro-82M-bf16` (~371 MB snapshot).
- WhisperKit Large v3: `argmaxinc/whisperkit-coreml`, wired to `openai_whisper-large-v3-v20240930_547MB`.
- Bundled deterministic cleanup engine.

The setup model step shows the recommended pack inline with install progress: WhisperKit on iOS and Parakeet-TDT v3 INT8 ONNX on Android. The optional model list opens as an in-place sheet, so first-run setup never detours to the Models tab.

WhisperKit Large v3 is wired for iOS transcription today. Parakeet-TDT v3 INT8 ONNX and Qwen3-ASR 0.6B INT8 ONNX are wired for Android through sherpa-onnx. These are local packs, not hosted APIs.

## Brand System

- Shared graphite background: `#091013`.
- Shared panel color: `#121821`.
- Shared mint accent: `#75E3BE`.
- Shared violet accent: `#AFA2FF`.
- Flutter iOS, Android, the keyboard surfaces, and the macOS Swift UI use the same accent palette and app-icon source.

## Setup and Settings

- First-run setup is linear and repeatable from Settings.
- Setup does not allow step jumping from the progress indicator.
- The keyboard step opens platform settings, explains the keyboard path, verifies through a real token inserted by the keyboard/input method, and supports finishing without the keyboard when the user chooses that path.
- Record keeps the primary action obvious: `Start talking` begins recording when the selected platform model is installed; `Install model` opens Models when it is not. Recording shows elapsed time, a stop button, and the level meter.
- Settings groups powerful controls into focused sections for status, recording, cleanup, keyboard behavior, privacy, and onboarding replay.

## Android Notes

- Android uses `local_whisper/speech`, `local_whisper/levels`, and `local_whisper/setup` channels behind the same Dart APIs as iOS.
- Android uses the stable application ID `info.gabrimatic.localwhisper` and the same Local Whisper launcher mark as iOS/macOS.
- The Android input method exposes Verify, punctuation, space, new-line, settings, and haptics. Add `android.permission.VIBRATE` with the input method so haptics never crash the app.
- Android debug QA can seed the recommended pack and interaction data with `--dart-define=LOCAL_WHISPER_QA_SEED=true`.
- Android records WAV audio through `AudioRecord`, hands the path to Flutter, and transcribes in a background isolate with sherpa-onnx. Do not add Android cloud speech fallback.

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

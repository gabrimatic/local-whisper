# Android Handover

This file captures the Flutter iOS implementation state so Android can follow the same product contract without re-discovering the work.

## Current Flutter Surface

- App root: `lib/main.dart`
- Main UI and controller: `lib/src/app.dart`
- Shared models/settings/history types: `lib/src/models.dart`
- Local persistence: `lib/src/history_store.dart`
- Model pack install and verification: `lib/src/model_store.dart`
- Native speech bridge API: `lib/src/native_speech_service.dart`
- Setup/keyboard bridge API: `lib/src/setup_service.dart`
- Local deterministic cleanup: `lib/src/text_polisher.dart`

The app has five tabs: `Record`, `History`, `Modes`, `Models`, and `Settings`.

## UX Contract To Keep On Android

- First launch shows setup before the tab shell, with no flash of Home/Record underneath.
- Setup is linear: welcome, recommended model install, microphone permission, keyboard setup/practice, finish.
- Setup can be replayed from Settings.
- The setup progress indicator is read-only. Users move with explicit actions, not by tapping step chips.
- Model install should be simple on the surface but still expose choices. The recommended WhisperKit pack is inline; more packs live in an in-place chooser.
- Record must never be ambiguous:
  - If the selected recording model is installed, the primary action is `Start talking`.
  - If the selected recording model is missing, the primary action is `Install model` and opens Models.
  - While recording, show `Listening`, `Speak now`, elapsed time, a stop button, cancel, and a level meter.
  - While processing, show `Working locally` and `Transcribing and formatting offline`.
- No cloud fallback. Recording and cleanup remain local.
- Missing model files, corrupt installs, permission denial, duplicate taps, app backgrounding, short recordings, empty transcripts, and canceled downloads must have clear user-facing states.

## Keyboard Extension Behavior To Mirror

iOS has a native keyboard extension at `ios/LocalWhisperKeyboard`.

The setup flow does not silently enable the keyboard because iOS requires the user to add third-party keyboards in Settings. The containing app opens its own Settings page and verifies the keyboard by asking the user to switch to Local Whisper Keyboard in a practice field and tap `Verify`.

Android should provide the equivalent guided path for enabling the input method:

- Explain the exact enable/select steps in-app.
- Offer direct Android settings intents where supported.
- Return to an in-app practice field.
- Verify that the keyboard/input method is active through a real insert/action, not only a checkbox.
- Keep a clear fallback when the user chooses not to enable the keyboard.

## Native Work Already Done On iOS

- `ios/Runner/LocalSpeechBridge.swift` records with `AVAudioEngine`.
- The native bridge transcribes through WhisperKit/Core ML with `download: false`.
- The model path is passed from Flutter into native start/transcription calls.
- `debugTranscribeFile` supports integration testing with a bundled fixture.
- `ios/Runner/AppDelegate.swift` owns setup method-channel calls for opening settings, keyboard status, marking keyboard verification, and syncing keyboard preferences.
- `ios/LocalWhisperKeyboard/KeyboardViewController.swift` is a native keyboard with mode buttons, punctuation, haptics/quick insert settings, next-keyboard support, and a `Verify` key.

## Android Implementation Targets

- Android native speech bridge now exists behind the existing `local_whisper/speech` method channel.
- Keep the Dart API shape in `NativeSpeechService` stable:
  - `status`
  - `requestPermissions`
  - `start`
  - `stop`
  - `cancel`
  - `debugTranscribeFile`
- Emit recording levels through the existing `local_whisper/levels` event channel.
- Android setup/input-method support now exists behind `local_whisper/setup` without changing the shared Flutter setup contract.
- Reuse `ModelStore` and the same installed-model validation contract where possible.
- Android records 16 kHz mono WAV audio locally and returns the file path through the existing Dart API. Flutter then transcribes the file in `lib/src/sherpa_speech_service.dart` with sherpa-onnx. Parakeet-TDT v3 INT8 ONNX is the default Android pack, and Qwen3-ASR 0.6B INT8 ONNX is the broader multilingual pack. Debug QA can still seed the recommended pack with `--dart-define=LOCAL_WHISPER_QA_SEED=true` to exercise the full app and input-method flow without adding any cloud fallback.

## Current Android Native Surface

- `android/app/src/main/kotlin/info/gabrimatic/localwhisper/MainActivity.kt`: method-channel bridge for microphone status/permission, local `AudioRecord` WAV capture, level events, app settings, input-method settings, keyboard status, keyboard verification, and keyboard settings sync.
- `lib/src/sherpa_speech_service.dart`: Flutter-side sherpa-onnx transcription runtime for Android model packs.
- `android/app/src/main/kotlin/info/gabrimatic/localwhisper/LocalWhisperInputMethodService.kt`: native input method with Verify, punctuation, space, new-line, settings, and haptics.
- `android/app/src/main/AndroidManifest.xml`: declares microphone, haptics, app activity, launcher identity, and input-method service.
- `android/app/build.gradle.kts`: uses `info.gabrimatic.localwhisper` for both namespace and application ID.
- Android launcher icon densities are generated from `assets/app_icon/app_icon_1024.png` and the launch theme uses the shared graphite background.

## Verified iOS Checks

Run from `src/flutter/local_whisper`:

```bash
flutter test
flutter analyze
flutter build ios --simulator --debug
flutter build apk --debug
flutter test integration_test/native_transcription_test.dart -d <simulator-id> --dart-define=LOCAL_WHISPER_MODEL_PATH=<installed-model-folder>
```

Last verified simulator: iPhone 17 Pro, iOS 26.4.

The native integration test passed with the real WhisperKit model folder and bundled speech fixture.

Latest Android emulator QA used API 36 ARM (`local_whisper_api36`) with a debug build seeded by `--dart-define=LOCAL_WHISPER_QA_SEED=true`. Covered first-run setup, model-ready state, microphone permission grant, Android keyboard settings, enabling/selecting Local Whisper Keyboard, real Verify-token insertion, finish setup, tab shell, recording start/stop/result, history search, modes, models, settings, recording limits, and crash-log checks.

## Useful Simulator Evidence

The latest manual screenshots were captured under `/tmp` on the development machine:

- `/tmp/local-whisper-record-model-needed-final.png`
- `/tmp/local-whisper-record-ready-final.png`
- `/tmp/local-whisper-record-listening-final.png`
- `/tmp/local-whisper-record-processing-final.png`
- `/tmp/local-whisper-record-result-final.png`
- `/tmp/local-whisper-keyboard-final-after-verify.png`
- `/tmp/local-whisper-keyboard-scroll-before.png`

These are not source artifacts, but they document the final iOS visual states that Android should match conceptually.

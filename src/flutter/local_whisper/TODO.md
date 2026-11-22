# Local Whisper Mobile Release Checklist

This checklist tracks the mobile work needed for a publish-grade Local Whisper app and keyboard.

## Product Surface

- [x] Main iOS Flutter app shell.
- [x] Record, History, Modes, Models, Settings tabs.
- [x] Custom iOS app icon assets.
- [x] iOS keyboard extension target.
- [x] Keyboard settings in the main app.
- [x] First-run onboarding for permissions, local models, keyboard setup, and privacy.
- [ ] App Store screenshots and preview copy.
- [x] Production display name and bundle identifiers.
- [ ] Signing team, archive profile, and App Store Connect metadata.

## Local Transcription

- [x] Local model catalog with install/remove state.
- [x] Full Hugging Face snapshot installer for Qwen3-ASR, Parakeet-TDT v3, Kokoro-82M TTS, and WhisperKit.
- [x] WhisperKit/Core ML package integration.
- [x] Selected local transcription model persisted and used by the record flow.
- [ ] Native Qwen3-ASR Core ML adapter.
- [ ] Native Parakeet-TDT v3 Core ML adapter.
- [ ] Native Kokoro-82M Core ML/TTS adapter.
- [x] Model download cancellation and partial cleanup.
- [x] Model integrity checks before treating packs as installed.
- [x] Automatic retry for transient model download failures.
- [ ] Resumable downloads and detailed storage accounting.
- [ ] Import local model pack from Files.
- [ ] Low-storage and failed-download recovery.

## Text Cleanup And Modes

- [x] Deterministic local cleanup for punctuation, capitalization, and filler words.
- [x] Built-in Clean, Message, Notes, and Prompt modes.
- [x] Editable custom modes.
- [ ] Mode sync with keyboard quick actions through App Group storage.
- [ ] Custom vocabulary and replacements.
- [ ] Per-mode formatting preview.

## Keyboard Extension

- [x] Native iOS keyboard extension target.
- [x] Quick mode markers and punctuation keys.
- [x] Open main app from keyboard.
- [x] Shared settings read by the iOS keyboard from App Group and by the Android keyboard from setup preferences.
- [x] Android keyboard inserts the latest transcript from local history.
- [ ] iOS keyboard inserts the latest transcript from shared history.
- [x] Keyboard onboarding and diagnostics.
- [ ] Accessibility labels for every keyboard key.

## History, Storage, And Privacy

- [x] Searchable local transcript history.
- [x] Local persistence decode fallback.
- [x] Privacy manifest.
- [x] Export, per-entry delete, and delete-all history controls.
- [x] Storage usage breakdown for history and models.
- [ ] App lock / privacy screen option.
- [ ] Clear privacy copy for App Store submission.

## Reliability And Edge Cases

- [x] Permission denial handling.
- [x] Missing selected local model handling.
- [x] Missing installed model files are reset to not installed.
- [x] Partial model downloads are cleaned up after failure.
- [x] Duplicate start/stop tap handling.
- [x] Backgrounding during recording handling.
- [x] Short recording and empty transcript handling.
- [x] Max-duration auto-stop.
- [ ] Audio interruption and route-change recovery.
- [x] Model download cancellation.
- [x] Model download retry affordance.
- [ ] Keyboard extension unavailable/disabled diagnostics.
- [ ] Device-only test pass on a physical iPhone.

## Verification

- [x] `flutter analyze`.
- [x] `flutter test`.
- [x] `flutter build ios --simulator --debug`.
- [x] `flutter build ipa --release --no-codesign` archive build.
- [x] Build iOS Apps simulator UI pass for Record, Models, and Settings.
- [x] Build iOS Apps keyboard target/simulator install verification.
- [ ] Physical iPhone recording test with an installed local model.

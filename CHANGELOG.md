# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-02-23

### Added

- Push-to-talk voice transcription via WhisperKit (on-device)
- Three grammar correction backends: Apple Intelligence, Ollama, LM Studio
- Menu bar app with live status, grammar submenu, and backend switching
- Settings window with six tabs (Recording, Transcription, Grammar, Interface, Advanced, About)
- Global keyboard shortcuts for text transformation (Proofread, Rewrite, Prompt Engineer)
- CLI service controller (`wh`) for managing the background service
- Auto-start at login via LaunchAgent
- Floating overlay showing recording status and duration
- Audio backup and session history
- macOS notifications on completion and errors
- Hallucination filter for common Whisper false outputs
- Silence detection to reject empty recordings

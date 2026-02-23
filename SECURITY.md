# Security Policy

## Privacy by Design

Privacy is a core constraint, not a feature toggle.

- **All processing is local.** Recording, transcription, and grammar correction happen entirely on your Mac.
- **No network calls** except to localhost (WhisperKit on port 50060, Ollama on 11434, LM Studio on 1234).
- **No telemetry, no analytics, no cloud.** Zero data leaves your machine.
- **Audio stays on device.** Recordings save to `~/.whisper/` and are never transmitted.
- **No outbound connections.** The app makes no internet requests at any point.

## Permissions

Two macOS permissions, nothing more:

| Permission | Why | Scope |
|------------|-----|-------|
| **Microphone** | Record voice for transcription | Active only during recording |
| **Accessibility** | Detect global hotkey and keyboard shortcuts | Monitors key events only |

No other permissions. The app does not access contacts, location, camera, or any other system resource.

## Trust Boundaries

| Boundary | Trust Level | Notes |
|----------|-------------|-------|
| User audio | Trusted | Captured locally, stays on device |
| WhisperKit server | Trusted | Runs on localhost, bundled with the app |
| Grammar backends | Trusted | All run on localhost or on-device |
| Config file (`~/.whisper/config.toml`) | Trusted | User-controlled, local filesystem |
| Backup directory (`~/.whisper/`) | Trusted | Local, user-readable only |

No remote trust boundaries. No authentication, no API keys, no external service dependencies.

## Audio Lifecycle

1. Recording is captured to a temporary WAV file in `~/.whisper/`
2. File is sent to WhisperKit on localhost for transcription
3. Transcription text is sent to the selected grammar backend on localhost
4. Result is copied to clipboard
5. Audio file is retained in `~/.whisper/` for backup (configurable)

At no point does audio or text leave the local machine.

## Vulnerability Reporting

Report vulnerabilities responsibly:

1. **Do not open a public issue.** Vulnerabilities stay private until a fix ships.
2. Use [GitHub's private vulnerability reporting](https://github.com/gabrimatic/local-whisper/security/advisories/new) to submit.
3. Include:
   - Steps to reproduce
   - Demonstrated impact
   - Suggested fix (if any)

Reports without reproduction steps or demonstrated impact are deprioritized.

Expect acknowledgment within 48 hours.

## Out of Scope

These are not considered vulnerabilities:

- Issues requiring physical access to the machine
- Issues requiring the user to have already granted Accessibility or Microphone permission to a malicious process
- Prompt injection via grammar backend responses (the app copies text to clipboard; it does not execute it)

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |

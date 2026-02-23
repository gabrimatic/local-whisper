# Contributing

Bug fixes, new grammar backends, better docs. Here's how to get involved.

## Dev Setup

```bash
git clone https://github.com/gabrimatic/local-whisper.git
cd local-whisper
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
wh build   # compiles the Apple Intelligence Swift CLI
```

Run the service for development:

```bash
wh start
wh log     # tail live output in another terminal
```

You need Accessibility permission for the `wh` process (System Settings opens on first run) and Microphone access.

## Architecture

```
src/whisper_voice/
├── app.py              # rumps menu bar app, state machine, hotkey handling
├── cli.py              # wh CLI (start/stop/restart/backend/config)
├── audio.py            # sounddevice recorder (16kHz mono)
├── transcriber.py      # WhisperKit client + server lifecycle
├── grammar.py          # delegates to selected backend via factory
├── settings.py         # NSPanel settings window (6 tabs)
├── overlay.py          # floating status pill (AppKit)
├── shortcuts.py        # global keyboard shortcuts for text transformation
├── key_interceptor.py  # low-level CGEvent tap
├── config.py           # TOML config loader + in-place mutation helpers
├── backup.py           # ~/.whisper persistence
├── utils.py            # logging, sounds, filters
└── backends/
    ├── base.py         # abstract GrammarBackend class
    ├── modes.py        # text transformation mode prompts
    ├── ollama/         # Ollama backend (localhost:11434)
    ├── apple_intelligence/  # Apple Intelligence + Swift CLI
    └── lm_studio/      # LM Studio (OpenAI-compatible API)
```

Key constraint: **lazy loading**. Backends and models initialize only when selected. Non-selected backends stay completely uninitialized. If your change touches initialization paths, verify startup memory footprint hasn't increased.

## New Grammar Backend

1. Create a folder under `src/whisper_voice/backends/<name>/` with `__init__.py` and `backend.py`.
2. Implement the `GrammarBackend` abstract class from `backends/base.py`.
3. Add an entry to `BACKEND_REGISTRY` in `backends/__init__.py`.
4. Done. The Grammar submenu, CLI, and Settings window all generate from the registry automatically.

See `backends/ollama/` for a minimal reference implementation.

## Testing

```bash
python tests/test_flow.py   # end-to-end (requires WhisperKit + active backend)
```

Manual verification flow:

1. Run `wh` and select a grammar backend from the menu
2. Double-tap Right Option to record
3. Speak a sentence with filler words ("um", "like", etc.)
4. Single-tap to stop
5. Verify the clipboard contains cleaned text
6. Check overlay showed the correct status transitions (recording, processing, copied)

If your change affects keyboard shortcuts, also test Ctrl+Shift+G/R/P on selected text.

## PR Checklist

- One feature or fix per PR. Keep scope tight.
- Test end-to-end before opening.
- Update `README.md` if user-facing behavior changes.
- No breaking config changes without migration notes in the PR description.
- Match existing code style. No reformatting unrelated files.
- Preserve lazy loading. Eager backend/model initialization gets flagged in review.

## Reporting Issues

Use the [bug report template](https://github.com/gabrimatic/local-whisper/issues/new?template=bug_report.yml). Include:

- Output of `wh version` and `wh status`
- macOS version and chip (e.g., macOS 26.0, M4)
- Which grammar backend you're using
- Steps to reproduce, expected vs. actual behavior
- Relevant lines from `wh log` if the issue involves processing or crashes

## Vulnerability Reporting

See [SECURITY.md](SECURITY.md). Do **not** open public issues for security vulnerabilities. Use GitHub's private vulnerability reporting.

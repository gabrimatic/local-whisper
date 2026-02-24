# History Menu Feature Review

Reviewed: History submenu implementation across `app.py`, `backup.py`, `utils.py`, plus docs alignment in `README.md`, `CHANGELOG.md`, and `CLAUDE.md`.

---

## Issues Found

### CRITICAL-1: Duplicate menu titles silently drop history entries

**Location**: `/Users/soroush/Developer/Projects/local-whisper/src/whisper_voice/app.py:354-358`

**Issue**: rumps uses `MenuItem.title` as the dictionary key when calling `add()`. The key uniqueness check at `rumps/rumps.py:260` (`if key not in self`) means that if two history entries produce the same title string, the second entry is silently dropped and never appears in the menu.

This will happen in practice: two transcriptions made within the same minute with similar-length text will both truncate to the same `"{N}m ago  {first60chars}..."` string. The `_history_key` attribute (line 357) is set but never used by rumps for keying.

**Suggestion**: Append a unique suffix to the title to guarantee uniqueness. For example, prepend the loop index or append the microsecond timestamp:

```python
title = f"{label}  {preview}"
# Ensure uniqueness for rumps dictionary keying
if i > 0:
    title = f"{title}\u200B" * i  # zero-width spaces, invisible but unique
# Or more robust: use a unique invisible suffix
title = f"{label}  {preview}\u200B{ts_key[-6:]}"
```

Alternatively, use `rumps.MenuItem.__setitem__` directly with `ts_key` as the explicit key instead of relying on `add()`.

---

### CRITICAL-2: Same duplicate-title issue affects Audio Files mode

**Location**: `/Users/soroush/Developer/Projects/local-whisper/src/whisper_voice/app.py:374-377`

**Issue**: Audio file titles are `"{time_ago}  {filename}"`. With only 5 audio files max (`_MAX_AUDIO_HISTORY = 5`), collision is less likely but still possible if two recordings happen in the same second (same `time_ago` label, timestamps differ only in microseconds which are in the filename). More importantly, the filename format `YYYYMMDD_HHMMSS_ffffff.wav` is unique, so the full title should be unique. However, `time_ago` can round two very close timestamps to the same label, and if the preview filenames are identical in the first characters... Actually, since the full filename is included (not truncated), this is lower risk but worth noting.

**Suggestion**: Same approach as CRITICAL-1: ensure title uniqueness with a suffix or explicit keying.

---

### WARNING-1: `_rebuild_history_items` called from NSMenu delegate may run on main thread but reads files synchronously

**Location**: `/Users/soroush/Developer/Projects/local-whisper/src/whisper_voice/app.py:307-308`

**Issue**: `menuNeedsUpdate_` is called by AppKit on the main thread when the submenu is about to open. `_rebuild_history_items` calls `self.backup.get_history(100)` which reads up to 100 files from disk synchronously. With 100 text files, this could cause a noticeable UI stall (menu opens slowly).

The Grammar submenu does not have this problem because it only reads in-memory state.

**Suggestion**: Consider caching the history entries and rebuilding the menu from cache, updating the cache in a background thread. Or accept the tradeoff since files are small and local SSD reads are fast. At minimum, document this as a known limitation.

---

### WARNING-2: `_rebuild_history_items` clears and rebuilds on every submenu open, but `_switch_history_mode` also triggers a rebuild

**Location**: `/Users/soroush/Developer/Projects/local-whisper/src/whisper_voice/app.py:387-390`

**Issue**: When the user clicks "Transcriptions" or "Audio Files" to switch mode, `_switch_history_mode` calls `_rebuild_history_items()`. But since the submenu is still open, `menuNeedsUpdate_` may also fire again, causing a double rebuild. This depends on AppKit's delegate callback timing, but it could cause a visual flicker.

**Suggestion**: Add a simple debounce flag or timestamp check to skip rebuilds that happen too close together.

---

### WARNING-3: No thread safety on `_history_mode`

**Location**: `/Users/soroush/Developer/Projects/local-whisper/src/whisper_voice/app.py:120, 389`

**Issue**: `_history_mode` is read and written without synchronization. While menu delegate callbacks run on the main thread, the attribute is initialized during `__init__` which runs on the main thread too, so this is likely fine in practice. However, if `_rebuild_history_items` were ever called from a background thread (it currently isn't), this would be a data race.

**Suggestion**: Low risk currently. No action needed unless the threading model changes.

---

### WARNING-4: `_open_history_folder` does not handle missing directory

**Location**: `/Users/soroush/Developer/Projects/local-whisper/src/whisper_voice/app.py:412-414`

**Issue**: If `self.backup.history_dir` does not exist (e.g., user manually deleted `~/.whisper/history/`), `subprocess.run(['open', ...])` will fail silently or show a Finder error. Unlike `_on_audio_reveal` which has a try/except, `_open_history_folder` has no error handling at all.

**Suggestion**: Wrap in try/except like `_on_audio_reveal`, or ensure the directory exists before opening:

```python
def _open_history_folder(self, _):
    path = self.backup.history_dir
    path.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(['open', str(path)], timeout=5)
    except Exception as e:
        log(f"Open folder failed: {e}", "WARN")
```

---

### WARNING-5: `get_history` sorts by filename but `_prune_text_history` also sorts by filename, creating a coupling to the naming scheme

**Location**: `/Users/soroush/Developer/Projects/local-whisper/src/whisper_voice/backup.py:234, 292`

**Issue**: Both `get_history` (line 234) and `_prune_text_history` (line 292) sort by `p.name` (alphabetical). This works correctly because the filename format is `YYYYMMDD_HHMMSS_ffffff.txt` which sorts chronologically. However, `_prune_audio_history` (line 125) sorts by `p.stat().st_mtime` instead. This inconsistency means if someone manually copies a file into the history directory with a wrong timestamp, the two pruning methods would disagree on what's "oldest." Minor but inconsistent.

**Suggestion**: Pick one approach (filename-based or mtime-based) and use it consistently across both pruning methods.

---

### WARNING-6: README `~/.whisper/` directory tree is missing `audio_history/`

**Location**: `/Users/soroush/Developer/Projects/local-whisper/README.md:536-543`

**Issue**: The README's data directory tree shows:

```
~/.whisper/
├── config.toml
├── last_recording.wav
├── last_raw.txt
├── last_transcription.txt
└── history/
```

But the implementation also creates `~/.whisper/audio_history/` (backup.py:39). The History menu's Audio Files mode reads from this directory.

**Suggestion**: Add `audio_history/` to the tree:

```
~/.whisper/
├── config.toml
├── last_recording.wav
├── last_raw.txt
├── last_transcription.txt
├── history/                # Text transcription history
└── audio_history/          # Audio recording history
```

---

### NIT-1: `time_ago` uses `%-d` which is platform-specific

**Location**: `/Users/soroush/Developer/Projects/local-whisper/src/whisper_voice/utils.py:298`

**Issue**: `dt.strftime("%b %-d")` uses `%-d` (no zero-padding) which works on macOS/Linux but is not portable. Since this is a macOS-only app, it works fine, but it's worth noting.

**Suggestion**: No action needed for a macOS-only project.

---

### NIT-2: `time_ago` does not handle future timestamps

**Location**: `/Users/soroush/Developer/Projects/local-whisper/src/whisper_voice/utils.py:283-284`

**Issue**: If `dt` is in the future (e.g., system clock was adjusted), `diff.total_seconds()` would be negative, and `int(diff.total_seconds())` would be negative. The `seconds < 60` check would pass (negative is < 60), returning "Just now", which is actually reasonable behavior. No real bug here.

**Suggestion**: No action needed.

---

### NIT-3: Unused `_history_key` attribute

**Location**: `/Users/soroush/Developer/Projects/local-whisper/src/whisper_voice/app.py:357`

**Issue**: `item._history_key = ts_key` is set but never read anywhere. The comment says "for uniqueness tracking" but it's not used for that purpose.

**Suggestion**: Either remove it or use it to solve CRITICAL-1 (unique keying).

---

### NIT-4: Inconsistent error handling style between history copy and audio reveal

**Location**: `/Users/soroush/Developer/Projects/local-whisper/src/whisper_voice/app.py:392-410`

**Issue**: `_on_history_copy` plays a sound and shows overlay on success but does nothing on failure (relies on `_copy_to_clipboard` logging). `_on_audio_reveal` logs on failure but gives no user feedback. Neither shows an error overlay.

**Suggestion**: Consider adding `play_sound("Basso")` or a brief overlay error state on failure for both, matching the pattern used in the main transcription flow.

---

### NIT-5: History entries with identical text could confuse users

**Location**: `/Users/soroush/Developer/Projects/local-whisper/src/whisper_voice/app.py:346-358`

**Issue**: If a user transcribes the same phrase twice, both entries will show the same preview text (after truncation). Combined with CRITICAL-1, the second one won't even appear. Even if uniqueness is fixed, users won't be able to distinguish them except by the time-ago label.

**Suggestion**: Already addressed by fixing CRITICAL-1, but the UX could benefit from showing more timestamp precision for entries that share the same preview text.

---

## Approved Items

**ObjC delegate pattern**: The `_HistoryMenuDelegate` pattern with `self._history_delegate` stored as an instance attribute is correct. Without that reference, the delegate would be garbage collected. Keeping a strong reference on `self` prevents that. Well done.

**Lazy rebuild on menu open**: Using `menuNeedsUpdate_` instead of eagerly rebuilding after every transcription is the right call. It avoids unnecessary work and keeps the menu always fresh.

**History file parsing**: The `get_history` method in `backup.py` (lines 230-263) handles malformed files gracefully with fallbacks for both timestamp parsing and content parsing. The `'x'` mode for exclusive file creation with `FileExistsError` fallback (lines 163-170) is a nice touch for collision avoidance.

**Consistent menu structure**: The History submenu follows the same checkmark pattern as the Grammar submenu, which gives users a consistent mental model.

**Error boundaries**: Both `_on_history_copy` and `_on_audio_reveal` use `getattr` with defaults to safely handle missing custom attributes. The backup methods wrap everything in try/except so menu display never crashes.

**Text pruning**: `_prune_text_history` at 100 entries is a reasonable default. It runs after each save_history call, keeping the directory bounded.

**CHANGELOG entry**: The 1.0.1 entry (line 17) accurately describes the History feature as shipped. Clean and user-facing.

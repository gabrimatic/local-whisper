# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Build and restart commands for the LocalWhisperUI Swift package."""

import shutil
import subprocess
import sys
import time
from pathlib import Path

from .constants import C_DIM, C_GREEN, C_RED, C_RESET, C_YELLOW
from .lifecycle import _is_running, cmd_start, cmd_stop


def _local_whisper_ui_dir() -> Path:
    """Return the LocalWhisperUI Swift package source directory (repo root)."""
    # This file is at src/whisper_voice/cli/build.py
    # parents: [0]=cli/, [1]=whisper_voice/, [2]=src/, [3]=project root
    return Path(__file__).parent.parent.parent.parent / "LocalWhisperUI"


def _local_whisper_ui_binary() -> Path:
    """Return the expected path of the installed LocalWhisperUI binary."""
    return Path.home() / ".whisper" / "LocalWhisperUI.app" / "Contents" / "MacOS" / "LocalWhisperUI"


def _local_whisper_ui_sources_newer_than_binary() -> bool:
    """Return True if any LocalWhisperUI Swift source is newer than the installed binary."""
    binary = _local_whisper_ui_binary()
    if not binary.exists():
        return True
    binary_mtime = binary.stat().st_mtime
    sources_dir = _local_whisper_ui_dir() / "Sources"
    if not sources_dir.exists():
        return False
    for src in sources_dir.rglob("*.swift"):
        if src.stat().st_mtime > binary_mtime:
            return True
    return False


_LOCAL_WHISPER_UI_INFO_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>LocalWhisperUI</string>
    <key>CFBundleIdentifier</key>
    <string>com.local-whisper.ui</string>
    <key>CFBundleName</key>
    <string>Local Whisper</string>
    <key>CFBundleVersion</key>
    <string>1.3.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.3.0</string>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
</dict>
</plist>
"""


def _build_local_whisper_ui(swift: str) -> bool:
    """Build the LocalWhisperUI Swift package and assemble the .app bundle.

    Returns True on success, False on failure.
    """
    ui_dir = _local_whisper_ui_dir()
    if not ui_dir.exists():
        print(f"{C_RED}LocalWhisperUI directory not found: {ui_dir}{C_RESET}", file=sys.stderr)
        return False

    print(f"{C_DIM}Building LocalWhisperUI...{C_RESET}")
    result = subprocess.run(
        [swift, "build", "-c", "release"],
        cwd=str(ui_dir),
    )
    if result.returncode != 0:
        print(f"{C_RED}LocalWhisperUI build failed{C_RESET}", file=sys.stderr)
        return False

    # Assemble .app bundle
    built_binary = ui_dir / ".build" / "release" / "LocalWhisperUI"
    if not built_binary.exists():
        print(f"{C_RED}Built binary not found: {built_binary}{C_RESET}", file=sys.stderr)
        return False

    macos_dir = Path.home() / ".whisper" / "LocalWhisperUI.app" / "Contents" / "MacOS"
    macos_dir.mkdir(parents=True, exist_ok=True)

    dest_binary = macos_dir / "LocalWhisperUI"
    shutil.copy2(str(built_binary), str(dest_binary))
    dest_binary.chmod(0o755)

    info_plist_path = macos_dir.parent / "Info.plist"
    info_plist_path.write_text(_LOCAL_WHISPER_UI_INFO_PLIST)

    print(f"{C_GREEN}LocalWhisperUI built:{C_RESET} {macos_dir.parent.parent}")
    return True


def cmd_build():
    """Build the LocalWhisperUI Swift package."""
    swift = shutil.which("swift")
    if not swift:
        print(f"{C_RED}swift not found - install Xcode or Xcode Command Line Tools{C_RESET}", file=sys.stderr)
        sys.exit(1)

    if not _build_local_whisper_ui(swift):
        sys.exit(1)


def cmd_restart(rebuild: bool = False):
    """Stop then start, optionally rebuilding LocalWhisperUI first."""
    needs_ui_rebuild = rebuild or _local_whisper_ui_sources_newer_than_binary()

    swift = None
    if needs_ui_rebuild:
        swift = shutil.which("swift")
        if not swift:
            print(f"{C_RED}swift not found - install Xcode or Xcode Command Line Tools{C_RESET}", file=sys.stderr)
            sys.exit(1)

    if needs_ui_rebuild:
        if not rebuild:
            print(f"{C_YELLOW}LocalWhisperUI sources changed - rebuilding...{C_RESET}")
        if not _build_local_whisper_ui(swift):
            sys.exit(1)

    cmd_stop()
    # Wait for lock to actually release (up to 3s)
    for _ in range(30):
        time.sleep(0.1)
        running, _ = _is_running()
        if not running:
            break
    cmd_start()

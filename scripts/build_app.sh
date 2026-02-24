#!/bin/bash
#
# Build Local Whisper.app bundle using py2app
#
# Usage: ./scripts/build_app.sh [--venv VENV_DIR]
# Output: dist/Local Whisper.app
#
# NOTE: This bundle statically includes pynput (LGPL-3.0). The full project
# source is provided to satisfy LGPL re-linking requirements. See README.md
# "Third-Party Licenses" for details.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$SCRIPT_DIR/.venv}"

cd "$SCRIPT_DIR"

# Ensure py2app and Pillow are installed
"$VENV_DIR/bin/pip" install --quiet py2app Pillow

SWIFT_CLI="$SCRIPT_DIR/src/whisper_voice/backends/apple_intelligence/cli/.build/release/apple-ai-cli"

# Write a temporary setup_app.py for py2app
cat > "$SCRIPT_DIR/setup_app.py" <<'PYEOF'
from setuptools import setup

APP = ['src/whisper_voice/__main__.py']
DATA_FILES = []
OPTIONS = {
    'iconfile': 'src/whisper_voice/assets/LocalWhisper.icns',
    'plist': {
        'CFBundleName': 'Local Whisper',
        'CFBundleDisplayName': 'Local Whisper',
        'CFBundleIdentifier': 'com.gabrimatic.local-whisper',
        'CFBundleVersion': '1.0.1',
        'CFBundleShortVersionString': '1.0.1',
        'LSUIElement': True,
        'LSMinimumSystemVersion': '13.0',
        'NSMicrophoneUsageDescription': 'Local Whisper needs microphone access for voice transcription.',
        'NSAppleEventsUsageDescription': 'Local Whisper needs accessibility access for global hotkey detection.',
        'NSHighResolutionCapable': True,
    },
    'packages': ['whisper_voice', '_sounddevice_data'],
    'includes': [
        'rumps', 'sounddevice', 'numpy', 'requests',
        'pynput', 'pynput.keyboard', 'pynput.keyboard._darwin',
        'pynput.mouse', 'pynput.mouse._darwin',
        'pynput._util', 'pynput._util.darwin',
        'AppKit', 'Cocoa', 'Quartz',
    ],
    'resources': ['src/whisper_voice/assets'],
    'emulate_shell_environment': True,
    'site_packages': True,
}

setup(
    name='Local Whisper',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
PYEOF

# Clean previous build artifacts
rm -rf "$SCRIPT_DIR/build" "$SCRIPT_DIR/dist"

# Build the app bundle
"$VENV_DIR/bin/python" "$SCRIPT_DIR/setup_app.py" py2app 2>&1

# Remove temporary setup file
rm -f "$SCRIPT_DIR/setup_app.py"

APP_BUNDLE="$SCRIPT_DIR/dist/Local Whisper.app"

if [[ ! -d "$APP_BUNDLE" ]]; then
    echo "ERROR: App bundle not found at $APP_BUNDLE" >&2
    exit 1
fi

# Copy the Swift CLI binary into the bundle if it exists
if [[ -f "$SWIFT_CLI" ]]; then
    mkdir -p "$APP_BUNDLE/Contents/Resources/bin"
    cp "$SWIFT_CLI" "$APP_BUNDLE/Contents/Resources/bin/apple-ai-cli"
fi

# Write entitlements and ad-hoc sign the bundle
ENTITLEMENTS_FILE="$(mktemp /tmp/local-whisper-entitlements.XXXXXX.plist)"
cat > "$ENTITLEMENTS_FILE" <<'ENTEOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "https://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.device.audio-input</key>
    <true/>
    <key>com.apple.security.automation.apple-events</key>
    <true/>
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <true/>
    <key>com.apple.security.cs.disable-library-validation</key>
    <true/>
</dict>
</plist>
ENTEOF

codesign --force --deep --sign - --entitlements "$ENTITLEMENTS_FILE" "$APP_BUNDLE" 2>&1 || true
rm -f "$ENTITLEMENTS_FILE"

echo "Built: $APP_BUNDLE"

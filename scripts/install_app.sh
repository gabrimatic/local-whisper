#!/bin/bash
#
# Install Local Whisper.app to /Applications and set as Login Item
#
# Usage: ./scripts/install_app.sh
# Requires: dist/Local Whisper.app to exist (run build_app.sh first)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_BUNDLE="$SCRIPT_DIR/dist/Local Whisper.app"

if [[ ! -d "$APP_BUNDLE" ]]; then
    echo "Error: $APP_BUNDLE not found. Run ./scripts/build_app.sh first." >&2
    exit 1
fi

# Kill any running instance
pkill -x "Local Whisper" 2>/dev/null || true
pkill -f "whisper_voice" 2>/dev/null || true
rm -f /tmp/local-whisper.lock
sleep 1

# Install to /Applications
rm -rf "/Applications/Local Whisper.app"
cp -r "$APP_BUNDLE" /Applications/
echo "Installed: /Applications/Local Whisper.app"

TARGET_APP="/Applications/Local Whisper.app"

# Set Login Item
osascript -e "tell application \"System Events\" to delete (login items whose name is \"Local Whisper\")" 2>/dev/null || true
osascript -e "tell application \"System Events\" to make login item at end with properties {path:\"$TARGET_APP\", hidden:true}" 2>/dev/null && \
    echo "Login Item set (starts automatically at login)" || \
    echo "Warning: Could not set Login Item - add manually in System Settings → General → Login Items"

# Launch
open "$TARGET_APP"
echo "Local Whisper launched"

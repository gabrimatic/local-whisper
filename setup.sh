#!/bin/bash
#
# Local Whisper Setup Script
# Installs all dependencies for local voice transcription
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

log_step() { echo -e "\n${CYAN}▶${NC} $1"; }
log_ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
log_warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
log_info() { echo -e "  ${DIM}›${NC} $1"; }

fail() {
    echo ""
    echo -e "  ${RED}✗${NC} $1"
    echo -e "\n${RED}Setup failed.${NC} Fix the issue above and run this script again.\n"
    exit 1
}

write_plist() {
    # KeepAlive={SuccessfulExit=false} restarts on crash but honors `wh stop`.
    cat > "$PLIST_PATH" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.local-whisper</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_DIR/bin/wh</string>
        <string>_run</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>HF_HUB_CACHE</key>
        <string>$HOME/.whisper/models</string>
        <key>HF_HUB_OFFLINE</key>
        <string>1</string>
        <key>HF_HUB_DISABLE_TELEMETRY</key>
        <string>1</string>
    </dict>
    <key>RunAtLoad</key>
    <${1}/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>ExitTimeOut</key>
    <integer>30</integer>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>StandardOutPath</key>
    <string>$LOG_PATH</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.whisper/service.err.log</string>
</dict>
</plist>
PLIST_EOF
}

check_ax() {
    "$VENV_DIR/bin/python3" -c "
from whisper_voice.utils import check_accessibility_trusted
print('yes' if check_accessibility_trusted() else 'no')
" 2>/dev/null
}

check_mic() {
    "$VENV_DIR/bin/python3" -c "
from whisper_voice.utils import check_microphone_permission
ok, _ = check_microphone_permission()
print('yes' if ok else 'no')
" 2>/dev/null
}

# ============================================================================
# Header
# ============================================================================

echo ""
echo -e "${BOLD}╭────────────────────────────────────────╮${NC}"
echo -e "${BOLD}│${NC}  ${CYAN}Local Whisper${NC} · Setup                 ${BOLD}│${NC}"
echo -e "${BOLD}│${NC}  ${DIM}Transcription · Grammar · TTS${NC}         ${BOLD}│${NC}"
echo -e "${BOLD}╰────────────────────────────────────────╯${NC}"

# ============================================================================
# System requirements
# ============================================================================

log_step "Checking system requirements..."

if [[ "$OSTYPE" != "darwin"* ]]; then
    fail "macOS required. Detected: $OSTYPE"
fi

ARCH=$(uname -m)
if [[ "$ARCH" != "arm64" ]]; then
    fail "Apple Silicon required. Detected: $ARCH"
fi

MACOS_VERSION=$(sw_vers -productVersion)
MACOS_MAJOR=$(echo "$MACOS_VERSION" | cut -d'.' -f1)
if [[ "$MACOS_MAJOR" -lt 15 ]]; then
    log_ok "macOS $MACOS_VERSION (Apple Intelligence requires macOS 15+)"
else
    log_ok "macOS $MACOS_VERSION"
fi

# ============================================================================
# Homebrew
# ============================================================================

log_step "Checking Homebrew..."

if ! command -v brew &> /dev/null; then
    log_info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || \
        fail "Homebrew install failed. Visit https://brew.sh"
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi
log_ok "Homebrew ready"

# ============================================================================
# Python
# ============================================================================

log_step "Checking Python..."

# Find a compatible Python (3.11 or 3.12). Misaki (Kokoro TTS dep) requires <3.13.
PYTHON_BIN=""
for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" &> /dev/null; then
        _VER=$("$candidate" --version 2>&1 | cut -d' ' -f2)
        _MAJ=$(echo "$_VER" | cut -d'.' -f1)
        _MIN=$(echo "$_VER" | cut -d'.' -f2)
        if [[ "$_MAJ" -eq 3 && "$_MIN" -ge 11 && "$_MIN" -lt 13 ]]; then
            PYTHON_BIN=$(command -v "$candidate")
            PYTHON_VERSION="$_VER"
            break
        fi
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    log_info "No compatible Python found. Installing python@3.12 via Homebrew..."
    brew install python@3.12 || fail "Failed to install Python 3.12"
    PYTHON_BIN="$(brew --prefix python@3.12)/bin/python3.12"
    PYTHON_VERSION=$("$PYTHON_BIN" --version 2>&1 | cut -d' ' -f2)
fi
log_ok "Python $PYTHON_VERSION ($PYTHON_BIN)"

# ============================================================================
# Virtual environment + package install
# ============================================================================

log_step "Installing local-whisper..."

VENV_DIR="$SCRIPT_DIR/.venv"

# Recreate venv if it exists but uses an incompatible Python
if [[ -d "$VENV_DIR" ]]; then
    VENV_PY_VER=$("$VENV_DIR/bin/python3" --version 2>&1 | cut -d' ' -f2 || echo "0.0.0")
    VENV_PY_MIN=$(echo "$VENV_PY_VER" | cut -d'.' -f2)
    if [[ "$VENV_PY_MIN" -lt 11 || "$VENV_PY_MIN" -ge 13 ]]; then
        log_info "Recreating venv (was Python $VENV_PY_VER, need 3.11-3.12)..."
        rm -rf "$VENV_DIR"
    fi
fi

if [[ ! -d "$VENV_DIR" ]]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR" || fail "Failed to create virtual environment"
fi

source "$VENV_DIR/bin/activate" || fail "Failed to activate virtual environment"

pip install --upgrade pip -q || fail "Failed to upgrade pip"
# Apple Intelligence Foundation Models SDK supports macOS 15+.
# Earlier systems skip the optional extra and fall back to Ollama or LM Studio.
if [[ "$MACOS_MAJOR" -ge 15 ]]; then
    pip install -e "$SCRIPT_DIR[apple-intelligence]" -q || fail "Failed to install package"
    log_ok "Package installed (with Apple Intelligence)"
else
    pip install -e "$SCRIPT_DIR" -q || fail "Failed to install package"
    log_ok "Package installed"
fi

# ============================================================================
# Configuration
# ============================================================================

log_step "Configuring..."
mkdir -p "$HOME/.whisper"

"$VENV_DIR/bin/python" -c "
import re
from whisper_voice.config import DEFAULT_CONFIG
from pathlib import Path

config_path = Path.home() / '.whisper' / 'config.toml'

if not config_path.exists():
    config_path.write_text(DEFAULT_CONFIG, encoding='utf-8')
    print('created')
else:
    existing = config_path.read_text(encoding='utf-8')
    existing_sections = set(re.findall(r'^\[([^\]]+)\]', existing, re.MULTILINE))
    default_blocks = re.split(r'(?=^\[[^\]]+\])', DEFAULT_CONFIG, flags=re.MULTILINE)
    appended = []
    for block in default_blocks:
        m = re.match(r'^\[([^\]]+)\]', block)
        if m and m.group(1) not in existing_sections:
            appended.append(block.rstrip())
    if appended:
        with config_path.open('a', encoding='utf-8') as f:
            f.write('\n')
            f.write('\n'.join(appended))
            f.write('\n')
        print('updated')
    else:
        print('current')
" 2>/dev/null && log_ok "Config at ~/.whisper/config.toml" || log_warn "Could not write config"

MODEL_DIR="$HOME/.whisper/models"
mkdir -p "$MODEL_DIR"

# ============================================================================
# Models
# ============================================================================

log_step "Downloading models (one-time)..."

# Transcription engine: only prepare the currently-selected one. Users who
# switch engines later pay the download + warm-up on that switch's first call
# (engines lazy-load). Warm-up compiles the MLX graph (kernels cached to disk);
# it does not keep the model in RAM.
ACTIVE_ENGINE=$("$VENV_DIR/bin/python3" -c "
from whisper_voice.config import load_config
print(load_config().transcription.engine)
" 2>/dev/null || echo "parakeet_v3")

case "$ACTIVE_ENGINE" in
    parakeet_v3)
        if HF_HUB_CACHE="$MODEL_DIR" HF_HUB_DISABLE_TELEMETRY=1 "$VENV_DIR/bin/python3" -c "
from parakeet_mlx import from_pretrained
from_pretrained('mlx-community/parakeet-tdt-0.6b-v3')
" 2>/dev/null; then
            log_ok "Parakeet-TDT v3 model"
        else
            log_warn "Parakeet download failed (will retry on first use)"
        fi

        PARAKEET_WARM_SENTINEL="$MODEL_DIR/.parakeet_v3_warmed"
        if [[ -f "$PARAKEET_WARM_SENTINEL" ]]; then
            log_ok "Parakeet already warmed up"
        else
            log_info "Warming up Parakeet (compiling MLX graph, ~30s, one-time)..."
            if HF_HUB_CACHE="$MODEL_DIR" HF_HUB_DISABLE_TELEMETRY=1 "$VENV_DIR/bin/python3" -c "
import numpy as np, tempfile, wave, os
from parakeet_mlx import from_pretrained
model = from_pretrained('mlx-community/parakeet-tdt-0.6b-v3')
sr = int(model.preprocessor_config.sample_rate)
silence = np.zeros(int(sr * 0.5), dtype=np.int16)
with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
    path = f.name
try:
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(silence.tobytes())
    model.transcribe(path)
finally:
    try: os.unlink(path)
    except OSError: pass
" 2>/dev/null; then
                touch "$PARAKEET_WARM_SENTINEL"
                log_ok "Parakeet warmed up"
            else
                log_warn "Parakeet warm-up failed (first transcription may be slower)"
            fi
        fi
        ;;

    qwen3_asr)
        if HF_HUB_CACHE="$MODEL_DIR" HF_HUB_DISABLE_TELEMETRY=1 "$VENV_DIR/bin/python3" -c "
from qwen3_asr_mlx import Qwen3ASR
Qwen3ASR.from_pretrained('mlx-community/Qwen3-ASR-1.7B-bf16')
" 2>/dev/null; then
            log_ok "Qwen3-ASR model"
        else
            log_warn "Qwen3-ASR download failed (will retry on first use)"
        fi

        QWEN_WARM_SENTINEL="$MODEL_DIR/.qwen3_warmed"
        if [[ -f "$QWEN_WARM_SENTINEL" ]]; then
            log_ok "Qwen3-ASR already warmed up"
        else
            log_info "Warming up Qwen3-ASR (compiling MLX graph, 60-120s, one-time)..."
            if HF_HUB_CACHE="$MODEL_DIR" HF_HUB_DISABLE_TELEMETRY=1 "$VENV_DIR/bin/python3" -c "
from qwen3_asr_mlx import Qwen3ASR
model = Qwen3ASR.from_pretrained('mlx-community/Qwen3-ASR-1.7B-bf16')
model.warm_up()
" 2>/dev/null; then
                touch "$QWEN_WARM_SENTINEL"
                log_ok "Qwen3-ASR warmed up"
            else
                log_warn "Warm-up failed (first transcription may be slower)"
            fi
        fi
        ;;

    whisperkit)
        log_info "WhisperKit engine selected. Install 'whisperkit-cli' via Homebrew; models download on first run."
        ;;

    *)
        log_warn "Unknown engine '$ACTIVE_ENGINE'. Model download skipped."
        ;;
esac

# Text-to-Speech (Kokoro): only prepare when the user has TTS enabled. Off by
# default to keep fresh installs lean (~170 MB model + spaCy dict). Run
# `./setup.sh` again after enabling TTS in Settings to download the assets.
TTS_ENABLED=$("$VENV_DIR/bin/python3" -c "
from whisper_voice.config import load_config
print('true' if load_config().tts.enabled else 'false')
" 2>/dev/null || echo "false")

# espeak-ng is tiny and useful beyond TTS; install regardless so enabling TTS
# later does not require another Homebrew run.
if ! brew list espeak-ng &>/dev/null 2>&1; then
    brew install espeak-ng -q 2>/dev/null || log_warn "espeak-ng install failed (TTS may not work)"
fi

if [ "$TTS_ENABLED" = "true" ]; then
    # Skip the spaCy download when the model is already available; on re-runs it
    # otherwise re-downloads unconditionally even though pip already has it.
    if ! "$VENV_DIR/bin/python3" -c "import en_core_web_sm" 2>/dev/null; then
        "$VENV_DIR/bin/python3" -m spacy download en_core_web_sm -q 2>/dev/null \
            || log_warn "spacy model download failed (TTS may not work)"
    fi

    if HF_HUB_CACHE="$MODEL_DIR" HF_HUB_DISABLE_TELEMETRY=1 "$VENV_DIR/bin/python3" -c "
from kokoro_mlx import KokoroTTS
KokoroTTS.from_pretrained('mlx-community/Kokoro-82M-bf16')
" 2>/dev/null; then
        log_ok "Kokoro TTS model"
    else
        log_warn "Kokoro download failed (will retry on first use)"
    fi
else
    log_info "Text-to-speech is off. Turn it on in Settings -> Voice to download Kokoro (~170 MB)."
fi

# ============================================================================
# Build Swift UI
# ============================================================================

log_step "Building UI..."

SWIFT_UI_DIR="$SCRIPT_DIR/LocalWhisperUI"
SWIFT_UI_DEST="$HOME/.whisper/LocalWhisperUI.app"

if [[ -d "$SWIFT_UI_DIR" ]]; then
    if ! command -v swift &> /dev/null; then
        log_warn "Swift not found. Service will run headless (rebuild later: wh build)"
    else
        cd "$SWIFT_UI_DIR"

        SWIFT_BUILD_LOG=$(mktemp)
        if swift build -c release >"$SWIFT_BUILD_LOG" 2>&1; then
            # Surface compiler warnings even on success so they don't silently pile up.
            if grep -iq "warning:" "$SWIFT_BUILD_LOG"; then
                log_warn "Swift build produced warnings:"
                grep -i "warning:" "$SWIFT_BUILD_LOG" >&2 || true
            fi
            rm -f "$SWIFT_BUILD_LOG"
            SWIFT_BIN="$SWIFT_UI_DIR/.build/release/LocalWhisperUI"
            if [[ -f "$SWIFT_BIN" ]]; then
                rm -rf "$SWIFT_UI_DEST"
                APP_MACOS="$SWIFT_UI_DEST/Contents/MacOS"
                APP_RES="$SWIFT_UI_DEST/Contents/Resources"
                mkdir -p "$APP_MACOS" "$APP_RES"
                cp "$SWIFT_BIN" "$APP_MACOS/LocalWhisperUI"

                cat > "$SWIFT_UI_DEST/Contents/Info.plist" <<'PLIST'
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
    <string>1.4.1</string>
    <key>CFBundleShortVersionString</key>
    <string>1.4.1</string>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
</dict>
</plist>
PLIST

                cp "$SCRIPT_DIR/src/whisper_voice/assets/LocalWhisper.icns" "$SWIFT_UI_DEST/Contents/Resources/AppIcon.icns"
                log_ok "LocalWhisperUI built"
            else
                log_warn "Build produced no binary. Service will run headless."
            fi
        else
            log_warn "Swift build failed (requires macOS 26+ SDK). Service will run headless."
            log_info "Build log: $SWIFT_BUILD_LOG"
        fi

        cd "$SCRIPT_DIR"
    fi
else
    log_warn "LocalWhisperUI source not found. Service will run headless."
fi

# ============================================================================
# LaunchAgent
# ============================================================================

log_step "Installing service..."

# Legacy cleanup
osascript -e 'tell application "System Events" to delete (login items whose name is "Local Whisper")' 2>/dev/null || true
if [[ -f "$HOME/Library/LaunchAgents/info.gabrimatic.local-whisper.plist" ]]; then
    launchctl unload "$HOME/Library/LaunchAgents/info.gabrimatic.local-whisper.plist" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/info.gabrimatic.local-whisper.plist"
fi

# Stop any running instance
if [[ -f "$HOME/Library/LaunchAgents/com.local-whisper.plist" ]]; then
    launchctl unload "$HOME/Library/LaunchAgents/com.local-whisper.plist" 2>/dev/null || true
fi
pkill -f "wh _run" 2>/dev/null || true
pkill -f "whisper_voice" 2>/dev/null || true
pkill -x "Local Whisper" 2>/dev/null || true
pkill -x "LocalWhisperUI" 2>/dev/null || true
sleep 1

# Clean stale runtime files
rm -f "$HOME/.whisper/service.lock" "$HOME/.whisper/ipc.sock" "$HOME/.whisper/cmd.sock"

WH_BIN="$VENV_DIR/bin/wh"
if [[ ! -f "$WH_BIN" ]]; then
    fail "wh binary not found at $WH_BIN"
fi

PLIST_PATH="$HOME/Library/LaunchAgents/com.local-whisper.plist"
LOG_PATH="$HOME/.whisper/service.log"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.whisper"

log_ok "Service prepared"

# ============================================================================
# Permissions
# ============================================================================
# Both permissions are requested from the venv Python binary (the same one the
# LaunchAgent runs). macOS TCC grants apply per-binary path, so granting here
# means the service inherits the same access.
#
# The permission dialogs will show "Python" as the app name. That's expected.

log_step "Checking permissions..."
log_info "macOS will show \"Python\" in permission dialogs. That is the correct app."

# Request Accessibility (opens System Settings if not granted)
AX_OK=$("$VENV_DIR/bin/python3" -c "
from whisper_voice.utils import check_accessibility_trusted, request_accessibility_permission
if check_accessibility_trusted():
    print('yes')
else:
    request_accessibility_permission()
    print('no')
" 2>/dev/null) || AX_OK="no"

if [ "$AX_OK" = "yes" ]; then
    log_ok "Accessibility"
fi

# Request Microphone (shows system dialog if not determined, may block up to 30s)
log_info "If a microphone dialog appears, click Allow."
MIC_OK=$(check_mic) || MIC_OK="no"

if [ "$MIC_OK" = "yes" ]; then
    log_ok "Microphone"
fi

# If either is missing, enter verification loop
if [ "$AX_OK" != "yes" ] || [ "$MIC_OK" != "yes" ]; then
    echo ""
    [ "$AX_OK" != "yes" ] && log_warn "Accessibility: not yet granted"
    [ "$MIC_OK" != "yes" ] && log_warn "Microphone: not yet granted"
    echo ""
    log_info "Grant the permissions above in System Settings, then press Enter."
    log_info "Look for \"Python\" in the permission lists."
    [ "$AX_OK" != "yes" ] && log_info "  → Privacy & Security → Accessibility"
    [ "$MIC_OK" != "yes" ] && log_info "  → Privacy & Security → Microphone"

    ATTEMPT=0
    while [ $ATTEMPT -lt 3 ]; do
        echo ""
        read -r -p "  Press Enter to verify... "

        AX_OK=$(check_ax) || AX_OK="no"
        MIC_OK=$(check_mic) || MIC_OK="no"

        if [ "$AX_OK" = "yes" ] && [ "$MIC_OK" = "yes" ]; then
            break
        fi

        ATTEMPT=$((ATTEMPT + 1))

        [ "$AX_OK" != "yes" ] && log_warn "Accessibility: still not granted"
        [ "$MIC_OK" != "yes" ] && log_warn "Microphone: still not granted"

        if [ $ATTEMPT -ge 3 ]; then
            echo ""
            log_warn "Continuing without full permissions. The service may not work."
            log_info "Grant permissions later, then run: wh restart"
        fi
    done
fi

PERMISSIONS_OK=false
if [ "$AX_OK" = "yes" ] && [ "$MIC_OK" = "yes" ]; then
    PERMISSIONS_OK=true
    log_ok "All permissions granted"
fi

# ============================================================================
# Start the service
# ============================================================================

log_step "Starting service..."

# Rewrite plist with RunAtLoad=true for login auto-start
write_plist "true"
launchctl load "$PLIST_PATH" 2>/dev/null || true
launchctl start com.local-whisper 2>/dev/null || true
sleep 2

if pgrep -f "wh _run" > /dev/null 2>&1; then
    _SVC_PID=$(pgrep -f "wh _run" | head -1)
    log_ok "Service running (pid $_SVC_PID)"
else
    log_warn "Service not yet running. Check: wh log"
fi

# Shell alias
WH_ALIAS="alias wh='$VENV_DIR/bin/wh'"
touch "$HOME/.zshrc"

for RC in "$HOME/.zshrc" "$HOME/.bashrc"; do
    if [[ -f "$RC" ]] && ! grep -q "alias wh=" "$RC" 2>/dev/null; then
        echo "" >> "$RC"
        echo "# Local Whisper CLI" >> "$RC"
        echo "$WH_ALIAS" >> "$RC"
    fi
done

if command -v fish &>/dev/null && [[ -d "$HOME/.config/fish" ]]; then
    FISH_CONFIG="$HOME/.config/fish/config.fish"
    if ! grep -q "alias wh=" "$FISH_CONFIG" 2>/dev/null; then
        log_info "Fish: add manually: alias wh='$VENV_DIR/bin/wh'"
    fi
fi

# ============================================================================
# Done
# ============================================================================

echo ""
if [ "$PERMISSIONS_OK" = "true" ]; then
    echo -e "${GREEN}${BOLD}  ✓ Setup complete!${NC}"
else
    echo -e "${YELLOW}${BOLD}  ⚠ Setup complete (permissions pending)${NC}"
    echo -e "  ${DIM}Grant missing permissions in System Settings, then: ${NC}${BOLD}wh restart${NC}"
fi
echo ""
echo -e "  ${BOLD}Usage:${NC} Double-tap ${YELLOW}Right Option (⌥)${NC} → speak → tap to stop"
echo -e "  ${BOLD}TTS:${NC}   Select text → ${YELLOW}⌥T${NC} to hear it aloud"
echo -e "  ${BOLD}CLI:${NC}   ${DIM}wh${NC} (manage service)  ${DIM}wh whisper \"text\"${NC} (speak)"
echo ""
echo -e "  ${DIM}Starts automatically at login. Run 'wh' in a new terminal.${NC}"
echo ""

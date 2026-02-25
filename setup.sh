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

print_header() {
    echo ""
    echo -e "${BOLD}╭────────────────────────────────────────╮${NC}"
    echo -e "${BOLD}│${NC}  ${CYAN}Local Whisper${NC} · Setup               ${BOLD}│${NC}"
    echo -e "${BOLD}│${NC}  ${DIM}Voice Transcription + Grammar Fix${NC}     ${BOLD}│${NC}"
    echo -e "${BOLD}╰────────────────────────────────────────╯${NC}"
    echo ""
}

log_step() {
    echo -e "${CYAN}▶${NC} $1"
}

log_ok() {
    echo -e "  ${GREEN}✓${NC} $1"
}

log_warn() {
    echo -e "  ${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "  ${RED}✗${NC} $1"
}

log_info() {
    echo -e "  ${DIM}›${NC} $1"
}

fail() {
    echo ""
    log_error "$1"
    echo ""
    echo -e "${RED}Setup failed.${NC} Please fix the issue above and run this script again."
    echo ""
    exit 1
}

# ============================================================================
# Pre-flight Checks
# ============================================================================

print_header

# Check macOS
log_step "Checking system requirements..."

if [[ "$OSTYPE" != "darwin"* ]]; then
    fail "This app only works on macOS. Detected: $OSTYPE"
fi
log_ok "macOS detected"

# Check architecture
ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]]; then
    log_ok "Apple Silicon (M1/M2/M3/M4) detected"
elif [[ "$ARCH" == "x86_64" ]]; then
    fail "Intel Mac detected. Local Whisper requires Apple Silicon (M1 or later)."
else
    fail "Unknown architecture: $ARCH"
fi

# Check macOS version (need macOS 26+ for Apple Intelligence Foundation Models)
MACOS_VERSION=$(sw_vers -productVersion)
MACOS_MAJOR=$(echo "$MACOS_VERSION" | cut -d'.' -f1)
if [[ "$MACOS_MAJOR" -lt 26 ]]; then
    log_warn "macOS $MACOS_VERSION detected"
    log_warn "Apple Intelligence Foundation Models require macOS 26 (Tahoe) or later"
    log_warn "Grammar correction will not work until you upgrade"
else
    log_ok "macOS $MACOS_VERSION (supports Apple Intelligence)"
fi

# ============================================================================
# Homebrew
# ============================================================================

echo ""
log_step "Checking Homebrew..."

if ! command -v brew &> /dev/null; then
    log_warn "Homebrew not found. Installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || \
        fail "Failed to install Homebrew. Visit https://brew.sh for manual installation."

    # Add brew to PATH for this session
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi
log_ok "Homebrew ready"

# ============================================================================
# Python 3
# ============================================================================

echo ""
log_step "Checking Python 3..."

if ! command -v python3 &> /dev/null; then
    log_warn "Python 3 not found. Installing via Homebrew..."
    brew install python3 || fail "Failed to install Python 3"
fi

PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f2)

if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 11 ]]; then
    fail "Python 3.11+ required. Found: $PYTHON_VERSION"
fi
log_ok "Python $PYTHON_VERSION"

# ============================================================================
# Virtual Environment
# ============================================================================

echo ""
log_step "Setting up Python virtual environment..."

VENV_DIR="$SCRIPT_DIR/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR" || fail "Failed to create virtual environment"
    log_ok "Created virtual environment"
else
    log_ok "Virtual environment exists"
fi

# Activate venv
source "$VENV_DIR/bin/activate" || fail "Failed to activate virtual environment"
log_ok "Activated virtual environment"

# ============================================================================
# Install Package (editable mode)
# ============================================================================

echo ""
log_step "Installing local-whisper package..."

pip install --upgrade pip -q || fail "Failed to upgrade pip"
pip install -e "$SCRIPT_DIR" || fail "Failed to install package"
log_ok "Package installed (editable mode)"

# ============================================================================
# Write default configuration
# ============================================================================

echo ""
log_step "Writing default configuration..."
mkdir -p "$HOME/.whisper"
"$VENV_DIR/bin/python" -c "
from whisper_voice.config import DEFAULT_CONFIG
from pathlib import Path
config_path = Path.home() / '.whisper' / 'config.toml'
config_path.write_text(DEFAULT_CONFIG, encoding='utf-8')
print(f'Config written to {config_path}')
" && log_ok "Config written to ~/.whisper/config.toml" || log_warn "Could not write config"

# ============================================================================
# Pre-download and warm up Qwen3-ASR model (default transcription engine)
# ============================================================================

echo ""
log_step "Pre-downloading Qwen3-ASR model..."
log_info "Downloads and caches the speech model to ~/.cache/huggingface/."
log_info "This only happens once."

if "$VENV_DIR/bin/python3" -c "
from mlx_audio.stt.utils import load_model
load_model('mlx-community/Qwen3-ASR-1.7B-bf16')
" 2>/dev/null; then
    log_ok "Qwen3-ASR model downloaded"
else
    log_warn "Qwen3-ASR model download failed - first use may download automatically"
fi

echo ""
log_step "Warming up Qwen3-ASR model..."
log_info "Compiling the MLX compute graph so first transcription is fast."
log_info "This may take 60-120 seconds. Only happens once."

if "$VENV_DIR/bin/python3" -c "
import numpy as np
import tempfile
import soundfile as sf
from mlx_audio.stt.utils import load_model

model = load_model('mlx-community/Qwen3-ASR-1.7B-bf16')
silence = np.zeros(8000, dtype=np.float32)
with tempfile.NamedTemporaryFile(suffix='.wav', delete=True) as tmp:
    sf.write(tmp.name, silence, 16000)
    model.generate(tmp.name, max_tokens=1)
" 2>/dev/null; then
    log_ok "Qwen3-ASR model warmed up and ready"
else
    log_warn "Model warm-up failed - first transcription may be slower"
fi

# ============================================================================
# WhisperKit CLI (alternative transcription engine)
# WhisperKit is not installed by default. If you want to use it, install
# manually: brew install whisperkit-cli
# Then switch engines via: wh engine whisperkit
# ============================================================================

# ============================================================================
# Ollama Model Setup (if Ollama is installed)
# ============================================================================

echo ""
log_step "Checking Ollama..."

OLLAMA_MODEL="gemma3:4b-it-qat"

if command -v ollama &> /dev/null; then
    log_ok "Ollama installed"

    # Check if model is already downloaded
    if ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"; then
        log_ok "Model $OLLAMA_MODEL already downloaded"
    else
        log_info "Downloading grammar model: $OLLAMA_MODEL"
        log_info "This may take a few minutes..."
        if ollama pull "$OLLAMA_MODEL" 2>&1 | grep -E "pulling|success|already"; then
            log_ok "Model $OLLAMA_MODEL ready"
        else
            log_warn "Failed to download model (you can do this later with: ollama pull $OLLAMA_MODEL)"
        fi
    fi
else
    log_info "Ollama not installed (optional - download from https://ollama.ai)"
fi

# ============================================================================
# LM Studio Model Setup (if LM Studio CLI is installed)
# ============================================================================

echo ""
log_step "Checking LM Studio..."

LMSTUDIO_MODEL="google/gemma-3-4b"

if command -v lms &> /dev/null; then
    log_ok "LM Studio CLI installed"

    # Check if model is already downloaded
    if lms ls 2>/dev/null | grep -q "gemma-3-4b"; then
        log_ok "Model $LMSTUDIO_MODEL already downloaded"
    else
        log_info "Downloading grammar model: $LMSTUDIO_MODEL"
        log_info "This may take a few minutes..."
        if lms get "$LMSTUDIO_MODEL" -y --quiet 2>/dev/null; then
            log_ok "Model $LMSTUDIO_MODEL ready"
        else
            log_warn "Failed to download model (you can do this later in LM Studio)"
        fi
    fi
else
    log_info "LM Studio not installed (optional - download from https://lmstudio.ai)"
fi

# ============================================================================
# Build Apple Intelligence CLI Helper
# ============================================================================

echo ""
log_step "Building Apple Intelligence CLI helper..."
log_info "This is a one-time build. The CLI is called automatically by the app."

SWIFT_CLI_DIR="$SCRIPT_DIR/src/whisper_voice/backends/apple_intelligence/cli"

if [[ -d "$SWIFT_CLI_DIR" ]]; then
    # Check if Xcode command line tools are available
    if ! command -v swift &> /dev/null; then
        log_warn "Swift not found. Installing Xcode Command Line Tools..."
        xcode-select --install 2>/dev/null || true
        log_warn "Please complete the Xcode Command Line Tools installation and run this script again"
        fail "Swift compiler required for Apple Intelligence CLI"
    fi

    # Build the Swift CLI in release mode
    cd "$SWIFT_CLI_DIR"

    swift build -c release 2>&1
    if [[ -f "$SWIFT_CLI_DIR/.build/release/apple-ai-cli" ]]; then
        log_ok "Apple Intelligence CLI built successfully"
        log_info "Binary: $SWIFT_CLI_DIR/.build/release/apple-ai-cli"
    else
        log_warn "Failed to build Apple Intelligence CLI"
        log_warn "This requires macOS 26+ and Xcode 26+"
        log_warn "Grammar correction will not be available"
    fi

    cd "$SCRIPT_DIR"
else
    log_warn "Apple Intelligence CLI source not found at $SWIFT_CLI_DIR"
fi

# ============================================================================
# Build LocalWhisperUI (Swift menu bar app)
# ============================================================================

echo ""
log_step "Building LocalWhisperUI..."
log_info "This is a one-time build. The app is launched automatically by the service."

SWIFT_UI_DIR="$SCRIPT_DIR/LocalWhisperUI"
SWIFT_UI_DEST="$HOME/.whisper/LocalWhisperUI.app"

if [[ -d "$SWIFT_UI_DIR" ]]; then
    if ! command -v swift &> /dev/null; then
        log_warn "Swift not found — skipping UI build"
        log_info "The service will run headless until you rebuild with: wh build"
    else
        cd "$SWIFT_UI_DIR"

        swift build -c release 2>&1
        SWIFT_BIN="$SWIFT_UI_DIR/.build/release/LocalWhisperUI"
        if [[ -f "$SWIFT_BIN" ]]; then
            # Assemble the .app bundle
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
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
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
PLIST

            log_ok "LocalWhisperUI built and installed at $SWIFT_UI_DEST"
        else
            log_warn "LocalWhisperUI build failed — service will run headless"
            log_warn "Requires macOS 26+ SDK and Xcode 26+"
        fi

        cd "$SCRIPT_DIR"
    fi
else
    log_warn "LocalWhisperUI source not found at $SWIFT_UI_DIR — skipping"
fi

# ============================================================================
# Install as LaunchAgent
# ============================================================================

echo ""
log_step "Installing as LaunchAgent..."

# Legacy cleanup: remove old Login Item and old LaunchAgent if present
osascript -e 'tell application "System Events" to delete (login items whose name is "Local Whisper")' 2>/dev/null || true
if [[ -f "$HOME/Library/LaunchAgents/info.gabrimatic.local-whisper.plist" ]]; then
    launchctl unload "$HOME/Library/LaunchAgents/info.gabrimatic.local-whisper.plist" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/info.gabrimatic.local-whisper.plist"
    log_ok "Removed legacy LaunchAgent"
fi

# Kill any existing instance
pkill -f "wh _run" 2>/dev/null || true
pkill -f "whisper_voice" 2>/dev/null || true
pkill -x "Local Whisper" 2>/dev/null || true
rm -f "$HOME/.whisper/service.lock"
sleep 1

WH_BIN="$VENV_DIR/bin/wh"

# Verify wh binary was created by pip install
if [[ ! -f "$WH_BIN" ]]; then
    fail "wh binary not found at $WH_BIN - package install may have failed"
fi

# Write LaunchAgent plist
PLIST_PATH="$HOME/Library/LaunchAgents/com.local-whisper.plist"
LOG_PATH="$HOME/.whisper/service.log"
mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$HOME/.whisper"

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
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$LOG_PATH</string>
    <key>StandardErrorPath</key>
    <string>$LOG_PATH</string>
</dict>
</plist>
PLIST_EOF

log_ok "LaunchAgent plist written"

# Unload stale entry if any, then load fresh
launchctl unload "$PLIST_PATH" 2>/dev/null || true
if launchctl load "$PLIST_PATH" 2>/dev/null; then
    log_ok "LaunchAgent loaded (auto-start at login enabled)"
else
    log_warn "LaunchAgent load had a warning - continuing"
fi

# Start the service now
launchctl start com.local-whisper 2>/dev/null || true
sleep 2

# Show status
if pgrep -f "wh _run" > /dev/null 2>&1; then
    _SVC_PID=$(pgrep -f "wh _run" | head -1)
    log_ok "Service started (pid $_SVC_PID)"
else
    log_info "Service starting in background"
fi

# Request Accessibility permission.
# We call AXIsProcessTrustedWithOptions from the venv Python - the same executable
# the LaunchAgent uses. Granting here grants it for the service too.
echo ""
log_step "Requesting Accessibility permission..."
AX_ALREADY_GRANTED=$("$VENV_DIR/bin/python3" -c "
from whisper_voice.utils import check_accessibility_trusted, request_accessibility_permission
if check_accessibility_trusted():
    print('yes')
else:
    request_accessibility_permission()
    print('no')
" 2>/dev/null)

if [ "$AX_ALREADY_GRANTED" = "yes" ]; then
    log_ok "Already granted"
else
    log_warn "System Settings opened - grant Accessibility to Python/wh"
    log_info "System Settings → Privacy & Security → Accessibility → enable the entry"
    echo ""
    read -r -p "  Press Enter once you have granted access... "
    echo ""
    # Re-verify
    AX_NOW=$("$VENV_DIR/bin/python3" -c "
from whisper_voice.utils import check_accessibility_trusted
print('yes' if check_accessibility_trusted() else 'no')
" 2>/dev/null)
    if [ "$AX_NOW" = "yes" ]; then
        log_info "Restarting service with new Accessibility permission..."
        "$WH_BIN" restart 2>/dev/null || true
        sleep 2
        log_ok "Service restarted with Accessibility"
    else
        log_warn "Accessibility not detected - hotkey may not work"
        log_info "Run 'wh restart' after granting Accessibility in System Settings"
    fi
fi

# Add wh alias to shell config if not already present
WH_ALIAS="alias wh='$VENV_DIR/bin/wh'"

# Always ensure .zshrc exists (macOS default shell is zsh)
touch "$HOME/.zshrc"

for RC in "$HOME/.zshrc" "$HOME/.bashrc"; do
    if [[ -f "$RC" ]] && ! grep -q "alias wh=" "$RC" 2>/dev/null; then
        echo "" >> "$RC"
        echo "# Local Whisper CLI" >> "$RC"
        echo "$WH_ALIAS" >> "$RC"
        log_ok "Added wh alias to $RC"
    fi
done

# Fish shell hint
if command -v fish &>/dev/null && [[ -d "$HOME/.config/fish" ]]; then
    FISH_CONFIG="$HOME/.config/fish/config.fish"
    if ! grep -q "alias wh=" "$FISH_CONFIG" 2>/dev/null; then
        log_info "Fish detected - add manually: alias wh='$VENV_DIR/bin/wh'"
    fi
fi

# ============================================================================
# Done
# ============================================================================

echo ""
echo -e "${GREEN}${BOLD}╭────────────────────────────────────────╮${NC}"
echo -e "${GREEN}${BOLD}│${NC}  ${GREEN}✓ Setup complete!${NC}                     ${GREEN}${BOLD}│${NC}"
echo -e "${GREEN}${BOLD}╰────────────────────────────────────────╯${NC}"
echo ""
echo -e "${BOLD}Transcription Engine:${NC}"
echo ""
echo -e "  ${CYAN}Qwen3-ASR${NC} (default):"
echo -e "     - On-device, Apple Silicon (MLX)"
echo -e "     - Model cached at ${DIM}~/.cache/huggingface/${NC}"
echo ""
echo -e "  ${CYAN}WhisperKit${NC} (alternative):"
echo -e "     - CoreML, Apple Silicon"
echo -e "     - Switch via ${DIM}wh engine${NC} or Settings"
echo ""
echo -e "${BOLD}Grammar Backends:${NC}"
echo ""
echo -e "  ${CYAN}Apple Intelligence${NC} (recommended):"
echo -e "     - macOS 26 (Tahoe) or later"
echo -e "     - Apple Silicon (M1/M2/M3/M4)"
echo -e "     - Enable in System Settings → Apple Intelligence & Siri"
echo ""
echo -e "  ${CYAN}Ollama${NC} (alternative):"
echo -e "     - Download from ${DIM}https://ollama.ai${NC}"
echo -e "     - Model auto-downloaded if Ollama was installed"
echo -e "     - Run: ${DIM}ollama serve${NC}"
echo ""
echo -e "  ${CYAN}LM Studio${NC} (alternative):"
echo -e "     - Download from ${DIM}https://lmstudio.ai${NC}"
echo -e "     - Model auto-downloaded if LM Studio CLI was installed"
echo -e "     - ${YELLOW}Developer → Start Server${NC} (required!)"
echo -e "     ${DIM}Note: Loading a model does NOT auto-start the server${NC}"
echo ""
echo -e "${BOLD}You're ready:${NC}"
echo ""
echo -e "  Double-tap ${YELLOW}Right Option (⌥)${NC} → speak → tap to stop → text copied to clipboard"
echo ""
echo -e "  ${DIM}Service starts automatically at login.${NC}"
echo -e "  ${DIM}Run 'wh' in a new terminal to manage the service.${NC}"
echo ""

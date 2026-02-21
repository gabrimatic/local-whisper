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
    fail "Intel Mac detected - Apple Intelligence requires Apple Silicon"
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
    if [[ "$ARCH" == "arm64" ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    else
        eval "$(/usr/local/bin/brew shellenv)"
    fi
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

if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 9 ]]; then
    fail "Python 3.9+ required. Found: $PYTHON_VERSION"
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
# WhisperKit CLI
# ============================================================================

echo ""
log_step "Checking WhisperKit CLI..."

if ! command -v whisperkit-cli &> /dev/null; then
    log_warn "WhisperKit CLI not found. Installing via Homebrew..."
    brew install whisperkit-cli || fail "Failed to install WhisperKit CLI. Try: brew tap argmaxinc/whisperkit && brew install whisperkit-cli"
fi
log_ok "WhisperKit CLI ready"

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
        if lms get "$LMSTUDIO_MODEL" -y --quiet 2>&1; then
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

    if swift build -c release 2>&1 | grep -v "^Building\|^Build complete"; then
        log_ok "Apple Intelligence CLI built successfully"
        log_info "Binary: $SWIFT_CLI_DIR/.build/release/apple-ai-cli"
    else
        if [[ -f "$SWIFT_CLI_DIR/.build/release/apple-ai-cli" ]]; then
            log_ok "Apple Intelligence CLI built successfully"
        else
            log_warn "Failed to build Apple Intelligence CLI"
            log_warn "This requires macOS 26+ and Xcode 26+"
            log_warn "Grammar correction will not be available"
        fi
    fi

    cd "$SCRIPT_DIR"
else
    log_warn "Apple Intelligence CLI source not found at $SWIFT_CLI_DIR"
fi

# ============================================================================
# Build .app bundle and install as Login Item
# ============================================================================

echo ""
log_step "Building app bundle..."

APP_BUNDLE="$SCRIPT_DIR/dist/Local Whisper.app"

VENV_DIR="$VENV_DIR" "$SCRIPT_DIR/scripts/build_app.sh" && \
    log_ok "App bundle built" || \
    log_warn "App bundle build failed - will use existing bundle if available"

echo ""
log_step "Installing as Login Item..."

# Kill any existing instance cleanly and wait for it to fully exit
pkill -x "Local Whisper" 2>/dev/null || true
pkill -f "whisper_voice" 2>/dev/null || true
rm -f /tmp/local-whisper.lock
sleep 2

if [[ -d "$APP_BUNDLE" ]]; then
    # Always copy fresh bundle to /Applications
    rm -rf "/Applications/Local Whisper.app"
    cp -r "$APP_BUNDLE" /Applications/ || fail "Could not install to /Applications"
    log_ok "Installed to /Applications/Local Whisper.app"

    TARGET_APP="/Applications/Local Whisper.app"

    # Add to Login Items (remove stale entry first)
    osascript -e "tell application \"System Events\" to delete (login items whose name is \"Local Whisper\")" 2>/dev/null || true
    osascript -e "tell application \"System Events\" to make login item at end with properties {path:\"$TARGET_APP\", hidden:true}" 2>/dev/null && \
        log_ok "Login Item set (starts automatically at login)" || \
        log_warn "Could not set Login Item - add manually: System Settings → General → Login Items"

    # Launch exactly one instance
    open "$TARGET_APP"
    log_ok "Local Whisper launched"
else
    fail "App bundle not found at $APP_BUNDLE - build failed"
fi

# ============================================================================
# Done
# ============================================================================

echo ""
echo -e "${GREEN}${BOLD}╭────────────────────────────────────────╮${NC}"
echo -e "${GREEN}${BOLD}│${NC}  ${GREEN}✓ Setup complete!${NC}                     ${GREEN}${BOLD}│${NC}"
echo -e "${GREEN}${BOLD}╰────────────────────────────────────────╯${NC}"
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
echo -e "${BOLD}Next steps:${NC}"
echo ""
echo -e "  1. ${CYAN}Grant Accessibility permission:${NC}"
echo -e "     System Settings → Privacy & Security → Accessibility"
echo -e "     Add: ${DIM}Local Whisper${NC} (or your terminal app)"
echo ""
echo -e "  2. ${CYAN}App is already running as a background service.${NC}"
echo -e "     It starts automatically at login. No need to run ${DIM}wh${NC} manually."
echo ""
echo -e "  3. ${CYAN}Configure grammar backend:${NC}"
echo -e "     Edit ${DIM}~/.whisper/config.toml${NC} and set ${DIM}[grammar] backend${NC}"
echo -e "     Then re-run ${DIM}./setup.sh${NC} to apply and restart."
echo ""
echo -e "  4. ${CYAN}Use it:${NC}"
echo -e "     Double-tap ${YELLOW}Right Option (⌥)${NC} → speak → tap to stop → text copied"
echo ""
echo -e "  5. ${CYAN}Manage:${NC}"
echo -e "     Login Items: ${DIM}System Settings → General → Login Items${NC}"
echo -e "     Quit: ${DIM}menu bar icon → Quit${NC}"
echo ""

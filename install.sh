#!/usr/bin/env bash
#
# One-command installer for Local Whisper.
# Installs the Homebrew formula, then runs the guided first-time setup.
#

set -euo pipefail

BOLD='\033[1m'
DIM='\033[2m'
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
fi

say() {
  echo -e "$1"
}

run() {
  if [[ "$DRY_RUN" == "true" ]]; then
    printf '  %s\n' "$*"
  else
    "$@"
  fi
}

fail() {
  say ""
  say "${RED}Install stopped.${NC} $1"
  exit 1
}

say ""
say "${BOLD}Local Whisper installer${NC}"
say "${DIM}Local dictation for macOS. Setup downloads models once, then speech stays on-device or localhost.${NC}"
say ""

if [[ "$(uname -s)" != "Darwin" ]]; then
  fail "Local Whisper's desktop service requires macOS."
fi

if [[ "$(uname -m)" != "arm64" ]]; then
  fail "Apple Silicon is required."
fi

say "${CYAN}1/3 Checking Homebrew${NC}"
if ! command -v brew >/dev/null 2>&1; then
  say "${DIM}Homebrew is needed to install and update Local Whisper.${NC}"
  if [[ "$DRY_RUN" == "true" ]]; then
    say "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
  else
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  fi
fi

if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

command -v brew >/dev/null 2>&1 || fail "Homebrew is installed but not on PATH. Open a new terminal and run this installer again."
say "${GREEN}Homebrew ready${NC}"

say ""
say "${CYAN}2/3 Installing Local Whisper${NC}"
run brew install gabrimatic/local-whisper/local-whisper

if [[ "$DRY_RUN" == "true" ]]; then
  WH_BIN="wh"
else
  WH_BIN="$(brew --prefix)/bin/wh"
  if [[ ! -x "$WH_BIN" ]]; then
    WH_BIN="$(command -v wh || true)"
  fi

  if [[ -z "$WH_BIN" || ! -x "$WH_BIN" ]]; then
    fail "Local Whisper installed, but the wh command was not found. Open a new terminal and run: wh setup"
  fi
fi
say "${GREEN}Local Whisper installed${NC}"

say ""
say "${CYAN}3/3 Running first-time setup${NC}"
say "${DIM}macOS may ask for Microphone and Accessibility access. Grant both so the hotkey can record from any app.${NC}"
run "$WH_BIN" setup

say ""
say "${GREEN}${BOLD}Done.${NC}"
say "Try it: double-tap Right Option, speak, then tap again to stop."

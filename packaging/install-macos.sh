#!/usr/bin/env bash
# Install Vigil for the current macOS user: venv, PATH, Applications, LaunchAgents.
# Prefer double-clicking install.command, which calls this script.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPPORT="${HOME}/Library/Application Support/vigil"
VENV="${SUPPORT}/venv"
SETUP="${1:-}"

pick_python() {
  local candidate
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  if command -v brew >/dev/null 2>&1; then
    if [[ -x "$(brew --prefix)/bin/python3" ]]; then
      if "$(brew --prefix)/bin/python3" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
        echo "$(brew --prefix)/bin/python3"
        return 0
      fi
    fi
  fi
  return 1
}

PYTHON="$(pick_python || true)"
if [[ -z "${PYTHON}" ]]; then
  echo "Python 3.11+ not found."
  echo "Install from https://www.python.org/downloads/ or: brew install python"
  exit 1
fi

echo "Using Python: $PYTHON"
echo "Installing into $VENV"
mkdir -p "$SUPPORT"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/pip" install "$ROOT"

if [[ ! -x "$VENV/bin/vigil" ]]; then
  echo "Install finished but $VENV/bin/vigil is missing" >&2
  exit 1
fi

# So desktop hooks find vigil even before a new shell.
export PATH="$VENV/bin:$PATH"
"$VENV/bin/vigil" desktop

# Clear quarantine on our launchers when possible (unsigned local build).
if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "$HOME/Applications/Vigil.app" 2>/dev/null || true
  xattr -dr com.apple.quarantine "$HOME/Applications/Vigil Setup.app" 2>/dev/null || true
  xattr -dr com.apple.quarantine "$HOME/Applications/Vigil Tray.app" 2>/dev/null || true
fi

echo
echo "Install complete."
echo "Next: open a NEW terminal, then run:"
echo "  vigil setup"
echo "Or open ~/Applications/Vigil Setup.app (first time: right-click → Open)."
echo "If macOS blocks a script: System Settings → Privacy & Security → Open Anyway."

if [[ "${SETUP}" == "--setup" || "${SETUP}" == "-Setup" ]]; then
  echo
  echo "Launching first-run wizard..."
  "$VENV/bin/vigil" setup
fi

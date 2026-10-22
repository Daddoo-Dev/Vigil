#!/usr/bin/env bash
# Install Vigil for the current user: pipx or a venv, example config, monthly timer, apps launcher, tray autostart.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

if command -v pipx >/dev/null 2>&1; then
  if pipx list --short 2>/dev/null | awk '{print $1}' | grep -qx vigil; then
    echo "reinstalling vigil with pipx"
    pipx install --force "$ROOT"
  else
    echo "installing vigil with pipx"
    pipx install "$ROOT"
  fi
else
  VENV="${XDG_DATA_HOME:-$HOME/.local/share}/vigil/venv"
  echo "pipx not found; installing into $VENV"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install "$ROOT"
  mkdir -p "$HOME/.local/bin"
  ln -sfn "$VENV/bin/vigil" "$HOME/.local/bin/vigil"
  echo "linked $HOME/.local/bin/vigil"
fi

if command -v vigil >/dev/null 2>&1; then
  VIGIL_BIN="$(command -v vigil)"
elif [[ -x "$HOME/.local/bin/vigil" ]]; then
  VIGIL_BIN="$HOME/.local/bin/vigil"
else
  echo "vigil was installed but is not on PATH. Add \$HOME/.local/bin to PATH and run this script again." >&2
  exit 1
fi
echo "using $VIGIL_BIN"

mkdir -p "$UNIT_DIR" "$AUTOSTART_DIR" "$APPLICATIONS_DIR"

echo "done installing $VIGIL_BIN"
echo "Next: run the first-run wizard"
echo "  vigil setup"
echo "(Or just: vigil)"
echo "That creates config, lets you pick projects, and can run the first scan."

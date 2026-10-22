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

"$VIGIL_BIN" init
"$VIGIL_BIN" desktop

mkdir -p "$UNIT_DIR" "$AUTOSTART_DIR" "$APPLICATIONS_DIR"
sed "s|@VIGIL@|${VIGIL_BIN}|g" "$ROOT/packaging/vigil-scan.service" > "$UNIT_DIR/vigil-scan.service"
cp "$ROOT/packaging/vigil-scan.timer" "$UNIT_DIR/vigil-scan.timer"
sed "s|@VIGIL@|${VIGIL_BIN}|g" "$ROOT/packaging/vigil.desktop" > "$APPLICATIONS_DIR/vigil.desktop"
sed "s|@VIGIL@|${VIGIL_BIN}|g" "$ROOT/packaging/vigil-tray.desktop" > "$AUTOSTART_DIR/vigil-tray.desktop"
echo "installed systemd user units in $UNIT_DIR"
echo "installed apps launcher $APPLICATIONS_DIR/vigil.desktop"
echo "installed tray autostart $AUTOSTART_DIR/vigil-tray.desktop"

systemctl --user daemon-reload
systemctl --user enable --now vigil-scan.timer
echo "enabled vigil-scan.timer"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

echo "done."
echo "Search for Vigil in the apps grid to open the latest report."
echo "For the top-bar icon: sudo dnf install gnome-shell-extension-appindicator"
echo "Then log out and back in, or run: vigil tray"

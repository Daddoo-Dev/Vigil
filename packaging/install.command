#!/bin/bash
# Double-click in Finder. Runs the macOS installer in Terminal.
cd "$(dirname "$0")"
chmod +x ./install-macos.sh 2>/dev/null || true
./install-macos.sh "$@"
echo
read -r -p "Press Enter to close…"

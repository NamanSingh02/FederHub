#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$ROOT/client/node_modules/.bin/electron" ] && [ ! -f "$ROOT/client/node_modules/.bin/electron.cmd" ]; then
  echo "[ERROR] Electron is not installed in client/node_modules."
  echo "Run ./setup_mac_dependencies.command first, or:"
  echo "  cd \"$ROOT/client\""
  echo "  npm install --include=dev"
  read -r -p "Press Enter to close..."
  exit 1
fi

osascript <<EOF
tell application "Terminal"
  do script "cd '$ROOT/client' && npm start"
  activate
end tell
EOF

echo "FederHub client launched in a separate Terminal window."
read -r -p "Press Enter to close..."

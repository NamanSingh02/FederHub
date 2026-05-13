#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Starting FederHub services from:"
echo "$ROOT"
echo

osascript <<EOF
tell application "Terminal"
  do script "cd '$ROOT/federated-engine' && python3 grpc_server.py"
  do script "cd '$ROOT/backend' && python3 -m uvicorn app.main:app --reload"
  do script "cd '$ROOT/frontend' && npm start"
  activate
end tell
EOF

echo
echo "FederHub services were launched in separate Terminal windows:"
echo "  - Gamma gRPC server"
echo "  - Backend API (http://localhost:8000)"
echo "  - Frontend (http://localhost:3000)"
echo
echo "The desktop client is not launched by default."
echo "Start it separately with ./run_client_mac.command when ready."
echo
echo "If any service fails, check that Terminal window for dependency or environment errors."

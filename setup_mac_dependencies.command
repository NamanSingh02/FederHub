#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "FederHub macOS setup starting from:"
echo "$ROOT"
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 was not found in PATH."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] npm was not found in PATH."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] Docker was not found in PATH."
  exit 1
fi

echo "[1/6] Installing backend Python dependencies..."
cd "$ROOT/backend"
python3 -m pip install -r requirements.txt

echo
echo "[2/6] Installing federated-engine Python dependencies..."
cd "$ROOT/federated-engine"
python3 -m pip install -r requirements.txt

echo
echo "[3/6] Installing client Python dependencies..."
cd "$ROOT/client"
python3 -m pip install -r requirements.txt

echo
echo "[4/6] Installing frontend Node dependencies..."
cd "$ROOT/frontend"
npm install --include=dev

echo
echo "[5/6] Installing client Node dependencies..."
cd "$ROOT/client"
npm install --include=dev

echo
echo "[6/6] Building the FederHub client Docker image..."
cd "$ROOT"
docker build -t federhub-beta-trainer -f client/Dockerfile .

echo
echo "FederHub macOS setup completed successfully."
echo "Next step:"
echo "  1. run ./run_all_services_mac.command"
echo "  2. run ./run_client_mac.command when you want the desktop client"

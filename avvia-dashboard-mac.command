#!/bin/zsh

set -e

SCRIPT_DIR="${0:A:h}"
VENV_DIR="$SCRIPT_DIR/.venv"

cd "$SCRIPT_DIR"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Preparazione iniziale della dashboard..."
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$VENV_DIR/bin/python" -m pip install -r requirements.txt
fi

if [[ ! -f "$SCRIPT_DIR/web-build/dashboard.html" ]]; then
  if ! command -v "${NODE_BIN:-node}" >/dev/null 2>&1; then
    echo "Prima compilazione richiesta: installa Node.js e avvia node scripts/build-web.cjs nella cartella del progetto."
    exit 1
  fi
  "${NODE_BIN:-node}" scripts/build-web.cjs
fi

echo "Avvio offline della dashboard. Per monitorare TWS usa --broker-mode monitor-readonly da Terminale."
exec "$VENV_DIR/bin/python" ibkr_paper_bridge.py

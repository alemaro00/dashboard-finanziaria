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

echo "Avvio della dashboard finanziaria..."
exec "$VENV_DIR/bin/python" ibkr_paper_bridge.py

"""Disposable UI fixture. No real banking credentials, data or broker connection."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from secure_storage import atomic_write

with tempfile.TemporaryDirectory(prefix="dashboard-splits-preview-") as directory:
    test_dir = Path(directory)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    records = [{"id": "fixture-" + kind, "recordType": kind, "amount": 1000, "currency": "EUR",
                "date": "2026-10-01", "bank": "Banca di prova", "description": "Bonifico prova " + kind}
               for kind in ("expense", "income")]
    state = {"monthName": "Ottobre", "year": 2026, "monthlyHistory": [], "monthDrafts": {}, "notes": [],
             "income": 0, "additionalIncome": 0, "fixedCosts": 0, "variableCosts": 0}
    atomic_write(test_dir / "dashboard-state.json", json.dumps({"state": state, "entry": {}}).encode())
    atomic_write(test_dir / "enable-banking/bank-transactions.json", json.dumps({"records": records}).encode())
    env = dict(os.environ, DASHBOARD_DATA_DIR=str(test_dir), DASHBOARD_RESOURCE_DIR=str(ROOT))
    print(f"Fixture UI: http://127.0.0.1:{port}/", flush=True)
    process = subprocess.Popen([sys.executable, str(ROOT / "ibkr_paper_bridge.py"), "--no-browser", "--broker-mode", "offline", "--http-port", str(port)], env=env)
    try:
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait(timeout=10)

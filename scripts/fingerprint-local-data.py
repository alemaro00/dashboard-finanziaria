"""Print only hashes/counts to verify preservation without exposing financial data."""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from secure_storage import read_bytes

directory = Path(sys.argv[1])
def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
document = json.loads(read_bytes(directory / "dashboard-state.json"))
state = document["state"]
result = {"monthlyHistoryHash": digest(state.get("monthlyHistory", [])),
          "notesHash": digest(state.get("notes", [])), "draftsHash": digest(state.get("monthDrafts", {})),
          "months": len(state.get("monthlyHistory", [])), "notes": len(state.get("notes", []))}
for name in ("enable-banking/bank-transactions.json", "Secrets/enable-banking.pem"):
    path = directory / name
    if path.exists(): result[name] = hashlib.sha256(read_bytes(path)).hexdigest()
print(json.dumps(result))

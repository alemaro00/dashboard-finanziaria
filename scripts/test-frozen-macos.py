"""Exercise the shipped runtime on loopback using only disposable fixtures."""
import http.client
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time

app = Path(sys.argv[1]).resolve()
runtime = app / "Contents/Resources/runtime"
with tempfile.TemporaryDirectory(prefix="dashboard-frozen-test-") as directory:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME", "OPENSSL_BIN"}}
    env.update({"PATH": "/usr/bin:/bin", "DASHBOARD_DATA_DIR": directory,
                "DASHBOARD_RESOURCE_DIR": str(runtime), "DASHBOARD_REQUIRE_ENCRYPTION": "1",
                "DASHBOARD_KEYCHAIN_HELPER": str(app / "Contents/MacOS/DashboardKeychain")})
    def request(method, path, document=None, token=None):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-CSRF-Token"] = token
        connection.request(method, path, body=json.dumps(document) if document is not None else None, headers=headers)
        response = connection.getresponse()
        result = response.status, response.read()
        connection.close()
        return result
    with open(Path(directory) / "test.log", "wb") as log:
        process = subprocess.Popen([str(runtime / "bridge/dashboard-bridge"), "--no-browser", "--broker-mode", "offline", "--http-port", str(port)], env=env, stdout=log, stderr=log)
        try:
            for _ in range(50):
                try:
                    if request("GET", "/api/health")[0] == 200:
                        break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError("Frozen runtime exited unexpectedly")
                    time.sleep(0.1)
            code, page = request("GET", "/")
            assert code == 200
            token = re.search(rb'name="csrf-token" content="([^"]+)"', page)[1].decode()
            fixture = {"state": {"monthlyHistory": [{"monthName": "Fixture", "notes": [{"bankTransactionIds": ["fixture-id"], "category": "Costo Fisso"}]}]}, "entry": {"label": "fixture"}}
            assert request("POST", "/api/state", fixture, token)[0] == 200
            raw = (Path(directory) / "dashboard-state.json").read_bytes()
            assert raw.startswith(b"DFB1\n") and b"fixture-id" not in raw
            assert json.loads(request("GET", "/api/state")[1])["state"] == fixture["state"]
            password = "temporary test fixture password"
            code, archive = request("POST", "/api/backup/export", {"password": password}, token)
            assert code == 200 and b"fixture-id" not in archive
            restore = {"password": "incorrect fixture password", "archive": json.loads(archive), "confirmReplace": True}
            assert request("POST", "/api/backup/import", restore, token)[0] == 400
            restore["password"] = password
            assert request("POST", "/api/backup/import", restore, token)[0] == 200
            assert (Path(directory) / "dashboard-state.json.bak").read_bytes().startswith(b"DFB1\n")
            assert json.loads(request("GET", "/api/state")[1])["state"] == fixture["state"]
            assert request("GET", "/privacy")[0] == 200
            assert request("GET", "/terms")[0] == 200
            print("Frozen runtime, Keychain encryption, backup roundtrip, wrong-password protection, legal pages: OK")
        finally:
            process.terminate()
            process.wait(timeout=10)

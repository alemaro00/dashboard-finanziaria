#!/usr/bin/env python3
"""Store a Wallet Premium API token in the macOS Keychain without echoing it."""
from __future__ import annotations

import getpass
import subprocess


SERVICE = "it.alemaro.dashboard-finanziaria.wallet-api"
ACCOUNT = "wallet-api"


def main() -> int:
    token = getpass.getpass("Incolla il token API Wallet Premium (non verrà mostrato): ").strip()
    if len(token) < 20 or len(token) > 4096 or any(character.isspace() for character in token):
        raise SystemExit("Token non valido: operazione annullata.")
    completed = subprocess.run(
        ["/usr/bin/security", "add-generic-password", "-U", "-a", ACCOUNT, "-s", SERVICE, "-w", token],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, timeout=10, check=False,
    )
    if completed.returncode:
        raise SystemExit("Impossibile salvare il token nel Portachiavi macOS.")
    print("Token Wallet salvato nel Portachiavi macOS. Riapri Dashboard Finanziaria.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

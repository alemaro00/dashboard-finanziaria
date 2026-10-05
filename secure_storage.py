"""Authenticated local storage and password-protected portable backups."""
from __future__ import annotations

import base64
import functools
import json
import os
from pathlib import Path
import subprocess
import tempfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"DFB1\n"
MAX_SIZE = 20 * 1024 * 1024


@functools.lru_cache(maxsize=1)
def local_key() -> bytes | None:
    helper = os.environ.get("DASHBOARD_KEYCHAIN_HELPER")
    if not helper:
        if os.environ.get("DASHBOARD_REQUIRE_ENCRYPTION") == "1":
            raise RuntimeError("Protezione dati non disponibile: riapri l'app installata")
        return None  # Source-only development, explicitly documented.
    result = subprocess.run([helper], capture_output=True, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError("Portachiavi non disponibile. Sblocca il Portachiavi e riapri la Dashboard")
    if len(result.stdout) != 32:
        raise RuntimeError("Chiave di protezione locale non valida")
    return result.stdout


def seal(raw: bytes) -> bytes:
    key = local_key()
    if key is None:
        return raw
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, raw, MAGIC)


def unseal(raw: bytes) -> bytes:
    if not raw.startswith(MAGIC):
        return raw  # Read existing data to migrate on first encrypted write.
    key = local_key()
    if key is None:
        raise RuntimeError("Apri questi dati con l'app sul Mac che li ha salvati, oppure importa un backup protetto")
    try:
        return AESGCM(key).decrypt(raw[5:17], raw[17:], MAGIC)
    except (InvalidTag, ValueError) as error:
        raise ValueError("Archivio protetto non leggibile o alterato: usa un backup valido") from error


def read_bytes(path: Path) -> bytes:
    if path.is_symlink() or path.stat().st_size > MAX_SIZE:
        raise ValueError("Archivio locale non sicuro o troppo grande")
    return unseal(path.read_bytes())


def atomic_write(path: Path, raw: bytes) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Percorso dati non sicuro")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    protected = seal(raw)
    fd, temporary = tempfile.mkstemp(prefix=".dashboard-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(protected)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def migrate(path: Path) -> None:
    if not path.exists():
        return
    raw = read_bytes(path)
    if local_key() is not None and not path.read_bytes().startswith(MAGIC):
        atomic_write(path, raw)


def _backup_key(password: object, salt: bytes) -> bytes:
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError("Scegli una password di almeno 12 caratteri (massimo 256)")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode("utf-8"))


def export_backup(document: dict, password: object) -> dict:
    salt, nonce = os.urandom(16), os.urandom(12)
    key = _backup_key(password, salt)
    raw = json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")
    encrypted = AESGCM(key).encrypt(nonce, raw, b"dashboard-portable-backup-v1")
    return {
        "format": "dashboard-encrypted-backup", "version": 1,
        "salt": base64.b64encode(salt).decode(), "nonce": base64.b64encode(nonce).decode(),
        "data": base64.b64encode(encrypted).decode(),
    }


def import_backup(archive: object, password: object) -> dict:
    if not isinstance(archive, dict) or archive.get("format") != "dashboard-encrypted-backup" or archive.get("version") != 1:
        raise ValueError("Seleziona un backup protetto della Dashboard")
    try:
        salt = base64.b64decode(archive["salt"], validate=True)
        nonce = base64.b64decode(archive["nonce"], validate=True)
        raw = base64.b64decode(archive["data"], validate=True)
        if len(salt) != 16 or len(nonce) != 12 or len(raw) > MAX_SIZE:
            raise ValueError("Dimensione backup non valida")
        key = _backup_key(password, salt)
        document = json.loads(AESGCM(key).decrypt(nonce, raw, b"dashboard-portable-backup-v1"))
    except (InvalidTag, KeyError, TypeError, ValueError) as error:
        raise ValueError("Password errata o backup alterato") from error
    if not isinstance(document, dict) or document.get("format") != "dashboard-auto-state":
        raise ValueError("Contenuto backup non valido")
    return document

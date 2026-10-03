"""Read-only Enable Banking connector for the single-user desktop app."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import secrets
import stat
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


API_ORIGIN = "https://api.enablebanking.com"
APPLICATION_ID = "832f4ca4-67b0-4054-8ebd-ed0518198791"
DEFAULT_REDIRECT_URL = "https://localhost:8766/api/enable-banking/callback"
DEFAULT_KEY_PATH = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Dashboard Finanziaria"
    / "Secrets"
    / "enable-banking.pem"
)
ALLOWED_METHODS = {"GET", "POST"}
ALLOWED_PREFIXES = ("/application", "/aspsps", "/auth", "/sessions", "/accounts/")


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")


def _atomic_json_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    path.chmod(0o600)


def _read_json(path: Path, fallback: object) -> object:
    if not path.is_file():
        return fallback
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Archivio Enable Banking troppo grande")
    return json.loads(path.read_text(encoding="utf-8"))


def _clean_text(value: object, maximum: int = 255) -> str:
    if isinstance(value, dict):
        value = value.get("name") or value.get("value") or value.get("text") or ""
    return str(value or "").strip()[:maximum]


def _amount(value: object) -> tuple[float, str] | None:
    if not isinstance(value, dict):
        return None
    raw = value.get("amount", value.get("value"))
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or abs(number) >= 100_000_000:
        return None
    currency = str(value.get("currency") or value.get("currency_code") or value.get("currencyCode") or "EUR").upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        currency = "EUR"
    return number, currency


def _account_identifier(account: dict) -> tuple[str, str]:
    candidates = [account.get("account_id"), *(account.get("all_account_ids") or [])]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        value = candidate.get("iban") or candidate.get("identification")
        if value:
            scheme = "IBAN" if candidate.get("iban") else str(candidate.get("scheme_name") or "ID")
            return str(value), scheme
    return "", ""


def normalize_account(account: dict, bank: str = "") -> dict | None:
    if not isinstance(account, dict):
        return None
    uid = str(account.get("uid") or "")
    if not uid or len(uid) > 200:
        return None
    identifier, scheme = _account_identifier(account)
    currency = str(account.get("currency") or "EUR").upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        currency = "EUR"
    name = _clean_text(account.get("name") or account.get("product") or bank or "Conto bancario", 100)
    masked = ("•••• " + identifier[-4:]) if identifier else ""
    return {
        "id": uid,
        "name": name,
        "bank": _clean_text(bank or account.get("account_servicer"), 100),
        "currency": currency,
        "identifierScheme": scheme,
        "identifierMasked": masked,
    }


def normalize_transaction(transaction: dict, account: dict) -> dict | None:
    if not isinstance(transaction, dict):
        return None
    parsed_amount = _amount(transaction.get("transaction_amount") or transaction.get("amount"))
    if parsed_amount is None:
        return None
    number, currency = parsed_amount
    indicator = str(transaction.get("credit_debit_indicator") or transaction.get("creditDebitIndicator") or "").upper()
    if indicator.startswith("DBIT") or indicator.startswith("DEBIT"):
        number = -abs(number)
    elif indicator.startswith("CRDT") or indicator.startswith("CREDIT"):
        number = abs(number)
    if number == 0:
        return None
    date = str(
        transaction.get("booking_date")
        or transaction.get("booking_date_time")
        or transaction.get("bookingDate")
        or transaction.get("value_date")
        or ""
    )[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return None
    parties = []
    for key in ("creditor", "debtor", "merchant"):
        value = transaction.get(key)
        if isinstance(value, dict):
            parties.append(_clean_text(value.get("name"), 120))
    remittance = transaction.get("remittance_information") or transaction.get("remittanceInformation")
    if isinstance(remittance, list):
        remittance = " · ".join(_clean_text(item, 120) for item in remittance)
    descriptions = [
        *parties,
        _clean_text(remittance, 180),
        _clean_text(transaction.get("additional_information") or transaction.get("additionalInformation"), 180),
        _clean_text(transaction.get("reference_number") or transaction.get("transaction_id"), 120),
    ]
    description = " · ".join(dict.fromkeys(item for item in descriptions if item))[:240] or "Movimento bancario"
    remote_id = str(transaction.get("transaction_id") or transaction.get("entry_reference") or "")
    identity = remote_id or "|".join((account["id"], date, f"{number:.8f}", currency, description))
    return {
        "id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "bankRecordId": remote_id,
        "recordType": "expense" if number < 0 else "income",
        "bank": account.get("bank") or account.get("name") or "Conto bancario",
        "accountId": account["id"],
        "accountName": account.get("name") or "Conto bancario",
        "date": date,
        "amount": round(abs(number), 2),
        "signedAmount": round(number, 2),
        "currency": currency,
        "description": description,
        "suggestedCategory": "Da classificare",
        "categoryId": "",
        "needsReview": number < 0,
        "source": "enable-banking",
        "editable": False,
    }


class EnableBankingClient:
    def __init__(self, key_path: Path = DEFAULT_KEY_PATH, application_id: str = APPLICATION_ID, timeout: int = 25):
        self.key_path = Path(key_path)
        self.application_id = str(application_id)
        self.timeout = timeout

    def _validate_key(self) -> None:
        if not self.key_path.is_file() or self.key_path.is_symlink():
            raise ValueError("Chiave privata Enable Banking non trovata")
        metadata = self.key_path.stat()
        if metadata.st_size < 1500 or metadata.st_size > 20_000:
            raise ValueError("Chiave privata Enable Banking non valida")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ValueError("La chiave Enable Banking deve essere accessibile soltanto al tuo utente")

    def jwt(self, now: int | None = None) -> str:
        self._validate_key()
        issued = int(time.time() if now is None else now)
        header = _b64url(_json_bytes({"alg": "RS256", "kid": self.application_id, "typ": "JWT"}))
        payload = _b64url(_json_bytes({"aud": "api.enablebanking.com", "exp": issued + 300, "iat": issued, "iss": "enablebanking.com"}))
        signing_input = f"{header}.{payload}".encode("ascii")
        completed = subprocess.run(
            ["/usr/bin/openssl", "dgst", "-sha256", "-sign", str(self.key_path)],
            input=signing_input,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0 or not completed.stdout:
            raise RuntimeError("Impossibile firmare la richiesta Enable Banking")
        return f"{header}.{payload}.{_b64url(completed.stdout)}"

    def request(self, method: str, path: str, query: dict | None = None, payload: object | None = None) -> dict:
        if method not in ALLOWED_METHODS or not path.startswith(ALLOWED_PREFIXES) or ".." in path:
            raise ValueError("Richiesta Enable Banking non ammessa")
        url = API_ORIGIN + path + (("?" + urlencode(query)) if query else "")
        body = None if payload is None else _json_bytes(payload)
        headers = {
            "Accept": "application/json",
            "Authorization": "Bearer " + self.jwt(),
            "User-Agent": "Dashboard-Finanziaria/1.12",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            with urlopen(Request(url, data=body, method=method, headers=headers), timeout=self.timeout) as response:
                raw = response.read(8_000_000)
        except HTTPError as error:
            detail = error.read(4096).decode("utf-8", "replace")
            if error.code == 401:
                raise RuntimeError("Chiave Enable Banking non riconosciuta o revocata") from error
            if error.code == 403:
                raise RuntimeError("Operazione non consentita dall'app Production Restricted") from error
            if error.code == 429:
                raise RuntimeError("Limite Enable Banking raggiunto. Riprova più tardi") from error
            raise RuntimeError(f"Enable Banking ha risposto {error.code}: {detail[:500]}") from error
        except (URLError, TimeoutError) as error:
            raise RuntimeError(f"Enable Banking non raggiungibile: {error}") from error
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("Risposta Enable Banking non valida") from error
        if not isinstance(parsed, dict):
            raise RuntimeError("Risposta Enable Banking non valida")
        return parsed

    def get(self, path: str, query: dict | None = None) -> dict:
        return self.request("GET", path, query=query)

    def post(self, path: str, payload: object) -> dict:
        return self.request("POST", path, payload=payload)


class EnableBankingService:
    def __init__(self, directory: Path, key_path: Path = DEFAULT_KEY_PATH):
        self.directory = Path(directory)
        self.data_path = self.directory / "bank-transactions.json"
        self.key_path = Path(key_path)
        self.lock = threading.RLock()
        self.sync_lock = threading.Lock()
        self.last_error = ""

    @staticmethod
    def _empty() -> dict:
        return {"sessions": [], "pending": None, "accounts": [], "records": [], "lastSync": None, "application": None}

    def _data(self) -> dict:
        value = _read_json(self.data_path, self._empty())
        if not isinstance(value, dict):
            raise ValueError("Archivio Enable Banking non valido")
        result = self._empty()
        result.update(value)
        return result

    def _save(self, value: dict) -> None:
        _atomic_json_write(self.data_path, value)

    def _client(self) -> EnableBankingClient:
        return EnableBankingClient(self.key_path)

    @staticmethod
    def _session_account_ids(session: dict) -> list[str]:
        identifiers: list[str] = []
        for item in (session.get("accounts_data") or session.get("accounts") or []):
            uid = item.get("uid") if isinstance(item, dict) else item
            uid = str(uid or "")
            if uid and len(uid) <= 200 and uid not in identifiers:
                identifiers.append(uid)
        return identifiers

    def _session_accounts(self, client: EnableBankingClient, session: dict, bank: str) -> list[dict]:
        accounts: list[dict] = []
        for uid in self._session_account_ids(session):
            details = client.get(f"/accounts/{uid}/details")
            details["uid"] = uid
            normalized = normalize_account(details, bank)
            if normalized:
                accounts.append(normalized)
        return accounts

    def configured(self) -> bool:
        try:
            self._client()._validate_key()
            return True
        except (OSError, ValueError):
            return False

    def snapshot(self) -> dict:
        with self.lock:
            data = self._data()
        records = data.get("records") if isinstance(data.get("records"), list) else []
        return {
            "provider": "Enable Banking",
            "configured": self.configured(),
            "readOnly": True,
            "writesEnabled": False,
            "environment": "PRODUCTION",
            "restricted": True,
            "application": data.get("application"),
            "authorizationRequired": not bool(data.get("sessions")),
            "authorizationPending": bool(data.get("pending")),
            "connectionCount": len(data.get("sessions", [])),
            "accounts": data.get("accounts", []),
            "records": records,
            "expenses": [item for item in records if item.get("recordType") == "expense"],
            "incomes": [item for item in records if item.get("recordType") == "income"],
            "lastSync": data.get("lastSync"),
            "syncing": self.sync_lock.locked(),
            "error": self.last_error,
        }

    def verify(self) -> dict:
        application = self._client().get("/application")
        safe = {
            "name": _clean_text(application.get("name"), 100),
            "environment": str(application.get("environment") or ""),
            "active": bool(application.get("active")),
            "services": [str(item)[:50] for item in (application.get("services") or [])],
            "countries": [str(item)[:2] for item in (application.get("countries") or [])],
        }
        with self.lock:
            data = self._data()
            data["application"] = safe
            self._save(data)
            self.last_error = ""
        return self.snapshot()

    def rename_record(self, record_id: object, custom_name: object) -> dict:
        identifier = str(record_id or "")
        name = _clean_text(custom_name, 120)
        if not re.fullmatch(r"[0-9a-f]{64}", identifier):
            raise ValueError("Movimento bancario non valido")
        if not name:
            raise ValueError("Inserisci un nome per il movimento")
        with self.lock:
            data = self._data()
            found = False
            for record in data.get("records", []):
                if isinstance(record, dict) and record.get("id") == identifier:
                    record["customName"] = name
                    found = True
                    break
            if not found:
                raise ValueError("Movimento bancario non trovato")
            self._save(data)
            self.last_error = ""
        return self.snapshot()

    def start_authorization(self, bank_name: object, country: object, valid_days: object = 90) -> dict:
        name = _clean_text(bank_name, 100)
        country_code = str(country or "").upper()
        if not name or not re.fullmatch(r"[A-Z]{2}", country_code):
            raise ValueError("Banca o Paese non validi")
        try:
            days = max(1, min(180, int(valid_days)))
        except (TypeError, ValueError):
            raise ValueError("Durata autorizzazione non valida") from None
        state = secrets.token_urlsafe(32)
        valid_until = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        response = self._client().post(
            "/auth",
            {
                "access": {"valid_until": valid_until, "balances": True, "transactions": True},
                "aspsp": {"name": name, "country": country_code},
                "state": state,
                "redirect_url": DEFAULT_REDIRECT_URL,
                "psu_type": "personal",
                "language": "it",
            },
        )
        url = str(response.get("url") or "")
        authorization_url = urlparse(url)
        hostname = (authorization_url.hostname or "").lower()
        if authorization_url.scheme != "https" or not (hostname == "enablebanking.com" or hostname.endswith(".enablebanking.com")):
            raise RuntimeError("Enable Banking non ha restituito un indirizzo di autorizzazione valido")
        with self.lock:
            data = self._data()
            data["pending"] = {"stateHash": hashlib.sha256(state.encode()).hexdigest(), "createdAt": time.time(), "bank": name, "country": country_code}
            self._save(data)
        return {"status": "authorization_required", "url": url}

    def complete_authorization(self, callback_url: object) -> dict:
        value = str(callback_url or "").strip()
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("Indirizzo di ritorno Enable Banking non valido")
        query = parse_qs(parsed.query)
        if query.get("error"):
            raise ValueError(_clean_text(query.get("error_description", query["error"])[0], 300))
        code = str((query.get("code") or [""])[0])
        state_value = str((query.get("state") or [""])[0])
        if not code or len(code) > 200 or not state_value:
            raise ValueError("Codice di autorizzazione mancante")
        with self.lock:
            data = self._data()
            pending = data.get("pending") if isinstance(data.get("pending"), dict) else {}
        expected = str(pending.get("stateHash") or "")
        if not expected or not secrets.compare_digest(expected, hashlib.sha256(state_value.encode()).hexdigest()):
            raise ValueError("Stato autorizzazione non valido")
        if time.time() - float(pending.get("createdAt") or 0) > 20 * 60:
            raise ValueError("Autorizzazione scaduta: avviala nuovamente")
        session = self._client().post("/sessions", {"code": code})
        session_id = str(session.get("session_id") or "")
        if not session_id or len(session_id) > 200:
            raise RuntimeError("Enable Banking non ha restituito una sessione valida")
        aspsp = session.get("aspsp") if isinstance(session.get("aspsp"), dict) else {}
        bank = _clean_text(aspsp.get("name") or pending.get("bank"), 100)
        accounts = self._session_accounts(self._client(), session, bank)
        with self.lock:
            data = self._data()
            sessions = [item for item in data.get("sessions", []) if isinstance(item, dict) and item.get("id") != session_id]
            sessions.append({"id": session_id, "bank": bank, "country": pending.get("country"), "accounts": accounts})
            data["sessions"], data["pending"] = sessions, None
            self._save(data)
        return self.sync()

    def _transactions(self, client: EnableBankingClient, account: dict, date_from: str) -> list[dict]:
        records: list[dict] = []
        continuation = None
        for _ in range(100):
            query = {"date_from": date_from}
            if continuation:
                query["continuation_key"] = continuation
            page = client.get(f"/accounts/{account['id']}/transactions", query)
            records.extend(item for item in (normalize_transaction(raw, account) for raw in (page.get("transactions") or [])) if item)
            continuation = page.get("continuation_key")
            if not continuation:
                return records
        raise RuntimeError("Paginazione Enable Banking eccessiva")

    def sync(self) -> dict:
        if not self.sync_lock.acquire(blocking=False):
            raise ValueError("Sincronizzazione bancaria già in corso")
        try:
            with self.lock:
                data = self._data()
            sessions = [item for item in data.get("sessions", []) if isinstance(item, dict) and item.get("id")]
            if not sessions:
                raise ValueError("Autorizza prima almeno un conto dalla Dashboard")
            client = self._client()
            all_accounts: list[dict] = []
            all_records: list[dict] = []
            date_from = (datetime.now(timezone.utc) - timedelta(days=365)).date().isoformat()
            for stored in sessions:
                session = client.get(f"/sessions/{stored['id']}")
                aspsp = session.get("aspsp") if isinstance(session.get("aspsp"), dict) else {}
                bank = _clean_text(aspsp.get("name") or stored.get("bank"), 100)
                stored["bank"] = bank
                accounts = self._session_accounts(client, session, bank)
                if not accounts:
                    accounts = [item for item in stored.get("accounts", []) if isinstance(item, dict) and item.get("id")]
                for account in accounts:
                    balances = client.get(f"/accounts/{account['id']}/balances")
                    parsed_balances = [_amount(item.get("balance_amount") or item.get("amount")) for item in (balances.get("balances") or []) if isinstance(item, dict)]
                    available = next((item for item in parsed_balances if item is not None), None)
                    account["balance"] = round(available[0], 2) if available else None
                    account["currency"] = available[1] if available else account["currency"]
                    all_accounts.append(account)
                    all_records.extend(self._transactions(client, account, date_from))
            unique_accounts = {item["id"]: item for item in all_accounts}
            previous_names = {
                item.get("id"): item.get("customName")
                for item in data.get("records", [])
                if isinstance(item, dict) and item.get("id") and item.get("customName")
            }
            unique_records = {item["id"]: item for item in all_records}
            for identifier, custom_name in previous_names.items():
                if identifier in unique_records:
                    unique_records[identifier]["customName"] = custom_name
            data["accounts"] = sorted(unique_accounts.values(), key=lambda item: (item["bank"].casefold(), item["currency"], item["name"].casefold()))
            data["records"] = sorted(unique_records.values(), key=lambda item: (item["date"], item["id"]), reverse=True)
            data["lastSync"] = datetime.now(timezone.utc).isoformat()
            with self.lock:
                self._save(data)
                self.last_error = ""
        except (ValueError, RuntimeError, OSError) as error:
            self.last_error = str(error)
            raise
        finally:
            self.sync_lock.release()
        return self.snapshot()

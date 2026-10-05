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
import threading
import time
import ssl
import certifi
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, HTTPRedirectHandler, HTTPSHandler, build_opener
from secure_storage import atomic_write, read_bytes, migrate
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


API_ORIGIN = "https://api.enablebanking.com"
LEGACY_APPLICATION_ID = "832f4ca4-67b0-4054-8ebd-ed0518198791"
DEFAULT_REDIRECT_URL = os.environ.get(
    "DASHBOARD_BANKING_REDIRECT_URL",
    "http://127.0.0.1:8767/api/enable-banking/callback",
)


def _default_data_dir():
    configured = os.environ.get("DASHBOARD_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return local_app_data / "Dashboard Finanziaria Beta"
    return Path.home() / "Library" / "Application Support" / "Dashboard Finanziaria Beta"


DEFAULT_DATA_DIR = _default_data_dir()
DEFAULT_KEY_PATH = (
    DEFAULT_DATA_DIR
    / "Secrets"
    / "enable-banking.pem"
)
ALLOWED_METHODS = {"GET", "POST"}
ALLOWED_PREFIXES = ("/application", "/aspsps", "/auth", "/sessions", "/accounts/")
# Ninety days covers the current and previous months for normal use and avoids
# predictable 422 responses from banks that reject year-long AIS queries.
TRANSACTION_LOOKBACK_DAYS = (90, 60, 30, 14, 7)


class EnableBankingAPIError(RuntimeError):
    def __init__(self, status: int, detail: str, error_code: str = ""):
        super().__init__(f"Enable Banking ha risposto {status}: {error_code or 'richiesta non riuscita'}. I dati salvati restano disponibili.")
        self.status = status
        self.error_code = error_code


class NoAPIRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Reindirizzamento inatteso dall'API bancaria: richiesta interrotta")


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")


def _atomic_json_write(path: Path, value: object) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def _read_json(path: Path, fallback: object) -> object:
    if not path.is_file():
        return fallback
    if path.is_symlink():
        raise ValueError("Archivio locale non sicuro")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Archivio Enable Banking troppo grande")
    return json.loads(read_bytes(path))


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
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", uid):
        return None
    identifier, scheme = _account_identifier(account)
    currency = str(account.get("currency") or "EUR").upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        currency = "EUR"
    name = _clean_text(account.get("name") or account.get("product") or bank or "Conto bancario", 100)
    masked = ("•••• " + identifier[-4:]) if identifier else ""
    return {
        "id": uid,
        "stableAccountId": str(account.get("identification_hash") or hashlib.sha256(f"{bank}|{identifier or uid}|{currency}".encode()).hexdigest()),
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
    identity = "|".join((str(account.get("stableAccountId") or account["id"]), remote_id or "|".join((date, f"{number:.8f}", currency, description))))
    return {
        "id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "bankRecordId": remote_id,
        "recordType": "expense" if number < 0 else "income",
        "bank": account.get("bank") or account.get("name") or "Conto bancario",
        "accountId": account["id"],
        "stableAccountId": account.get("stableAccountId"),
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
    def __init__(self, key_path: Path = DEFAULT_KEY_PATH, application_id: str = "", timeout: int = 25):
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
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,160}", self.application_id):
            raise ValueError("Application ID Enable Banking non valido")
        issued = int(time.time() if now is None else now)
        header = _b64url(_json_bytes({"alg": "RS256", "kid": self.application_id, "typ": "JWT"}))
        payload = _b64url(_json_bytes({"aud": "api.enablebanking.com", "exp": issued + 300, "iat": issued, "iss": "enablebanking.com"}))
        signing_input = f"{header}.{payload}".encode("ascii")
        key = serialization.load_pem_private_key(read_bytes(self.key_path), password=None)
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
            raise ValueError("Serve una chiave privata RSA di almeno 2048 bit")
        signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        return f"{header}.{payload}.{_b64url(signature)}"

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
            # URL origin is fixed above and paths are restricted to the API allowlist.
            opener = build_opener(NoAPIRedirect(), HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))
            with opener.open(  # nosec B310
                Request(url, data=body, method=method, headers=headers), timeout=self.timeout,
            ) as response:
                raw = response.read(8_000_000)
        except HTTPError as error:
            detail = error.read(4096).decode("utf-8", "replace")
            if error.code == 401:
                raise RuntimeError("Chiave Enable Banking non riconosciuta o revocata") from error
            if error.code == 403:
                raise RuntimeError("Operazione non consentita dall'app Production Restricted") from error
            if error.code == 429:
                raise EnableBankingAPIError(
                    429,
                    "Limite temporaneo di richieste raggiunto",
                    "RATE_LIMIT",
                ) from error
            error_code = ""
            try:
                error_payload = json.loads(detail)
                nested_detail = error_payload.get("detail") if isinstance(error_payload, dict) else {}
                if isinstance(nested_detail, dict):
                    error_code = str(nested_detail.get("error") or "")
                if not error_code and isinstance(error_payload, dict):
                    error_code = str(error_payload.get("error") or "")
            except json.JSONDecodeError:
                pass
            raise EnableBankingAPIError(error.code, detail, error_code) from error
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
    def __init__(self, directory: Path, key_path: Path = DEFAULT_KEY_PATH, redirect_url: str = DEFAULT_REDIRECT_URL):
        self.directory = Path(directory)
        self.data_path = self.directory / "bank-transactions.json"
        self.configuration_path = self.directory / "configuration.json"
        self.key_path = Path(key_path)
        self.redirect_url = str(redirect_url)
        self.lock = threading.RLock()
        self.sync_lock = threading.Lock()
        self.last_error = ""
        self.last_warning = ""
        self.bank_cache: dict[str, tuple[float, dict]] = {}
        for archive in (self.data_path, self.configuration_path, self.key_path):
            migrate(archive)

    @staticmethod
    def _empty() -> dict:
        return {
            "sessions": [],
            "pending": None,
            "accounts": [],
            "records": [],
            "lastSync": None,
            "transactionHistoryFrom": None,
            "application": None,
        }

    def _data(self) -> dict:
        value = _read_json(self.data_path, self._empty())
        if not isinstance(value, dict):
            raise ValueError("Archivio Enable Banking non valido")
        result = self._empty()
        result.update(value)
        return result

    def _save(self, value: dict) -> None:
        _atomic_json_write(self.data_path, value)

    def _configuration(self) -> dict:
        value = _read_json(self.configuration_path, {})
        if isinstance(value, dict) and value.get("applicationId"):
            return {"applicationId": str(value["applicationId"])}
        if self.key_path.is_file():
            return {"applicationId": LEGACY_APPLICATION_ID, "legacy": True}
        return {}

    def _client(self) -> EnableBankingClient:
        configuration = self._configuration()
        return EnableBankingClient(self.key_path, str(configuration.get("applicationId") or ""))

    def configure(self, application_id: object, private_key: object) -> dict:
        identifier = str(application_id or "").strip()
        key_text = str(private_key or "").strip() + "\n"
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,160}", identifier):
            raise ValueError("Application ID non valido")
        if not (1_500 <= len(key_text.encode("utf-8")) <= 20_000):
            raise ValueError("Chiave privata non valida")
        if not re.search(r"-----BEGIN (?:RSA )?PRIVATE KEY-----", key_text):
            raise ValueError("Seleziona la chiave privata PEM scaricata da Enable Banking")
        self.key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.key_path.parent.chmod(0o700)
        temporary = self.key_path.with_suffix(self.key_path.suffix + ".tmp")
        atomic_write(temporary, key_text.encode("utf-8"))
        try:
            EnableBankingClient(temporary, identifier).jwt()
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        temporary.replace(self.key_path)
        self.key_path.chmod(0o600)
        _atomic_json_write(self.configuration_path, {"applicationId": identifier})
        return self.verify()

    @staticmethod
    def _session_account_ids(session: dict) -> list[str]:
        identifiers: list[str] = []
        for item in (session.get("accounts_data") or session.get("accounts") or []):
            uid = item.get("uid") if isinstance(item, dict) else item
            uid = str(uid or "")
            if re.fullmatch(r"[A-Za-z0-9_-]{1,200}", uid) and uid not in identifiers:
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
            client = self._client()
            client._validate_key()
            identifier = str(getattr(client, "application_id", "test-client"))
            return bool(re.fullmatch(r"[A-Za-z0-9_-]{8,160}", identifier))
        except (OSError, ValueError, RuntimeError):
            return False

    def snapshot(self) -> dict:
        with self.lock:
            data = self._data()
        records = data.get("records") if isinstance(data.get("records"), list) else []
        is_configured = self.configured()
        return {
            "provider": "Enable Banking",
            "configured": is_configured,
            "readOnly": True,
            "writesEnabled": False,
            "environment": "PRODUCTION",
            "restricted": True,
            "redirectUrl": self.redirect_url,
            "configurationRequired": not is_configured,
            "application": data.get("application"),
            "authorizationRequired": not bool(data.get("sessions")),
            "selectionRequired": any(item.get("selectionRequired") for item in data.get("sessions", []) if isinstance(item, dict)),
            "authorizationPending": bool(data.get("pending")) and 0 <= time.time() - float(data["pending"].get("createdAt") or 0) < 1200,
            "retryAfterSeconds": max(0, int(float(data.get("syncRetryAt") or 0) - time.time())),
            "connectionCount": len(data.get("sessions", [])),
            "connections": [{"bank": item.get("bank"), "country": item.get("country") or "IT", "validUntil": item.get("validUntil")} for item in data.get("sessions", []) if isinstance(item, dict)],
            "accounts": data.get("accounts", []),
            "records": records,
            "expenses": [item for item in records if item.get("recordType") == "expense"],
            "incomes": [item for item in records if item.get("recordType") == "income"],
            "lastSync": data.get("lastSync"),
            "transactionHistoryFrom": data.get("transactionHistoryFrom"),
            "syncing": self.sync_lock.locked(),
            "error": self.last_error,
            "warning": self.last_warning,
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

    def list_banks(self, country: object) -> dict:
        country_code = str(country or "IT").upper()
        if not re.fullmatch(r"[A-Z]{2}", country_code):
            raise ValueError("Paese non valido")
        cached = self.bank_cache.get(country_code)
        if cached and time.time() - cached[0] < 3600:
            return cached[1]
        response = self._client().get("/aspsps", {"country": country_code})
        raw_banks = response.get("aspsps") or response.get("items") or []
        banks: list[dict[str, object]] = []
        for item in raw_banks:
            if not isinstance(item, dict):
                continue
            name = _clean_text(item.get("name"), 100)
            item_country = str(item.get("country") or country_code).upper()
            if not name or not re.fullmatch(r"[A-Z]{2}", item_country):
                continue
            try:
                maximum_seconds = max(1, min(180 * 86400, int(item.get("maximum_consent_validity") or 90 * 86400)))
            except (TypeError, ValueError):
                maximum_seconds = 90 * 86400
            banks.append({
                "name": name,
                "country": item_country,
                "maximumConsentDays": max(1, maximum_seconds // 86400),
                "maximumConsentSeconds": maximum_seconds,
                "pushAvailable": any(method.get("approach") == "DECOUPLED" and method.get("psu_type") == "personal" and not method.get("credentials") and not method.get("hidden_method") for method in item.get("auth_methods", []) if isinstance(method, dict)),
                "authMethod": next((str(method.get("name")) for method in item.get("auth_methods", []) if isinstance(method, dict) and method.get("approach") == "DECOUPLED" and method.get("psu_type") == "personal" and method.get("name") and not method.get("credentials") and not method.get("hidden_method")), None),
            })
        unique = {(item["name"], item["country"]): item for item in banks}
        result = {"country": country_code, "banks": sorted(unique.values(), key=lambda item: str(item["name"]).casefold())}
        self.bank_cache[country_code] = (time.time(), result)
        return result

    def forget_bank_data(self) -> dict:
        with self.lock:
            self._save(self._empty())
            self.last_error = ""
            self.last_warning = ""
        return self.snapshot()

    def cancel_authorization(self) -> dict:
        with self.lock:
            data = self._data()
            data["pending"] = None
            self._save(data)
        return self.snapshot()

    def select_accounts(self, identifiers: object) -> dict:
        if not isinstance(identifiers, list) or any(not isinstance(item, str) for item in identifiers):
            raise ValueError("Selezione conti non valida")
        with self.lock:
            data = self._data()
            known = {item["id"] for item in data.get("accounts", []) if isinstance(item, dict)}
            if not set(identifiers).issubset(known) or not identifiers:
                raise ValueError("Seleziona almeno un conto disponibile")
            for session in data.get("sessions", []):
                session["selectedAccountIds"] = [item["id"] for item in session.get("accounts", []) if item["id"] in identifiers]
                session["selectionRequired"] = False
            for account in data.get("accounts", []):
                account["selected"] = account["id"] in identifiers
            self._save(data)
        return self.sync()

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
        bank = next((item for item in self.list_banks(country_code)["banks"] if item["name"] == name), None)
        if bank is None:
            raise ValueError("Seleziona una banca disponibile nell'elenco")
        days = min(days, bank["maximumConsentDays"])
        state = secrets.token_urlsafe(32)
        valid_until = (datetime.now(timezone.utc) + timedelta(seconds=min(days * 86400, bank["maximumConsentSeconds"]))).isoformat()
        response = self._client().post(
            "/auth",
            {
                "access": {"valid_until": valid_until, "balances": True, "transactions": True},
                "aspsp": {"name": name, "country": country_code},
                "state": state,
                "redirect_url": self.redirect_url,
                "psu_type": "personal",
                "language": "it",
                **({"auth_method": bank["authMethod"]} if bank.get("authMethod") else {}),
            },
        )
        url = str(response.get("url") or "")
        authorization_url = urlparse(url)
        hostname = (authorization_url.hostname or "").lower()
        if authorization_url.scheme != "https" or not (hostname == "enablebanking.com" or hostname.endswith(".enablebanking.com")):
            raise RuntimeError("Enable Banking non ha restituito un indirizzo di autorizzazione valido")
        with self.lock:
            data = self._data()
            data["pending"] = {"stateHash": hashlib.sha256(state.encode()).hexdigest(), "createdAt": time.time(), "bank": name, "country": country_code, "validUntil": valid_until}
            self._save(data)
        return {"status": "authorization_required", "url": url}

    def complete_authorization(self, callback_url: object) -> dict:
        value = str(callback_url or "").strip()
        parsed = urlparse(value)
        expected = urlparse(self.redirect_url)
        if (parsed.scheme, parsed.hostname, parsed.port, parsed.path) != (expected.scheme, expected.hostname, expected.port, expected.path):
            raise ValueError("Indirizzo di ritorno Enable Banking non valido")
        query = parse_qs(parsed.query)
        code = str((query.get("code") or [""])[0])
        state_value = str((query.get("state") or [""])[0])
        if (not code and not query.get("error")) or len(code) > 200 or not state_value:
            raise ValueError("Codice di autorizzazione mancante")
        with self.lock:
            data = self._data()
            pending = data.get("pending") if isinstance(data.get("pending"), dict) else {}
        expected = str(pending.get("stateHash") or "")
        if not expected or not secrets.compare_digest(expected, hashlib.sha256(state_value.encode()).hexdigest()):
            raise ValueError("Stato autorizzazione non valido")
        if time.time() - float(pending.get("createdAt") or 0) > 20 * 60:
            raise ValueError("Autorizzazione scaduta: avviala nuovamente")
        with self.lock:
            current = self._data()
            if current.get("pending") != pending:
                raise ValueError("Autorizzazione già utilizzata")
            current["pending"] = None
            self._save(current)
        if query.get("error"):
            raise ValueError("Autorizzazione annullata o non concessa dalla banca. Puoi riprovare.")
        session = self._client().post("/sessions", {"code": code})
        session_id = str(session.get("session_id") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", session_id):
            raise RuntimeError("Enable Banking non ha restituito una sessione valida")
        aspsp = session.get("aspsp") if isinstance(session.get("aspsp"), dict) else {}
        bank = _clean_text(aspsp.get("name") or pending.get("bank"), 100)
        accounts = self._session_accounts(self._client(), session, bank)
        with self.lock:
            data = self._data()
            sessions = [item for item in data.get("sessions", []) if isinstance(item, dict) and item.get("id") != session_id and not (item.get("bank") == bank and item.get("country") == pending.get("country"))]
            access = session.get("access") if isinstance(session.get("access"), dict) else {}
            sessions.append({"id": session_id, "bank": bank, "country": pending.get("country"), "accounts": accounts, "selectionRequired": True, "validUntil": access.get("valid_until") or pending.get("validUntil")})
            data["sessions"], data["pending"] = sessions, None
            preserved_ids = {account["id"] for old_session in sessions[:-1] for account in old_session.get("accounts", [])}
            data["accounts"] = [account for account in data.get("accounts", []) if account.get("id") in preserved_ids] + accounts
            self._save(data)
        return self.snapshot()

    def _transactions(self, client: EnableBankingClient, account: dict) -> tuple[list[dict], str]:
        today = datetime.now(timezone.utc).date()
        last_period_error: EnableBankingAPIError | None = None
        for lookback_days in TRANSACTION_LOOKBACK_DAYS:
            date_from = (today - timedelta(days=lookback_days)).isoformat()
            records: list[dict] = []
            continuation = None
            try:
                for _ in range(100):
                    query = {"date_from": date_from}
                    if continuation:
                        query["continuation_key"] = continuation
                    page = client.get(f"/accounts/{account['id']}/transactions", query)
                    records.extend(
                        item
                        for item in (
                            normalize_transaction(raw, account)
                            for raw in (page.get("transactions") or [])
                        )
                        if item
                    )
                    continuation = page.get("continuation_key")
                    if not continuation:
                        return records, date_from
            except EnableBankingAPIError as error:
                if error.status != 422 or error.error_code != "WRONG_TRANSACTIONS_PERIOD":
                    raise
                last_period_error = error
                continue
            raise RuntimeError("Paginazione Enable Banking eccessiva")
        raise RuntimeError(
            "La banca non accetta neppure una richiesta degli ultimi 7 giorni. "
            "Rinnova il consenso del conto e riprova."
        ) from last_period_error

    def sync(self) -> dict:
        if not self.sync_lock.acquire(blocking=False):
            raise ValueError("Sincronizzazione bancaria già in corso")
        try:
            with self.lock:
                data = self._data()
            original_sessions = json.dumps(data.get("sessions", []), sort_keys=True)
            if float(data.get("syncRetryAt") or 0) > time.time():
                self.last_warning = "Aggiornamento in pausa: i dati salvati restano disponibili. Riprova fra qualche minuto."
                return self.snapshot()
            sessions = [item for item in data.get("sessions", []) if isinstance(item, dict) and item.get("id")]
            if not sessions:
                raise ValueError("Autorizza prima almeno un conto dalla Dashboard")
            client = self._client()
            all_accounts: list[dict] = []
            all_records: list[dict] = []
            previous_records = [item for item in data.get("records", []) if isinstance(item, dict)]
            # Preserve imported history and existing classification identifiers.
            all_records.extend(previous_records)
            history_starts: list[str] = []
            for stored in sessions:
                if stored.get("selectionRequired") or stored.get("selectedAccountIds") == []:
                    all_accounts.extend(stored.get("accounts", []))
                    continue
                session = client.get(f"/sessions/{stored['id']}")
                aspsp = session.get("aspsp") if isinstance(session.get("aspsp"), dict) else {}
                bank = _clean_text(aspsp.get("name") or stored.get("bank"), 100)
                stored["bank"] = bank
                accounts = self._session_accounts(client, session, bank)
                if not accounts:
                    accounts = [item for item in stored.get("accounts", []) if isinstance(item, dict) and item.get("id")]
                for account in accounts:
                    selected_ids = stored.get("selectedAccountIds")
                    if selected_ids is not None and account["id"] not in selected_ids:
                        account["selected"] = False
                        all_accounts.append(account)
                        continue
                    account["selected"] = True
                    balances = client.get(f"/accounts/{account['id']}/balances")
                    parsed_balances = [_amount(item.get("balance_amount") or item.get("amount")) for item in (balances.get("balances") or []) if isinstance(item, dict)]
                    available = next((item for item in parsed_balances if item is not None), None)
                    account["balance"] = round(available[0], 2) if available else None
                    account["currency"] = available[1] if available else account["currency"]
                    all_accounts.append(account)
                    new_records, date_from = self._transactions(client, account)
                    previous_accounts = [old for old in data.get("accounts", []) if isinstance(old, dict) and (
                        old.get("stableAccountId") == account.get("stableAccountId") or
                        (not old.get("stableAccountId") and old.get("bank") == account.get("bank") and old.get("currency") == account.get("currency") and old.get("identifierMasked") and old.get("identifierMasked") == account.get("identifierMasked")))]
                    old_ids = {old["id"] for old in previous_accounts} if len(previous_accounts) == 1 else {account["id"]}
                    for record in new_records:
                        matches = [old for old in previous_records if old.get("accountId") in old_ids and old.get("bankRecordId") and old.get("bankRecordId") == record.get("bankRecordId")]
                        if len(matches) == 1:
                            record["id"] = matches[0]["id"]
                    history_starts.append(date_from)
                    all_records.extend(new_records)
                    all_records.extend(
                        item
                        for item in previous_records
                        if item.get("accountId") == account["id"]
                        and isinstance(item.get("date"), str)
                        and item["date"] < date_from
                    )
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
            data["transactionHistoryFrom"] = min(history_starts) if history_starts else None
            with self.lock:
                latest = self._data()
                if json.dumps(latest.get("sessions", []), sort_keys=True) != original_sessions:
                    self.last_warning = "Il collegamento è cambiato durante l'aggiornamento. Riprova con la selezione corrente."
                    return self.snapshot()
                for record in data["records"]:
                    latest_name = next((item.get("customName") for item in latest.get("records", []) if item.get("id") == record.get("id")), None)
                    if latest_name:
                        record["customName"] = latest_name
                for field in ("accounts", "records", "lastSync", "transactionHistoryFrom"):
                    latest[field] = data[field]
                self._save(latest)
                self.last_error = ""
                self.last_warning = ""
        except EnableBankingAPIError as error:
            if error.status != 429:
                self.last_error = str(error)
                raise
            self.last_error = ""
            self.last_warning = (
                "Enable Banking ha chiesto una pausa temporanea. I dati già salvati restano disponibili; "
                "riprova l'aggiornamento fra qualche minuto."
            )
            with self.lock:
                saved = self._data()
                saved["syncRetryAt"] = time.time() + 300
                self._save(saved)
        except (ValueError, RuntimeError, OSError) as error:
            self.last_error = str(error)
            raise
        finally:
            self.sync_lock.release()
        return self.snapshot()

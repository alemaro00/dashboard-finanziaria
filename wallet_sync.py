"""Safe Wallet by BudgetBakers sync and manual-record editing."""
from __future__ import annotations

import hashlib, json, math, os, re, subprocess, threading, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_ORIGIN = "https://rest.budgetbakers.com/wallet"
KEYCHAIN_SERVICE = "it.alemaro.dashboard-finanziaria.wallet-api"
KEYCHAIN_ACCOUNT = "wallet-api"
UNKNOWN_CATEGORIES = {"", "unknown", "uncategorized", "non categorizzato", "da classificare"}
PAYMENT_TYPES = {"cash", "debit_card", "credit_card", "transfer", "voucher", "mobile_payment", "web_payment"}
RECORD_TYPES = {"expense", "income"}


def _atomic_json_write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path); path.chmod(0o600)


def _read_json(path: Path, fallback):
    if not path.is_file(): return fallback
    if path.stat().st_size > 20 * 1024 * 1024: raise ValueError("Archivio Wallet troppo grande")
    return json.loads(path.read_text(encoding="utf-8"))


def _field_name(value, fallback="") -> str:
    return str(value.get("name") or value.get("label") or fallback) if isinstance(value, dict) else str(value or fallback)


def _clean_text(value, maximum=255) -> str:
    return str(value or "").strip()[:maximum]


def normalize_wallet_record(record: dict, managed_ids: set[str] | None = None) -> dict | None:
    if not isinstance(record, dict): return None
    amount_data = record.get("amount") or {}
    raw_value = amount_data.get("value") if isinstance(amount_data, dict) else amount_data
    try: raw_amount = float(raw_value)
    except (TypeError, ValueError): return None
    if not math.isfinite(raw_amount) or raw_amount == 0 or abs(raw_amount) >= 10_000_000: return None
    record_type = str(record.get("recordType") or ("expense" if raw_amount < 0 else "income")).casefold()
    if record_type not in RECORD_TYPES: return None
    date = str(record.get("recordDate") or record.get("date") or "")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date): return None
    category_data = record.get("category")
    category = _field_name(category_data, "Da classificare").strip()[:100]
    category_id = str(category_data.get("id") or "") if isinstance(category_data, dict) else str(record.get("categoryId") or "")
    counterparty, note = _clean_text(record.get("counterParty")), _clean_text(record.get("note"))
    description = " · ".join(dict.fromkeys(x for x in (counterparty, note) if x))[:240] or category
    record_id = str(record.get("id") or "")
    currency = str(amount_data.get("currencyCode") or "EUR").upper() if isinstance(amount_data, dict) else "EUR"
    identity = record_id or "|".join((date, f"{raw_amount:.2f}", currency, description, category))
    account = record.get("account")
    account_id = str(record.get("accountId") or (account.get("id") if isinstance(account, dict) else "") or "")
    account_name = str(record.get("accountName") or _field_name(account, account_id or "Wallet"))[:100]
    source = str(record.get("source") or "missing")
    editable = bool(record_id and managed_ids and record_id in managed_ids and source == "rest")
    return {"id": hashlib.sha256(identity.encode()).hexdigest(), "walletRecordId": record_id,
            "recordType": record_type, "bank": account_name or "Wallet", "accountId": account_id,
            "date": date, "amount": round(abs(raw_amount), 2), "signedAmount": round(raw_amount, 2),
            "currency": currency, "description": description, "counterParty": counterparty, "note": note,
            "suggestedCategory": category or "Da classificare", "categoryId": category_id,
            "needsReview": category.casefold() in UNKNOWN_CATEGORIES,
            "paymentType": str(record.get("paymentType") or "")[:80], "source": source, "editable": editable}


def normalize_wallet_expense(record: dict) -> dict | None:
    value = normalize_wallet_record(record)
    return value if value and value["recordType"] == "expense" else None


class WalletClient:
    def __init__(self, token: str, timeout: int = 20):
        if len(token) < 20 or len(token) > 4096 or any(c.isspace() for c in token): raise ValueError("Token Wallet non valido")
        self.token, self.timeout = token, timeout

    def request(self, method: str, path: str, query: dict | None = None, payload=None):
        if method not in {"GET", "POST", "PATCH"} or not path.startswith("/v1/api/"): raise ValueError("Richiesta Wallet non ammessa")
        url = API_ORIGIN + path + (("?" + urlencode(query)) if query else "")
        body = None if payload is None else json.dumps(payload, allow_nan=False).encode()
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/json", "User-Agent": "Dashboard-Finanziaria/1.11"}
        if body is not None: headers["Content-Type"] = "application/json"
        try:
            with urlopen(Request(url, data=body, method=method, headers=headers), timeout=self.timeout) as response:
                parsed = json.loads(response.read(4_000_000).decode()); response_headers = dict(response.headers.items())
        except HTTPError as error:
            detail = error.read(4096).decode("utf-8", "replace")
            if error.code == 409: raise RuntimeError("Wallet sta preparando la sincronizzazione iniziale. Riprova tra alcuni minuti.") from error
            if error.code == 401: raise RuntimeError("Token Wallet non valido o revocato") from error
            if error.code == 429: raise RuntimeError("Limite API Wallet raggiunto. Riprova più tardi.") from error
            raise RuntimeError(f"Wallet ha risposto {error.code}: {detail[:500]}") from error
        except (URLError, TimeoutError) as error:
            uncertain = " Esito incerto: sincronizza Wallet prima di riprovare." if method != "GET" else ""
            raise RuntimeError(f"Wallet non raggiungibile: {error}.{uncertain}") from error
        except json.JSONDecodeError as error: raise RuntimeError("Risposta Wallet non valida") from error
        if not isinstance(parsed, dict): raise RuntimeError("Risposta Wallet non valida")
        return parsed, response_headers

    def get(self, path, query=None): return self.request("GET", path, query=query)
    def post(self, path, payload): return self.request("POST", path, payload=payload)
    def patch(self, path, payload, query=None): return self.request("PATCH", path, query=query, payload=payload)


def read_keychain_token() -> str:
    token = os.environ.get("WALLET_API_TOKEN", "")
    if token: return token.strip()
    result = subprocess.run(["/usr/bin/security", "find-generic-password", "-w", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT],
                            capture_output=True, text=True, timeout=10, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def _validate_mutation(record: dict, accounts: list[dict], categories: list[dict], require_id=False) -> dict:
    if not isinstance(record, dict): raise ValueError("Movimento Wallet non valido")
    allowed = {"walletRecordId", "recordType", "accountId", "categoryId", "date", "amount", "counterParty", "note", "paymentType"}
    if set(record) - allowed: raise ValueError("Campi Wallet non ammessi")
    record_type, account_id = _clean_text(record.get("recordType"), 20).casefold(), _clean_text(record.get("accountId"), 100)
    if record_type not in RECORD_TYPES: raise ValueError("Tipo movimento non valido")
    account = next((item for item in accounts if item["id"] == account_id and not item.get("archived")), None)
    if not account: raise ValueError("Conto Wallet non valido")
    try: amount = float(record.get("amount"))
    except (TypeError, ValueError): raise ValueError("Importo Wallet non valido") from None
    if not math.isfinite(amount) or amount <= 0 or amount >= 10_000_000: raise ValueError("L'importo Wallet deve essere positivo")
    date = _clean_text(record.get("date"), 10)
    try: parsed_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError: raise ValueError("Data Wallet non valida") from None
    if parsed_date > datetime.now(timezone.utc) + timedelta(hours=24): raise ValueError("La data Wallet è troppo lontana nel futuro")
    category_id = _clean_text(record.get("categoryId"), 100)
    if category_id and category_id not in {item["id"] for item in categories if item.get("enabled")}: raise ValueError("Categoria Wallet non valida")
    payment_type = _clean_text(record.get("paymentType"), 30) or "debit_card"
    if payment_type not in PAYMENT_TYPES: raise ValueError("Metodo di pagamento Wallet non valido")
    result = {"accountId": account_id, "amount": {"value": round(-amount if record_type == "expense" else amount, 2), "currencyCode": account["currency"]},
              "recordDate": date + "T12:00:00Z", "paymentType": payment_type,
              "counterParty": _clean_text(record.get("counterParty")), "note": _clean_text(record.get("note"))}
    if category_id: result["categoryId"] = category_id
    if require_id:
        result["id"] = _clean_text(record.get("walletRecordId"), 100)
        if not result["id"]: raise ValueError("ID Wallet mancante")
    return result


class WalletSyncService:
    def __init__(self, directory: Path):
        self.directory, self.data_path = Path(directory), Path(directory) / "wallet-transactions.json"
        self.lock, self.sync_lock = threading.RLock(), threading.Lock()
        self.last_error, self.last_attempt = "", 0.0

    def _data(self):
        fallback = {"records": [], "accounts": [], "categories": [], "managedRecordIds": [], "lastSync": None, "sourceUpdatedAt": None}
        value = _read_json(self.data_path, fallback)
        if not isinstance(value, dict): raise ValueError("Archivio Wallet non valido")
        if "records" not in value and "expenses" in value: value["records"] = value.get("expenses", [])
        for key, default in fallback.items(): value.setdefault(key, default)
        return value

    def _client(self):
        token = read_keychain_token()
        if not token: raise ValueError("Configura prima il token API di Wallet Premium")
        return WalletClient(token)

    def configured(self): return bool(read_keychain_token())

    def snapshot(self):
        with self.lock: data = self._data()
        configured, last_sync = self.configured(), data.get("lastSync")
        try: stale = not last_sync or time.time() - datetime.fromisoformat(last_sync).timestamp() > 900
        except (TypeError, ValueError): stale = True
        if configured and stale and time.monotonic() - self.last_attempt > 300: threading.Thread(target=self._background_sync, daemon=True).start()
        records = data.get("records", [])
        return {"provider": "Wallet by BudgetBakers", "readOnly": False, "writesEnabled": configured,
                "writeScope": "dashboard-managed-records-only", "configured": configured, "records": records,
                "expenses": [x for x in records if x.get("recordType") == "expense"],
                "incomes": [x for x in records if x.get("recordType") == "income"],
                "accounts": data.get("accounts", []), "categories": data.get("categories", []),
                "lastSync": last_sync, "sourceUpdatedAt": data.get("sourceUpdatedAt"),
                "syncing": self.sync_lock.locked(), "error": self.last_error}

    def _background_sync(self):
        if not self.sync_lock.acquire(blocking=False): return
        self.last_attempt = time.monotonic()
        try: self._sync_locked()
        except (ValueError, RuntimeError, OSError) as error: self.last_error = str(error)
        finally: self.sync_lock.release()

    def sync(self):
        if not self.sync_lock.acquire(blocking=False): raise ValueError("Sincronizzazione Wallet già in corso")
        self.last_attempt = time.monotonic()
        try: self._sync_locked()
        finally: self.sync_lock.release()
        return self.snapshot()

    @staticmethod
    def _page_all(client, path, key, query=None):
        values, offset, updated = [], 0, None
        for _ in range(100):
            response, headers = client.get(path, {"limit": 200, "offset": offset, **(query or {})})
            updated = headers.get("X-Last-Data-Change-At") or updated
            page = response.get(key) or response.get("data") or []
            if not isinstance(page, list): raise RuntimeError(f"Elenco Wallet {key} non valido")
            values.extend(page)
            if response.get("nextOffset") is None: return values, updated
            try: offset = int(response["nextOffset"])
            except (TypeError, ValueError): raise RuntimeError("Paginazione Wallet non valida") from None
        raise RuntimeError("Paginazione Wallet eccessiva")

    def _sync_locked(self):
        client, old = self._client(), self._data()
        managed = set(map(str, old.get("managedRecordIds", [])))
        date_from = (datetime.now(timezone.utc) - timedelta(days=365)).date().isoformat()
        raw_records, updated = self._page_all(client, "/v1/api/records", "records", {"recordDate": f"gte.{date_from}"})
        raw_accounts, _ = self._page_all(client, "/v1/api/accounts", "accounts")
        raw_categories, _ = self._page_all(client, "/v1/api/categories", "categories")
        records = [x for x in (normalize_wallet_record(item, managed) for item in raw_records) if x]
        accounts = []
        for item in raw_accounts:
            balance = item.get("balance") or item.get("initialBalance") or {}
            accounts.append({"id": str(item.get("id") or ""), "name": _clean_text(item.get("name"), 100),
                             "currency": str(balance.get("currencyCode") or "EUR").upper(),
                             "isBankSync": bool(item.get("isBankSync")), "archived": bool(item.get("archived"))})
        categories = [{"id": str(x.get("id") or ""), "name": _clean_text(x.get("name"), 100),
                       "group": _field_name(x.get("group")), "archived": bool(x.get("archived")),
                       "enabled": x.get("enabled") is not False} for x in raw_categories]
        data = {"records": sorted(records, key=lambda x: (x["date"], x["id"]), reverse=True),
                "accounts": sorted((x for x in accounts if x["id"]), key=lambda x: x["name"].casefold()),
                "categories": sorted((x for x in categories if x["id"]), key=lambda x: (x["group"].casefold(), x["name"].casefold())),
                "managedRecordIds": sorted(managed), "lastSync": datetime.now(timezone.utc).isoformat(), "sourceUpdatedAt": updated}
        with self.lock: _atomic_json_write(self.data_path, data); self.last_error = ""

    @staticmethod
    def _successful_record(response):
        results = response.get("results")
        if not isinstance(results, list) or len(results) != 1 or not results[0].get("success"):
            detail = results[0].get("error") if isinstance(results, list) and results else response.get("error")
            raise RuntimeError("Wallet non ha salvato il movimento" + (f": {detail}" if detail else ""))
        return results[0].get("record") or {"id": results[0].get("id")}

    def create_record(self, record):
        with self.sync_lock:
            data = self._data(); body = _validate_mutation(record, data["accounts"], data["categories"])
            created = self._successful_record(self._client().post("/v1/api/records", [body])[0])
            created_id = str(created.get("id") or "")
            if not created_id: raise RuntimeError("Wallet non ha restituito l'ID del movimento")
            data["managedRecordIds"] = sorted(set(map(str, data.get("managedRecordIds", []))) | {created_id})
            _atomic_json_write(self.data_path, data); self._sync_locked()
        return self.snapshot()

    def update_record(self, record):
        with self.sync_lock:
            data = self._data(); body = _validate_mutation(record, data["accounts"], data["categories"], True)
            if body["id"] not in set(map(str, data.get("managedRecordIds", []))): raise ValueError("Puoi modificare soltanto movimenti creati dalla Dashboard")
            current = next((x for x in data["records"] if x.get("walletRecordId") == body["id"]), None)
            if not current or not current.get("editable"): raise ValueError("Il movimento Wallet non è modificabile dalla Dashboard")
            self._successful_record(self._client().patch("/v1/api/records", [body], {"validation": "strict"})[0]); self._sync_locked()
        return self.snapshot()

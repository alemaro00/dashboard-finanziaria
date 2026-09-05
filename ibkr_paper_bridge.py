from __future__ import annotations

import argparse
import json
import math
import os
import queue
import re
import subprocess
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper


SCRIPT_DIR = Path(__file__).resolve().parent
DASHBOARD_FILE = SCRIPT_DIR / "salary-planner-react.html"
ARCHIVE_FILE_PATTERN = re.compile(r"^patrimonio-[0-9]{4}-[a-z0-9-]+\.json$")
# Account updates normally arrive every three minutes; allow a five-minute gap.
STALE_AFTER_SECONDS = 300
ACCOUNT_SUMMARY_TAGS = ",".join(
    [
        "AccountType",
        "NetLiquidation",
        "TotalCashValue",
        "SettledCash",
        "BuyingPower",
        "AvailableFunds",
        "ExcessLiquidity",
        "MaintMarginReq",
        "GrossPositionValue",
        "UnrealizedPnL",
        "RealizedPnL",
        "Currency",
    ]
)
INFORMATION_CODES = {
    2104,
    2106,
    2107,
    2108,
    2158,
}
SECURITY_TYPES = {
    "STK": "Azioni",
    "OPT": "Opzioni",
    "FUT": "Futures",
    "FOP": "Opzioni su futures",
    "IOPT": "Opzioni",
    "CONTFUT": "Future continuo",
    "CASH": "Forex",
    "CFD": "CFD",
    "BOND": "Obbligazioni",
    "FUND": "Fondi",
    "IND": "Indici",
    "WAR": "Warrant",
    "CMDTY": "Commodities",
    "CRYPTO": "Crypto",
    "BAG": "Strategie combinate",
}

COUNTRY_CONTINENT_BY_CODE = {}
for country_code in "AL AD AT AX BY BE BA BG HR CY CZ DK EE FO FI FR DE GI GR GG VA HU IS IE IM IT JE LV LI LT LU MT MD MC ME NL MK NO PL PT RO RU SM RS SK SI ES SE CH UA GB XK".split():
    COUNTRY_CONTINENT_BY_CODE[country_code] = "Europa"
for country_code in "US CA".split():
    COUNTRY_CONTINENT_BY_CODE[country_code] = "Nord America (USA e Canada)"
for country_code in "AI AG AR AW BS BB BZ BM BO BQ BR KY CL CO CR CU CW DM DO EC SV FK GF GL GD GP GT GY HT HN JM MQ MX MS NI PA PY PE PR BL KN LC MF PM VC SX SR TT TC UY VE VG VI".split():
    COUNTRY_CONTINENT_BY_CODE[country_code] = "Resto dell'America"
for country_code in "AF AM AZ BH BD BT BN KH CN GE HK IN ID IR IQ IL JP JO KZ KW KG LA LB MO MY MV MN MM NP KP OM PK PS PH QA SA SG KR LK SY TW TJ TH TL TR TM AE UZ VN YE".split():
    COUNTRY_CONTINENT_BY_CODE[country_code] = "Asia"
for country_code in "DZ AO BJ BW BF BI CV CM CF TD KM CD CG CI DJ EG GQ ER SZ ET GA GM GH GN GW KE LS LR LY MG MW ML MR MU YT MA MZ NA NE NG RE RW SH ST SN SC SL SO ZA SS SD TZ TG TN UG EH ZM ZW".split():
    COUNTRY_CONTINENT_BY_CODE[country_code] = "Africa"
for country_code in "AS AU CK FJ PF GU KI MH FM NR NC NZ NU NF MP PW PG PN WS SB TK TO TV UM VU WF".split():
    COUNTRY_CONTINENT_BY_CODE[country_code] = "Oceania"
for country_code in "AQ BV GS HM TF".split():
    COUNTRY_CONTINENT_BY_CODE[country_code] = "Antartide"
for country_code in "XS EU UN".split():
    COUNTRY_CONTINENT_BY_CODE[country_code] = "Globale"

COUNTRY_CODE_ALIASES = {
    "UNITED STATES": "US",
    "UNITED STATES OF AMERICA": "US",
    "USA": "US",
    "CANADA": "CA",
    "ITALY": "IT",
    "ITALIA": "IT",
    "SPAIN": "ES",
    "SPAGNA": "ES",
    "FRANCE": "FR",
    "FRANCIA": "FR",
    "GERMANY": "DE",
    "GERMANIA": "DE",
    "UNITED KINGDOM": "GB",
    "REGNO UNITO": "GB",
    "SWITZERLAND": "CH",
    "SVIZZERA": "CH",
    "IRELAND": "IE",
    "IRLANDA": "IE",
    "LUXEMBOURG": "LU",
    "LUSSEMBURGO": "LU",
    "NETHERLANDS": "NL",
    "PAESI BASSI": "NL",
    "MEXICO": "MX",
    "MESSICO": "MX",
    "BRAZIL": "BR",
    "BRASILE": "BR",
    "ARGENTINA": "AR",
    "CHINA": "CN",
    "CINA": "CN",
    "JAPAN": "JP",
    "GIAPPONE": "JP",
    "INDIA": "IN",
    "AUSTRALIA": "AU",
    "NEW ZEALAND": "NZ",
    "NUOVA ZELANDA": "NZ",
    "SOUTH AFRICA": "ZA",
    "SUDAFRICA": "ZA",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return number if math.isfinite(number) else 0.0


def security_identifiers(contract_details) -> dict[str, str]:
    return {
        str(item.tag or "").upper(): str(item.value or "")
        for item in (getattr(contract_details, "secIdList", None) or [])
        if getattr(item, "tag", None) and getattr(item, "value", None)
    }


def normalized_country_code(value: object) -> str:
    normalized = re.sub(r"[^A-Z]+", " ", str(value or "").upper()).strip()
    if len(normalized) == 2 and normalized in COUNTRY_CONTINENT_BY_CODE:
        return normalized
    return COUNTRY_CODE_ALIASES.get(normalized, "")


def issuer_country_from_details(contract_details) -> tuple[str, str]:
    contract = contract_details.contract
    direct_values = [
        getattr(contract_details, "issuerCountryCode", ""),
        getattr(contract_details, "issuerCountry", ""),
        getattr(contract_details, "countryCode", ""),
        getattr(contract_details, "country", ""),
        getattr(contract, "issuerCountryCode", ""),
        getattr(contract, "issuerCountry", ""),
        getattr(contract, "countryCode", ""),
        getattr(contract, "country", ""),
    ]
    for value in direct_values:
        country_code = normalized_country_code(value)
        if country_code:
            return country_code, "IBKR Description"

    descriptive_text = "\n".join(
        str(value or "")
        for value in (
            getattr(contract, "description", ""),
            getattr(contract_details, "longName", ""),
            getattr(contract_details, "descAppend", ""),
            getattr(contract_details, "notes", ""),
        )
        if value
    )
    patterns = (
        r"issuer\s+country(?:\s*/\s*region)?\s*[:=\-]\s*([^,;|\n]+)",
        r"country\s+of\s+issuer\s*[:=\-]\s*([^,;|\n]+)",
        r"issuer\s+domicile\s*[:=\-]\s*([^,;|\n]+)",
        r"country\s*/\s*region\s*[:=\-]\s*([^,;|\n]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, descriptive_text, flags=re.IGNORECASE)
        if match:
            country_code = normalized_country_code(match.group(1))
            if country_code:
                return country_code, "IBKR Description"

    isin = security_identifiers(contract_details).get("ISIN", "").upper()
    if len(isin) >= 2 and isin[:2].isalpha():
        country_code = isin[:2]
        if country_code in COUNTRY_CONTINENT_BY_CODE:
            return country_code, "IBKR ISIN"
    return "", ""


def investment_asset_class(contract_details) -> str:
    contract = contract_details.contract
    security_type = str(contract.secType or "").upper()
    details_text = " ".join(
        str(value or "").upper()
        for value in (
            getattr(contract_details, "stockType", ""),
            getattr(contract_details, "bondType", ""),
            getattr(contract_details, "longName", ""),
            getattr(contract_details, "category", ""),
            getattr(contract_details, "subcategory", ""),
            getattr(contract_details, "descAppend", ""),
        )
    )
    if security_type == "STK":
        if any(marker in details_text for marker in ("ETF", "ETN", "ETC", "UCITS", "EXCHANGE TRADED")):
            return "ETF"
        if "REIT" in details_text:
            return "Real Estate"
        return "Azioni"
    if security_type in {"OPT", "IOPT"}:
        return "Opzioni"
    if security_type in {"FUT", "FOP", "CONTFUT", "CFD", "WAR", "BAG", "SSP"}:
        return "Derivati"
    if security_type == "BOND":
        if any(marker in details_text for marker in ("GOVT", "GOVERNMENT", "TREASURY", "SOVEREIGN", "T-BILL", "BTP", "BOT", "CCT", "BUND", "GILT")):
            return "Titoli di Stato"
        return "Obbligazioni"
    return {
        "CASH": "Forex",
        "FUND": "Fondi",
        "IND": "Indici",
        "CMDTY": "Commodities",
        "CRYPTO": "Crypto",
    }.get(security_type, SECURITY_TYPES.get(security_type, security_type or "Altro"))


class IbkrAccountClient(EWrapper, EClient):
    """Read-only account monitor. No order methods are exposed by this service."""

    def __init__(self, host: str, port: int, client_id: int, environment: str):
        EWrapper.__init__(self)
        EClient.__init__(self, self)
        self.tws_host = host
        self.tws_port = port
        self.tws_client_id = client_id
        self.environment = environment.upper()
        self.environment_label = "Live" if self.environment == "LIVE" else "Paper"
        self.lock = threading.RLock()
        self.connection_lock = threading.Lock()
        self.ready = threading.Event()
        self.account_download_complete = threading.Event()
        self.account_summary_complete = threading.Event()
        self.stop_event = threading.Event()
        self.connection_state = "disconnected"
        self.connection_message = f"In attesa di TWS {self.environment_label}"
        self.accounts: list[str] = []
        self.active_account = ""
        self.account_summary: dict[str, dict[str, dict[str, object]]] = {}
        self.account_values: dict[str, dict[str, dict[str, object]]] = {}
        self.positions: dict[str, dict[str, object]] = {}
        self.contract_metadata: dict[int, dict[str, object]] = {}
        self.contract_detail_pending: set[int] = set()
        self.contract_detail_failed: set[int] = set()
        self.contract_detail_requests: dict[int, int] = {}
        self.contract_detail_queue = queue.Queue()
        self.recent_messages: list[dict[str, object]] = []
        self.last_data_update = ""
        self._last_data_monotonic: float | None = None
        self.last_update = ""
        self.last_account_time = ""
        self._next_contract_detail_request_id = 12000 if self.environment == "LIVE" else 22000
        self._reader_thread: threading.Thread | None = None
        self._monitor_thread: threading.Thread | None = None
        self._metadata_thread: threading.Thread | None = None
        self._subscribed_account = ""

    def start(self) -> None:
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self.stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._connection_monitor,
            name=f"ibkr-{self.environment.lower()}-monitor",
            daemon=True,
        )
        self._monitor_thread.start()
        self._metadata_thread = threading.Thread(
            target=self._contract_metadata_worker,
            name=f"ibkr-{self.environment.lower()}-metadata",
            daemon=True,
        )
        self._metadata_thread.start()

    def _connection_monitor(self) -> None:
        while not self.stop_event.is_set():
            reader_running = self._reader_thread and self._reader_thread.is_alive()
            if not self.isConnected() and not reader_running:
                self.connect_to_tws()
            self.stop_event.wait(5.0)

    def connect_to_tws(self) -> None:
        if not self.connection_lock.acquire(blocking=False):
            return
        try:
            with self.lock:
                self.connection_state = "connecting"
                self.connection_message = (
                    f"Connessione a TWS {self.environment_label} "
                    f"{self.tws_host}:{self.tws_port}"
                )
                self.ready.clear()
                self.account_download_complete.clear()
                self.account_summary_complete.clear()
                self._subscribed_account = ""
                # Rebuild financial data each session: absent positions must not survive reconnect.
                self.accounts = []
                self.active_account = ""
                self.account_summary.clear()
                self.account_values.clear()
                self.positions.clear()
                self.last_data_update = ""
                self._last_data_monotonic = None
                self.last_account_time = ""
            self.connect(self.tws_host, self.tws_port, self.tws_client_id)
            if self.isConnected():
                self._reader_thread = threading.Thread(
                    target=self.run,
                    name=f"ibkr-{self.environment.lower()}-reader",
                    daemon=True,
                )
                self._reader_thread.start()
        except Exception as error:
            with self.lock:
                self.connection_state = "error"
                self.connection_message = str(error)
        finally:
            self.connection_lock.release()

    def stop(self) -> None:
        self.stop_event.set()
        try:
            if self._subscribed_account and self.isConnected():
                self.reqAccountUpdates(False, self._subscribed_account)
            if self.isConnected():
                self.cancelPositions()
                self.cancelAccountSummary(9101)
                self.disconnect()
        except Exception:
            pass

    def _touch(self) -> None:
        self.last_update = utc_now()

    def _touch_data(self, account: str) -> None:
        if account and account == self.active_account and self.connection_state == "connected":
            self.last_data_update = utc_now()
            self._last_data_monotonic = time.monotonic()

    def _data_status(self) -> tuple[str, float | None, bool]:
        age = (max(0.0, time.monotonic() - self._last_data_monotonic)
               if self._last_data_monotonic is not None else None)
        complete = bool(self.active_account and self.account_summary_complete.is_set()
                        and self.account_download_complete.is_set())
        if self.connection_state == "connecting":
            return "connecting", age, complete
        if self.connection_state != "connected":
            return "disconnected", age, complete
        if not complete:
            return "synchronizing", age, complete
        return ("current" if age is not None and age < STALE_AFTER_SECONDS else "stale"), age, complete

    def _add_message(self, level: str, code: int, message: str) -> None:
        with self.lock:
            self.recent_messages.append(
                {"level": level, "code": code, "message": message, "at": utc_now()}
            )
            self.recent_messages = self.recent_messages[-12:]

    def _queue_contract_details(self, contract: Contract) -> None:
        con_id = int(getattr(contract, "conId", 0) or 0)
        if con_id <= 0:
            return
        with self.lock:
            if (
                con_id in self.contract_metadata
                or con_id in self.contract_detail_pending
                or con_id in self.contract_detail_failed
            ):
                return
            self.contract_detail_pending.add(con_id)
        request_contract = Contract()
        request_contract.conId = con_id
        request_contract.secType = getattr(contract, "secType", "") or ""
        request_contract.currency = getattr(contract, "currency", "") or ""
        request_contract.exchange = (
            getattr(contract, "exchange", "")
            or ("SMART" if request_contract.secType in {"STK", "OPT", "IOPT", "CFD", "FUND", "WAR", "BAG"} else getattr(contract, "primaryExchange", ""))
            or "SMART"
        )
        self.contract_detail_queue.put(request_contract)

    def _contract_metadata_worker(self) -> None:
        while not self.stop_event.is_set():
            try:
                contract = self.contract_detail_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            con_id = int(contract.conId or 0)
            if not self.ready.wait(timeout=1.0):
                self.contract_detail_queue.put(contract)
                self.stop_event.wait(1.0)
                continue
            with self.lock:
                if con_id in self.contract_metadata or con_id in self.contract_detail_failed:
                    self.contract_detail_pending.discard(con_id)
                    continue
                request_id = self._next_contract_detail_request_id
                self._next_contract_detail_request_id += 1
                self.contract_detail_requests[request_id] = con_id
            try:
                self.reqContractDetails(request_id, contract)
            except Exception as error:
                with self.lock:
                    self.contract_detail_requests.pop(request_id, None)
                    self.contract_detail_pending.discard(con_id)
                    self.contract_detail_failed.add(con_id)
                self._add_message("error", 0, f"Metadati contratto {con_id}: {error}")
            self.stop_event.wait(0.25)

    def _store_contract_details(self, request_id: int, contract_details) -> None:
        contract = contract_details.contract
        con_id = int(contract.conId or self.contract_detail_requests.get(request_id, 0) or 0)
        if con_id <= 0:
            return
        identifiers = security_identifiers(contract_details)
        country_code, country_source = issuer_country_from_details(contract_details)
        underlying_con_id = int(getattr(contract_details, "underConId", 0) or 0)
        description = (
            getattr(contract, "description", "")
            or getattr(contract_details, "longName", "")
            or contract.localSymbol
            or contract.symbol
            or str(con_id)
        )
        metadata = {
            "conId": con_id,
            "description": description,
            "longName": getattr(contract_details, "longName", "") or "",
            "securityType": contract.secType or "",
            "securityTypeLabel": SECURITY_TYPES.get(contract.secType, contract.secType or "Altro"),
            "assetClass": investment_asset_class(contract_details),
            "stockType": getattr(contract_details, "stockType", "") or "",
            "bondType": getattr(contract_details, "bondType", "") or "",
            "industry": getattr(contract_details, "industry", "") or "",
            "category": getattr(contract_details, "category", "") or "",
            "subcategory": getattr(contract_details, "subcategory", "") or "",
            "issuerId": getattr(contract, "issuerId", "") or "",
            "issuerCountryCode": country_code,
            "issuerContinent": COUNTRY_CONTINENT_BY_CODE.get(country_code, ""),
            "issuerCountrySource": country_source,
            "securityIdentifiers": identifiers,
            "underlyingConId": underlying_con_id,
            "underlyingSymbol": getattr(contract_details, "underSymbol", "") or contract.symbol or "",
            "underlyingSecurityType": getattr(contract_details, "underSecType", "") or "",
            "updatedAt": utc_now(),
        }
        with self.lock:
            current = self.contract_metadata.get(con_id, {})
            self.contract_metadata[con_id] = {
                **current,
                **{key: value for key, value in metadata.items() if value != "" and value is not None},
            }
            self.contract_detail_failed.discard(con_id)
            self._touch()
        if underlying_con_id > 0 and underlying_con_id != con_id:
            underlying_contract = Contract()
            underlying_contract.conId = underlying_con_id
            underlying_contract.secType = metadata["underlyingSecurityType"]
            underlying_contract.exchange = "SMART"
            self._queue_contract_details(underlying_contract)

    def contractDetails(self, reqId: int, contractDetails):
        self._store_contract_details(reqId, contractDetails)

    def bondContractDetails(self, reqId: int, contractDetails):
        self._store_contract_details(reqId, contractDetails)

    def contractDetailsEnd(self, reqId: int):
        with self.lock:
            con_id = self.contract_detail_requests.pop(reqId, 0)
            self.contract_detail_pending.discard(con_id)
            if con_id and con_id not in self.contract_metadata:
                self.contract_detail_failed.add(con_id)

    def nextValidId(self, orderId: int):
        with self.lock:
            self.connection_state = "connected"
            self.connection_message = f"TWS {self.environment_label} collegata in lettura"
            self._touch()
        self.ready.set()
        self.reqManagedAccts()
        self.reqAccountSummary(9101, "All", ACCOUNT_SUMMARY_TAGS)
        self.reqPositions()

    def managedAccounts(self, accountsList: str):
        accounts = [account.strip() for account in accountsList.split(",") if account.strip()]
        with self.lock:
            self.accounts = accounts
            self.active_account = accounts[0] if accounts else ""
            self._touch()
        if self.active_account and self._subscribed_account != self.active_account:
            if self._subscribed_account:
                self.reqAccountUpdates(False, self._subscribed_account)
            self._subscribed_account = self.active_account
            self.reqAccountUpdates(True, self.active_account)

    def accountSummary(self, reqId: int, account: str, tag: str, value: str, currency: str):
        with self.lock:
            account_data = self.account_summary.setdefault(account, {})
            account_data[tag] = {"value": as_number(value), "currency": currency}
            self._touch()

    def accountSummaryEnd(self, reqId: int):
        with self.lock:
            if reqId == 9101 and self.connection_state == "connected":
                self.account_summary_complete.set()

    def updateAccountValue(self, key: str, val: str, currency: str, accountName: str):
        with self.lock:
            account_data = self.account_values.setdefault(accountName, {})
            storage_key = f"{key}|{currency or 'BASE'}"
            account_data[storage_key] = {
                "key": key,
                "value": as_number(val),
                "currency": currency,
            }
            self._touch()
            self._touch_data(accountName)

    def updatePortfolio(
        self,
        contract: Contract,
        position: float,
        marketPrice: float,
        marketValue: float,
        averageCost: float,
        unrealizedPNL: float,
        realizedPNL: float,
        accountName: str,
    ):
        position_key = f"{accountName}:{contract.conId}"
        with self.lock:
            if float(position) == 0:
                self.positions.pop(position_key, None)
            else:
                symbol = contract.localSymbol or contract.symbol or str(contract.conId)
                self.positions[position_key] = {
                    "account": accountName,
                    "conId": contract.conId,
                    "symbol": symbol,
                    "underlyingSymbol": contract.symbol or symbol,
                    "description": getattr(contract, "description", "") or symbol,
                    "securityType": contract.secType,
                    "securityTypeLabel": SECURITY_TYPES.get(contract.secType, contract.secType or "Altro"),
                    "currency": contract.currency or "",
                    "exchange": contract.primaryExchange or contract.exchange or "",
                    "expiry": contract.lastTradeDateOrContractMonth or "",
                    "strike": as_number(contract.strike),
                    "right": contract.right or "",
                    "multiplier": contract.multiplier or "",
                    "quantity": as_number(position),
                    "marketPrice": as_number(marketPrice),
                    "marketValue": as_number(marketValue),
                    "averageCost": as_number(averageCost),
                    "unrealizedPnl": as_number(unrealizedPNL),
                    "realizedPnl": as_number(realizedPNL),
                    "updatedAt": utc_now(),
                }
            self._touch()
            self._touch_data(accountName)
        if float(position) != 0:
            self._queue_contract_details(contract)

    def position(self, account: str, contract: Contract, position: float, avgCost: float):
        position_key = f"{account}:{contract.conId}"
        with self.lock:
            if float(position) == 0:
                self.positions.pop(position_key, None)
            elif position_key not in self.positions:
                symbol = contract.localSymbol or contract.symbol or str(contract.conId)
                self.positions[position_key] = {
                    "account": account,
                    "conId": contract.conId,
                    "symbol": symbol,
                    "underlyingSymbol": contract.symbol or symbol,
                    "description": getattr(contract, "description", "") or symbol,
                    "securityType": contract.secType,
                    "securityTypeLabel": SECURITY_TYPES.get(contract.secType, contract.secType or "Altro"),
                    "currency": contract.currency or "",
                    "exchange": contract.primaryExchange or contract.exchange or "",
                    "expiry": contract.lastTradeDateOrContractMonth or "",
                    "strike": as_number(contract.strike),
                    "right": contract.right or "",
                    "multiplier": contract.multiplier or "",
                    "quantity": as_number(position),
                    "marketPrice": 0.0,
                    "marketValue": 0.0,
                    "averageCost": as_number(avgCost),
                    "unrealizedPnl": 0.0,
                    "realizedPnl": 0.0,
                    "updatedAt": utc_now(),
                }
            self._touch()
        if float(position) != 0:
            self._queue_contract_details(contract)

    def updateAccountTime(self, timeStamp: str):
        with self.lock:
            self.last_account_time = timeStamp
            self._touch()
            self._touch_data(self.active_account)

    def accountDownloadEnd(self, accountName: str):
        with self.lock:
            if accountName != self.active_account or self.connection_state != "connected":
                return
            self.account_download_complete.set()
            self._touch_data(accountName)
            self._touch()

    def connectionClosed(self):
        with self.lock:
            self.connection_state = "disconnected"
            self.connection_message = f"Connessione TWS {self.environment_label} chiusa"
            self._subscribed_account = ""
        self.ready.clear()
        self.account_download_complete.clear()
        self.account_summary_complete.clear()

    def error(self, reqId: int, errorCode: int, errorString: str, *args):
        level = "info" if errorCode in INFORMATION_CODES else "error"
        self._add_message(level, errorCode, errorString)
        with self.lock:
            con_id = self.contract_detail_requests.pop(reqId, 0)
            if con_id and errorCode not in INFORMATION_CODES:
                self.contract_detail_pending.discard(con_id)
                self.contract_detail_failed.add(con_id)
        if errorCode in {502, 503, 504, 1100, 1300}:
            with self.lock:
                self.connection_state = "error"
                self.connection_message = errorString
                self.account_download_complete.clear()
                self.account_summary_complete.clear()
                self.ready.clear()
            # A fresh socket/session rebuilds subscriptions after connectivity loss.
            self.disconnect()

    def _metric(self, account: str, tag: str, default=0.0):
        summary = self.account_summary.get(account, {}).get(tag)
        if summary is not None:
            return summary.get("value", default)
        candidates = [
            value
            for value in self.account_values.get(account, {}).values()
            if value.get("key") == tag
        ]
        if not candidates:
            return default
        preferred = next(
            (value for value in candidates if value.get("currency") in {"BASE", ""}),
            candidates[0],
        )
        return preferred.get("value", default)

    def _base_currency(self, account: str) -> str:
        candidates: list[object] = []
        summary = self.account_summary.get(account, {})
        for tag in ("Currency", "NetLiquidation", "TotalCashValue"):
            item = summary.get(tag, {})
            candidates.extend((item.get("value"), item.get("currency")))
        for item in self.account_values.get(account, {}).values():
            if item.get("key") in {"Currency", "NetLiquidation", "TotalCashValue"}:
                candidates.extend((item.get("value"), item.get("currency")))
        for candidate in candidates:
            currency = str(candidate or "").upper()
            if len(currency) == 3 and currency != "BASE" and currency.isalpha():
                return currency
        return ""

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            account = self.active_account or (self.accounts[0] if self.accounts else "")
            base_currency = self._base_currency(account) if account else ""
            account_positions = [
                dict(position)
                for position in self.positions.values()
                if position.get("account") == account
            ]
            positions = []
            for position in account_positions:
                con_id = int(position.get("conId") or 0)
                metadata = self.contract_metadata.get(con_id, {})
                underlying_con_id = int(metadata.get("underlyingConId") or 0)
                underlying_metadata = self.contract_metadata.get(underlying_con_id, {})
                geography_metadata = (
                    underlying_metadata
                    if underlying_metadata.get("issuerCountryCode")
                    else metadata
                )
                security_type = str(metadata.get("securityType") or position.get("securityType") or "")
                enriched_position = {
                    **position,
                    "description": metadata.get("description") or position.get("description"),
                    "securityType": security_type,
                    "securityTypeLabel": metadata.get("securityTypeLabel") or SECURITY_TYPES.get(security_type, security_type or "Altro"),
                    "assetClass": metadata.get("assetClass") or "",
                    "stockType": metadata.get("stockType") or "",
                    "industry": metadata.get("industry") or "",
                    "category": metadata.get("category") or "",
                    "subcategory": metadata.get("subcategory") or "",
                    "issuerCountryCode": geography_metadata.get("issuerCountryCode") or "",
                    "issuerContinent": geography_metadata.get("issuerContinent") or "",
                    "issuerCountrySource": geography_metadata.get("issuerCountrySource") or "",
                    "securityIdentifiers": metadata.get("securityIdentifiers") or {},
                    "underlyingConId": underlying_con_id,
                    "underlyingDescription": underlying_metadata.get("description") or "",
                    "metadataStatus": (
                        "ready"
                        if con_id in self.contract_metadata
                        else "unavailable"
                        if con_id in self.contract_detail_failed
                        else "pending"
                    ),
                }
                positions.append(enriched_position)
            positions = sorted(
                positions,
                key=lambda item: abs(float(item.get("marketValue") or 0)),
                reverse=True,
            )
            metrics = {
                "netLiquidation": self._metric(account, "NetLiquidation"),
                "totalCash": self._metric(account, "TotalCashValue"),
                "settledCash": self._metric(account, "SettledCash"),
                "buyingPower": self._metric(account, "BuyingPower"),
                "availableFunds": self._metric(account, "AvailableFunds"),
                "excessLiquidity": self._metric(account, "ExcessLiquidity"),
                "maintenanceMargin": self._metric(account, "MaintMarginReq"),
                "grossPositionValue": self._metric(account, "GrossPositionValue"),
                "unrealizedPnl": self._metric(account, "UnrealizedPnL"),
                "realizedPnl": self._metric(account, "RealizedPnL"),
            }
            data_status, data_age, sync_complete = self._data_status()
            return {
                "environment": self.environment,
                "readOnlyBridge": True,
                "contractMetadataVersion": 1,
                "status": self.connection_state,
                "dataStatus": data_status,
                "lastDataUpdate": self.last_data_update,
                "dataAgeSeconds": data_age,
                "staleAfterSeconds": STALE_AFTER_SECONDS,
                "initialSyncComplete": sync_complete,
                "message": self.connection_message,
                "host": self.tws_host,
                "port": self.tws_port,
                "clientId": self.tws_client_id,
                "account": account,
                "accounts": list(self.accounts),
                "baseCurrency": base_currency,
                "metrics": metrics,
                "positions": positions,
                "positionCount": len(positions),
                "lastUpdate": self.last_update,
                "lastAccountTime": self.last_account_time,
                "messages": list(self.recent_messages),
            }


class DashboardHandler(BaseHTTPRequestHandler):
    clients: dict[str, IbkrAccountClient]

    def _read_json_body(self, maximum_size: int = 10 * 1024 * 1024) -> dict[str, object]:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Dimensione richiesta non valida") from error
        if content_length <= 0 or content_length > maximum_size:
            raise ValueError("Dimensione archivio non valida")
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("JSON non valido") from error
        if not isinstance(payload, dict):
            raise ValueError("Archivio non valido")
        return payload

    @staticmethod
    def _safe_archive_name(file_name: object) -> str:
        candidate = Path(str(file_name or "")).name.lower()
        if not ARCHIVE_FILE_PATTERN.fullmatch(candidate):
            raise ValueError("Nome archivio non valido")
        return candidate

    @staticmethod
    def _open_archive_picker() -> Path | None:
        script = """
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.InitialDirectory = $env:IBKR_ARCHIVE_DIR
$dialog.Filter = 'Archivi dashboard (*.json)|*.json'
$dialog.Title = 'Seleziona un archivio della dashboard'
$dialog.CheckFileExists = $true
$dialog.Multiselect = $false
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
  [Console]::Out.Write($dialog.FileName)
}
"""
        environment = os.environ.copy()
        environment["IBKR_ARCHIVE_DIR"] = str(SCRIPT_DIR)
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            text=True,
            timeout=300,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "Impossibile aprire il selettore file")
        selected = completed.stdout.strip()
        if not selected:
            return None
        selected_path = Path(selected).resolve()
        if selected_path.parent != SCRIPT_DIR.resolve() or selected_path.suffix.lower() != ".json":
            raise ValueError("Seleziona un file JSON presente nella cartella del progetto")
        return selected_path

    def _send_headers(self, status: int, content_type: str, length: int | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.end_headers()

    def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_headers(204, "text/plain", 0)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            origin = self.headers.get("Origin", "")
            if origin and not origin.startswith(("http://127.0.0.1:", "http://localhost:")):
                self._send_json({"error": "Richiesta non autorizzata"}, 403)
                return
            if path == "/api/archive/export":
                payload = self._read_json_body()
                file_name = self._safe_archive_name(payload.get("fileName"))
                archive = payload.get("archive")
                if not isinstance(archive, dict) or archive.get("format") != "portfolio-operations-archive":
                    raise ValueError("Contenuto archivio non valido")
                target = SCRIPT_DIR / file_name
                temporary = target.with_suffix(".json.tmp")
                temporary.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
                temporary.replace(target)
                self._send_json({"status": "saved", "fileName": file_name, "path": str(target)})
                return
            if path == "/api/archive/pick":
                selected_path = self._open_archive_picker()
                if selected_path is None:
                    self._send_json({"status": "cancelled"})
                    return
                if selected_path.stat().st_size > 10 * 1024 * 1024:
                    raise ValueError("Il file supera il limite di 10 MB")
                try:
                    archive = json.loads(selected_path.read_text(encoding="utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise ValueError("Il file selezionato non contiene JSON valido") from error
                self._send_json({"status": "selected", "fileName": selected_path.name, "archive": archive})
                return
            self._send_json({"error": "Risorsa non trovata"}, 404)
        except (ValueError, RuntimeError, OSError) as error:
            self._send_json({"error": str(error)}, 400)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in {"/api/paper/snapshot", "/api/live/snapshot"}:
            environment = "live" if path.startswith("/api/live/") else "paper"
            self._send_json(self.clients[environment].snapshot())
            return
        if path == "/api/health":
            snapshots = {
                environment: client.snapshot()
                for environment, client in self.clients.items()
            }
            self._send_json(
                {
                    "service": "ibkr-dashboard-bridge",
                    "status": "connected"
                    if any(item["status"] == "connected" for item in snapshots.values())
                    else "disconnected",
                    "readOnlyBridge": True,
                    "connections": {
                        environment: {
                            "status": item["status"],
                            "dataStatus": item["dataStatus"],
                            "lastDataUpdate": item["lastDataUpdate"],
                            "dataAgeSeconds": item["dataAgeSeconds"],
                            "port": item["port"],
                            "account": item["account"],
                        }
                        for environment, item in snapshots.items()
                    },
                }
            )
            return
        if path in {"/", "/salary-planner-react.html"}:
            if not DASHBOARD_FILE.exists():
                self._send_json({"error": "Dashboard non trovata"}, 404)
                return
            body = DASHBOARD_FILE.read_bytes()
            self._send_headers(200, "text/html; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        self._send_json({"error": "Risorsa non trovata"}, 404)

    def log_message(self, format: str, *args) -> None:
        if self.path.startswith("/api/") and getattr(self, "command", "") == "GET":
            return
        super().log_message(format, *args)


def wait_for_snapshot(client: IbkrAccountClient, timeout: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = client.snapshot()
        if snapshot["dataStatus"] == "current":
            return snapshot
        time.sleep(0.25)
    return client.snapshot()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ponte locale read-only tra TWS Live/Paper e la dashboard."
    )
    parser.add_argument("--tws-host", default="127.0.0.1")
    parser.add_argument("--live-port", type=int, default=7496)
    parser.add_argument("--paper-port", type=int, default=7497)
    parser.add_argument("--live-client-id", type=int, default=70)
    parser.add_argument("--paper-client-id", type=int, default=71)
    parser.add_argument("--http-port", type=int, default=8765)
    parser.add_argument("--test", action="store_true", help="Verifica TWS, stampa un riepilogo e termina.")
    parser.add_argument(
        "--test-environment",
        choices=("live", "paper", "both"),
        default="both",
        help="Sceglie quale collegamento verificare con --test.",
    )
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    clients = {
        "live": IbkrAccountClient(
            args.tws_host,
            args.live_port,
            args.live_client_id,
            "LIVE",
        ),
        "paper": IbkrAccountClient(
            args.tws_host,
            args.paper_port,
            args.paper_client_id,
            "PAPER",
        ),
    }

    if args.test:
        selected = (
            clients
            if args.test_environment == "both"
            else {args.test_environment: clients[args.test_environment]}
        )
        snapshots: dict[str, dict[str, object]] = {}
        for environment, client in selected.items():
            client.start()
            snapshots[environment] = wait_for_snapshot(client, timeout=15)
        print(json.dumps(snapshots, ensure_ascii=False, indent=2))
        for client in selected.values():
            client.stop()
        return 0 if all(
            snapshot["dataStatus"] == "current"
            for snapshot in snapshots.values()
        ) else 1

    for client in clients.values():
        client.start()
    DashboardHandler.clients = clients
    server = ThreadingHTTPServer(("127.0.0.1", args.http_port), DashboardHandler)
    dashboard_url = f"http://127.0.0.1:{args.http_port}/"
    print("IBKR Dashboard Bridge avviato in modalita' sola lettura.")
    print(f"TWS Live:  {args.tws_host}:{args.live_port}")
    print(f"TWS Paper: {args.tws_host}:{args.paper_port}")
    print(f"Dashboard: {dashboard_url}")
    print("Puoi tenere aperta una sola sessione o entrambe: il bridge si ricollega automaticamente.")
    print("Premi Ctrl+C per chiudere il collegamento.")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(dashboard_url)).start()

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        for client in clients.values():
            client.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only bid/ask streams and explicitly labelled liquidation estimates."""
from copy import copy
from datetime import datetime, timezone
import math
import threading
import time

STALE_QUOTE_SECONDS = 3600
FROZEN_FALLBACK_SECONDS = 30
FROZEN_TIMEOUT_SECONDS = 60
SUPPORTED = {"STK", "OPT", "FUT", "FOP"}
DATA_TYPES = {1: "live", 2: "frozen", 3: "delayed", 4: "delayed-frozen"}


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def valuation(position, quote, now=None):
    quantity = finite(position.get("quantity"))
    kind = position.get("securityType")
    multiplier = 1.0 if kind == "STK" else finite(position.get("multiplier"))
    cost = finite(position.get("averageCost"))
    supported = kind in SUPPORTED and multiplier is not None and multiplier > 0
    side = "bid" if quantity is not None and quantity > 0 else "ask"
    tick = quote.get(side, {})
    price = finite(tick.get("price"))
    stamp = finite(tick.get("monotonic"))
    age = max(0, (time.monotonic() if now is None else now) - stamp) if stamp is not None else None
    data_type = DATA_TYPES.get(quote.get("type"), "unknown")
    valid_price = price is not None and price > 0
    status = "ready" if valid_price and data_type != "unknown" else ("pending" if not quote or quote.get("status") == "pending" else "unavailable")
    if not supported:
        status = "unsupported"
    elif quote.get("disconnected"):
        status = "disconnected"
    elif valid_price and (age is None or age >= STALE_QUOTE_SECONDS):
        status = "stale"
    elif valid_price and data_type == "unknown":
        status = "unknown"
    can_estimate = status == "ready" and quantity is not None and quantity != 0 and cost is not None
    pnl = quantity * (price * multiplier - cost) if can_estimate else None
    last_known_pnl = quantity * (price * multiplier - cost) if status == "stale" and supported and data_type != "unknown" and quantity is not None and quantity != 0 and cost is not None else None
    return {"averageEntryPrice": cost / multiplier if supported and cost is not None else None,
            "liquidationSide": side.upper(), "liquidationPrice": price if valid_price else None,
            "liquidationPnl": pnl, "liquidationLastKnownPnl": last_known_pnl, "liquidationStatus": status,
            "liquidationDataType": data_type, "liquidationReason": quote.get("reason", ""),
            "liquidationReceivedAt": tick.get("receivedAt"), "liquidationAgeSeconds": age}


class LiquidationMonitor:
    def __init__(self, owner):
        self.owner = owner
        self.contracts = {}
        self.quotes = {}
        self.requests = {}
        self.next_id = 52000
        self.thread = None

    def start(self):
        if self.owner.environment != "LIVE" or self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="ibkr-liquidation-quotes", daemon=True)
        self.thread.start()

    def reset(self):
        with self.owner.lock:
            self.contracts.clear()
            self.quotes.clear()
            self.requests.clear()

    def track(self, contract):
        if self.owner.environment == "LIVE" and contract.conId > 0:
            with self.owner.lock:
                self.contracts[contract.conId] = contract

    def quote(self, position):
        result = dict(self.quotes.get(position.get("conId"), {}))
        result["disconnected"] = not self.owner.ready.is_set() or not self.owner.isConnected()
        return result

    def _run(self):
        while not self.owner.stop_event.is_set():
            if self.owner.ready.is_set() and self.owner.isConnected():
                self._subscriptions()
            self.owner.stop_event.wait(1)

    def _subscriptions(self):
        with self.owner.lock:
            active = {p.get("conId") for p in self.owner.positions.values() if p.get("quantity")}
            now = time.monotonic()
            for con_id in active:
                q = self.quotes.get(con_id, {})
                requested = q.get("requestedAt", now)
                latest = max(q.get(side, {}).get("monotonic", -1) for side in ("bid", "ask"))
                if q.get("requestedType") == 4 and now - requested >= FROZEN_TIMEOUT_SECONDS and latest < requested:
                    q.update(status="unavailable", reason="noquotes")
            def frozen_fallback(con_id):
                q = self.quotes.get(con_id, {})
                requested = q.get("requestedAt", now)
                latest = max(q.get(side, {}).get("monotonic", -1) for side in ("bid", "ask"))
                return q.get("requestedType", 3) == 3 and now - requested >= FROZEN_FALLBACK_SECONDS and latest < requested
            def needs_refresh(con_id):
                q = self.quotes.get(con_id, {})
                if q.get("reason") == "permissions":
                    return False
                return frozen_fallback(con_id) or now - q.get("requestedAt", now) >= STALE_QUOTE_SECONDS
            removed = [(req, con_id) for req, con_id in self.requests.items() if con_id not in active or needs_refresh(con_id)]
            frozen_contracts = {con_id for _, con_id in removed if frozen_fallback(con_id)}
            for req, con_id in removed:
                self.requests.pop(req, None)
                if con_id not in active:
                    self.quotes.pop(con_id, None)
            contracts = [c for c in self.contracts.values() if c.conId in active and c.conId not in self.requests.values() and c.secType in SUPPORTED]
        for req, _ in removed:
            try:
                self.owner.cancelMktData(req)
            except Exception:
                pass
        for contract in contracts:
            if self.owner.stop_event.is_set() or not self.owner.ready.is_set():
                break
            with self.owner.lock:
                if len(self.requests) >= 90:
                    self.quotes[contract.conId] = {"status": "unavailable", "reason": "limit"}
                    continue
                request_id = self.next_id
                self.next_id += 1
                self.requests[request_id] = contract.conId
                # Retain the last quote with its original receipt time while
                # refreshing a silent stream; never make an old tick look new.
                q = self.quotes.setdefault(contract.conId, {})
                request_type = 4 if contract.conId in frozen_contracts else 3
                q.update(status="pending", requestedAt=time.monotonic(), requestedType=request_type)
                q.pop("reason", None)
                metadata = self.owner.contract_metadata.get(contract.conId, {})
            request_contract = copy(contract)
            # Position callbacks report the listing venue, not necessarily an
            # entitled direct feed. SMART retains the exact stock conId and
            # primaryExchange while allowing IBKR's authorized delayed quotes.
            request_contract.exchange = "SMART" if contract.secType == "STK" else getattr(contract, "exchange", "") or metadata.get("exchange") or "SMART"
            try:
                # IBKR automatically supplies live quotes if entitled; otherwise
                # request its free delayed stream, labelled as delayed in the UI.
                # Streaming requests do not buy regulatory snapshots/subscriptions.
                with self.owner.lock:
                    self.owner.reqMarketDataType(request_type)
                    self.owner.reqMktData(request_id, request_contract, "", False, False, [])
            except Exception:
                self.failed(request_id, "unavailable")
            self.owner.stop_event.wait(0.25)

    def data_type(self, request_id, kind):
        if kind not in DATA_TYPES:
            return
        with self.owner.lock:
            con_id = self.requests.get(request_id)
            if con_id is None:
                return
            q = self.quotes.setdefault(con_id, {})
            if q.get("type") is not None and q["type"] != kind:
                q.pop("bid", None)
                q.pop("ask", None)
            q["type"] = kind

    def price(self, request_id, tick_type, value):
        side = {1: "bid", 2: "ask", 66: "bid", 67: "ask"}.get(tick_type)
        if not side:
            return
        with self.owner.lock:
            con_id = self.requests.get(request_id)
            if con_id is None:
                return
            q = self.quotes.setdefault(con_id, {})
            if tick_type in {66, 67}:
                if q.get("type") not in {3, 4}:
                    q.pop("bid", None)
                    q.pop("ask", None)
                q["type"] = 4 if q.get("type") == 4 else 3
            elif q.get("type") in {3, 4}:
                # Do not silently label normal ticks live without marketDataType.
                q.pop("bid", None)
                q.pop("ask", None)
                q["type"] = None
            number = finite(value)
            if number is None or number <= 0:
                q.pop(side, None)
                return
            now = time.monotonic()
            previous = q.get(side, {}).get("monotonic")
            # Sample each side hourly, not on every streaming tick. A fresh
            # subscription may populate immediately; invalid ticks still clear it.
            if previous is not None and previous >= q.get("requestedAt", -1) and now - previous < STALE_QUOTE_SECONDS:
                return
            q[side] = {"price": number, "receivedAt": datetime.now(timezone.utc).isoformat(), "monotonic": now}
            q["status"] = "ready"
            q.pop("reason", None)

    def failed(self, request_id, reason=""):
        with self.owner.lock:
            con_id = self.requests.get(request_id)
            if con_id is not None:
                self.quotes[con_id] = {"status": "unavailable", "reason": reason}

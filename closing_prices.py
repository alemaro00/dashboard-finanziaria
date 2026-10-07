"""Completed regular-session stock closes; no bid/ask or streaming requests."""
from copy import copy
from datetime import datetime, timedelta, timezone
import math
import threading
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REFRESH_SECONDS = 3600


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def completed_through(metadata, now=None):
    """Include today's bar only after every RTH segment ends (+20m publication).

    The exchange timezone, not Rome or TWS's login timezone, determines dates.
    Without a usable schedule, conservatively exclude today's partial bar.
    """
    now = now or datetime.now(timezone.utc)
    try:
        zone = ZoneInfo(metadata.get("timeZoneId") or "")
    except (ZoneInfoNotFoundError, ValueError):
        return None
    local = now.astimezone(zone)
    today = local.date()
    prior = today - timedelta(days=1)
    stamp = today.strftime("%Y%m%d")
    sessions = [s for s in str(metadata.get("liquidHours", "")).split(";") if s.startswith(stamp + ":")]
    if not sessions:
        return prior
    ends = []
    try:
        for session in sessions:
            hours = session.split(":", 1)[1]
            if hours == "CLOSED":
                continue
            for segment in hours.split(","):
                end = segment.split("-", 1)[1]
                if ":" not in end:
                    end = stamp + ":" + end
                ends.append(datetime.strptime(end, "%Y%m%d:%H%M").replace(tzinfo=zone))
    except (ValueError, IndexError):
        return prior
    return today if ends and local >= max(ends) + timedelta(minutes=20) else prior


def valuation(position, quote):
    quantity = finite(position.get("quantity"))
    cost = finite(position.get("averageCost"))
    price = finite(quote.get("price"))
    supported = position.get("securityType") == "STK"
    valid = supported and price is not None and price > 0 and bool(quote.get("date"))
    pnl = quantity * (price - cost) if valid and quantity and cost is not None else None
    return {"averageEntryPrice": cost if supported else None,
            "closingPrice": price if valid else None, "closingDate": quote.get("date") if valid else None,
            "closingPnl": pnl, "closingStatus": quote.get("status", "pending") if supported else "unsupported",
            "closingReason": quote.get("reason", ""), "closingCheckedAt": quote.get("checkedAt")}


class ClosingPriceMonitor:
    def __init__(self, owner):
        self.owner = owner
        self.contracts = {}
        self.quotes = {}
        self.requests = {}
        self.next_id = 3000000
        self.generation = 0
        self.thread = None

    def start(self):
        if self.owner.environment != "LIVE" or self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="ibkr-closing-prices", daemon=True)
        self.thread.start()

    def reset(self):
        with self.owner.lock:
            self.generation += 1
            for request in self.requests.values():
                request["event"].set()
            self.requests.clear()
            self.contracts.clear()
            self.quotes.clear()

    def track(self, contract):
        if self.owner.environment == "LIVE" and contract.conId > 0:
            with self.owner.lock:
                self.contracts[contract.conId] = copy(contract)

    def quote(self, position):
        return dict(self.quotes.get(position.get("conId"), {}))

    def _run(self):
        while not self.owner.stop_event.is_set():
            if self.owner.ready.is_set() and self.owner.isConnected() and self.owner.account_download_complete.is_set():
                self._update()
            self.owner.stop_event.wait(10)

    def _update(self):
        with self.owner.lock:
            generation = self.generation
            active = {p.get("conId") for p in self.owner.positions.values()
                      if p.get("account") == self.owner.active_account and p.get("quantity")}
            self.quotes = {key: q for key, q in self.quotes.items() if key in active}
            contracts = [copy(c) for key, c in self.contracts.items() if key in active and c.secType == "STK"]
        for contract in contracts:
            if self.owner.stop_event.is_set() or generation != self.generation or not self.owner.ready.is_set():
                return
            with self.owner.lock:
                metadata = dict(self.owner.contract_metadata.get(contract.conId, {}))
                cached = self.quotes.get(contract.conId, {})
                if time.monotonic() - cached.get("checkedMonotonic", -REFRESH_SECONDS) < REFRESH_SECONDS:
                    continue
            cutoff = completed_through(metadata)
            if cutoff is None:  # Wait for actual exchange metadata; never guess by currency.
                continue
            self._request(contract, cutoff, generation)

    def _request(self, contract, cutoff, generation):
        with self.owner.lock:
            request_id = self.next_id
            self.next_id += 1
            request = {"prices": {}, "event": threading.Event(), "reason": ""}
            self.requests[request_id] = request
        request_contract = copy(contract)
        request_contract.exchange = "SMART"
        try:
            with self.owner.lock:
                # TRADES is split-adjusted, not dividend-adjusted ADJUSTED_LAST.
                # Completed RTH daily bars only; no paid snapshot or subscription.
                self.owner.reqMarketDataType(3)
                self.owner.reqHistoricalData(request_id, request_contract, "", "2 W", "1 day", "TRADES", 1, 1, False, [])
            deadline = time.monotonic() + 45
            while not request["event"].wait(0.25):
                if self.owner.stop_event.is_set() or generation != self.generation or time.monotonic() >= deadline:
                    request["reason"] = "timeout"
                    break
            dates = [day for day in request["prices"] if day <= cutoff]
            result = {"status": "unavailable", "reason": request["reason"] or "nohistory"}
            if not request["reason"] and dates:
                latest = max(dates)
                result = {"status": "ready", "price": request["prices"][latest], "date": latest.isoformat()}
            with self.owner.lock:
                if generation == self.generation:
                    self.quotes[contract.conId] = {**result, "checkedAt": datetime.now(timezone.utc).isoformat(),
                                                   "checkedMonotonic": time.monotonic()}
        except Exception:
            with self.owner.lock:
                if generation == self.generation:
                    self.quotes[contract.conId] = {"status": "unavailable", "reason": "request",
                                                   "checkedMonotonic": time.monotonic()}
        finally:
            with self.owner.lock:
                self.requests.pop(request_id, None)
            if not request["event"].is_set() or generation != self.generation:
                try:
                    self.owner.cancelHistoricalData(request_id)
                except Exception:
                    pass
        self.owner.stop_event.wait(1)

    def bar(self, request_id, bar):
        with self.owner.lock:
            request = self.requests.get(request_id)
            if request is None:
                return
            try:
                day = datetime.strptime(str(bar.date), "%Y%m%d").date()
                price = finite(bar.close)
                if price is None or price <= 0:
                    raise ValueError("invalid close")
                request["prices"][day] = price
            except (ValueError, TypeError):
                request["reason"] = "invalid"

    def end(self, request_id):
        with self.owner.lock:
            request = self.requests.get(request_id)
            if request is not None:
                request["event"].set()

    def failed(self, request_id, code, message):
        if code in {2188, 10167}:
            return
        with self.owner.lock:
            request = self.requests.get(request_id)
            if request is not None:
                permission = code in {354, 10089, 10186} or "permission" in message.lower() or "not subscribed" in message.lower()
                request["reason"] = "permissions" if permission else "nohistory"
                request["event"].set()

"""Read-only historical data and normal, one-day, 95% risk of current holdings."""
from copy import copy
from datetime import date, datetime, timedelta
import math
from statistics import NormalDist, mean, stdev
import threading
import time
from zoneinfo import ZoneInfo

from ibapi.contract import Contract

CONFIDENCE = 0.95
MAX_SERIES = 50


def positive(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (ValueError, TypeError):
        return None


def cutoff(today, years):
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


def normal_risk(components, nav, today=None):
    """Components have signed EUR exposure and adjusted EUR price histories.

    Daily scenario P/L is the sum of exposure * return on aligned dates, so
    covariance, short positions and FX are included without summing asset VaRs.
    Historical weights are hypothetical current constant weights, not actual
    historical holdings. Missing dates are not filled or silently dropped.
    """
    today = today or datetime.now(ZoneInfo("Europe/Rome")).date()
    base = {"confidence": CONFIDENCE, "horizonDays": 1, "distribution": "normal", "currency": "EUR",
            "scope": "current-ibkr", "var95": None, "es95": None}
    if not positive(nav):
        return {**base, "status": "unavailable", "message": "Valore netto IBKR non disponibile o non positivo."}
    if not components:
        return {**base, "status": "ready", "var95": 0.0, "es95": 0.0, "observations": 0, "years": 0,
                "message": "Solo liquidità EUR: rischio di mercato nullo nel modello, esclusi gli altri rischi."}
    for item in components:
        if not math.isfinite(item["exposure"]):
            return {**base, "status": "unavailable", "message": "Esposizione non valida."}
        if any(not isinstance(day, date) or not positive(price) for day, price in item["prices"].items()):
            return {**base, "status": "unavailable", "message": "Prezzi storici non validi."}
    common = set.intersection(*(set(item["prices"]) for item in components))
    completed = sorted(day for day in common if day < today)
    if not completed or (today - completed[-1]).days > 7:
        return {**base, "status": "unavailable", "message": "Storico assente o non aggiornato per tutte le esposizioni."}
    for years in (10, 5):
        start = cutoff(today, years)
        # One prior price is needed to measure the first day's return.
        prior = [day for day in completed if day <= start]
        days = ([prior[-1]] if prior else []) + [day for day in completed if day > start]
        if len(days) < years * 200 + 1 or days[0] > start + timedelta(days=10):
            continue
        if any((b - a).days > 10 for a, b in zip(days, days[1:])):
            continue
        pnl = [sum(item["exposure"] * (item["prices"][b] / item["prices"][a] - 1)
                   for item in components) for a, b in zip(days, days[1:])]
        mu, sigma = mean(pnl), stdev(pnl)
        z = NormalDist().inv_cdf(CONFIDENCE)
        var = z * sigma - mu
        es = sigma * math.exp(-z * z / 2) / math.sqrt(2 * math.pi) / (1 - CONFIDENCE) - mu
        if not all(math.isfinite(x) for x in (mu, sigma, var, es)):
            return {**base, "status": "unavailable", "message": "Calcolo numerico non valido."}
        return {**base, "status": "ready", "var95": var, "es95": es,
                "varPct": var / nav * 100, "esPct": es / nav * 100,
                "meanDailyPnl": mu, "dailyPnlStdDev": sigma, "years": years,
                "observations": len(pnl), "startDate": days[0].isoformat(), "endDate": days[-1].isoformat(),
                "message": "Pesi attuali costanti; ipotesi normale, non una previsione garantita."}
    return {**base, "status": "unavailable", "message": "Storico comune insufficiente: servono almeno cinque anni completi."}


class PortfolioRiskMonitor:
    def __init__(self, owner):
        self.owner = owner
        self.contracts = {}
        self.cache = {}
        self.requests = {}
        self.next_id = 2000000
        self.generation = 0
        self.thread = None
        self.result_signature = None
        self.result = self.unavailable("Collega TWS per calcolare il rischio delle posizioni attuali.")

    @staticmethod
    def unavailable(message, status="unavailable"):
        return {"confidence": CONFIDENCE, "horizonDays": 1, "distribution": "normal", "currency": "EUR",
                "var95": None, "es95": None, "status": status, "message": message}

    def start(self):
        if self.owner.environment != "LIVE" or self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="ibkr-portfolio-risk", daemon=True)
        self.thread.start()

    def reset(self):
        with self.owner.lock:
            self.generation += 1
            self.contracts.clear()
            self.cache.clear()
            for request in self.requests.values():
                request["error"] = "Collegamento TWS interrotto."
                request["event"].set()
            self.requests.clear()
            self.result = self.unavailable("In attesa del collegamento TWS.", "pending")
            self.result_signature = None

    def track(self, contract):
        if self.owner.environment == "LIVE" and contract.conId > 0:
            with self.owner.lock:
                self.contracts[contract.conId] = copy(contract)

    def snapshot(self):
        result = dict(self.result)
        if not self.owner.ready.is_set() or not self.owner.isConnected():
            return self.unavailable("TWS disconnessa: stima sospesa.")
        if result.get("status") == "ready" and self.result_signature != self._signature():
            return self.unavailable("Posizioni o liquidità cambiate: ricalcolo della stima in corso.", "pending")
        return result

    def _signature(self):
        with self.owner.lock:
            account = self.owner.active_account
            holdings = sorted((int(p.get("conId") or 0), float(p.get("quantity") or 0), p.get("currency", ""), p.get("securityType", ""))
                              for p in self.owner.positions.values() if p.get("account") == account and p.get("quantity"))
            cash = sorted((str(v.get("currency")), float(v.get("value") or 0)) for v in self.owner.account_values.get(account, {}).values()
                          if str(v.get("key", "")).removeprefix("$LEDGER-") == "CashBalance" and v.get("currency") != "BASE")
            return account, tuple(holdings), tuple(cash)

    def _inputs(self):
        with self.owner.lock:
            account = self.owner.active_account
            positions = [dict(p) for p in self.owner.positions.values() if p.get("account") == account and p.get("quantity")]
            values = list(self.owner.account_values.get(account, {}).values())
            rates = {str(v.get("currency")): float(v.get("value") or 0) for v in values
                     if str(v.get("key", "")).removeprefix("$LEDGER-") == "ExchangeRate"}
            rates["EUR"] = 1.0
            cash = [(str(v.get("currency")), float(v.get("value") or 0)) for v in values
                    if str(v.get("key", "")).removeprefix("$LEDGER-") == "CashBalance" and v.get("currency") not in (None, "BASE")]
            return positions, cash, rates, self.owner._metric(account, "NetLiquidation"), self.owner._base_currency(account)

    def _run(self):
        while not self.owner.stop_event.is_set():
            if self.owner.ready.is_set() and self.owner.isConnected() and self.owner.account_download_complete.is_set():
                try:
                    self._update()
                except Exception:
                    with self.owner.lock:
                        self.result = self.unavailable("Impossibile completare lo storico IBKR.")
            self.owner.stop_event.wait(10)

    def _update(self):
        today = datetime.now(ZoneInfo("Europe/Rome")).date()
        with self.owner.lock:
            generation = self.generation
            signature = self._signature()
            positions, cash, rates, nav, currency = self._inputs()
        if currency != "EUR":
            self.result = self.unavailable("Il modello richiede la valuta base IBKR EUR.")
            return
        if not cash:
            self.result = self.unavailable("Liquidità per valuta ancora non disponibile.", "pending")
            return
        if any(p.get("securityType") != "STK" for p in positions):
            self.result = self.unavailable("Modello disponibile per azioni/ETF e liquidità; presenti strumenti non supportati.")
            return
        currencies = {p.get("currency") for p in positions} | {c for c, amount in cash if amount != 0}
        if any(not c or len(c) != 3 or not positive(rates.get(c)) for c in currencies):
            self.result = self.unavailable("Cambio corrente EUR mancante per una delle esposizioni.")
            return
        if len(positions) + len(currencies - {"EUR"}) > MAX_SERIES:
            self.result = self.unavailable("Troppe serie storiche: nessuna posizione è stata esclusa dal calcolo.")
            return
        components = []
        for p in positions:
            if not positive(p.get("marketPrice")):
                self.result = self.unavailable("Prezzo della posizione non disponibile.", "pending")
                return
            with self.owner.lock:
                contract = self.contracts.get(p["conId"])
            if contract is None:
                self.result = self.unavailable("Contratto IBKR non ancora disponibile.", "pending")
                return
            record = self._history(("stock", p["conId"]), contract, "ADJUSTED_LAST", today, generation)
            if record.get("error"):
                self.result = self.unavailable(record["error"])
                return
            prices = record["prices"]
            if p["currency"] != "EUR":
                fx = self._fx(p["currency"], today, generation)
                if fx.get("error"):
                    self.result = self.unavailable(fx["error"])
                    return
                prices = {day: price * fx["prices"][day] for day, price in prices.items() if day in fx["prices"]}
            components.append({"exposure": float(p["quantity"]) * float(p["marketPrice"]) * rates[p["currency"]], "prices": prices})
        for c, amount in cash:
            if c == "EUR" or amount == 0:
                continue
            fx = self._fx(c, today, generation)
            if fx.get("error"):
                self.result = self.unavailable(fx["error"])
                return
            components.append({"exposure": amount * rates[c], "prices": fx["prices"]})
        result = normal_risk(components, nav, today)
        with self.owner.lock:
            if generation == self.generation and signature == self._signature():
                self.result = {**result, "computedAt": datetime.now(ZoneInfo("Europe/Rome")).isoformat()}
                self.result_signature = signature

    def _fx(self, currency, today, generation):
        contract = Contract()
        contract.symbol, contract.currency, contract.secType, contract.exchange = "EUR", currency, "CASH", "IDEALPRO"
        record = self._history(("fx", currency), contract, "MIDPOINT", today, generation)
        return {**record, "prices": {day: 1 / price for day, price in record.get("prices", {}).items()}}

    def _history(self, key, contract, what, today, generation):
        with self.owner.lock:
            self.cache = {cache_key: value for cache_key, value in self.cache.items() if cache_key[1] == today}
            cached = self.cache.get((key, today))
            if cached is not None:
                return cached
            self.result = self.unavailable("Caricamento dello storico giornaliero IBKR (10 anni, oppure 5).", "pending")
        result = {"error": "Storico IBKR non disponibile.", "prices": {}}
        for years in (10, 5):
            if self.owner.stop_event.is_set() or generation != self.generation:
                return result
            request_contract = copy(contract)
            # Position callbacks carry the listing venue, whose direct feed may
            # be unavailable even when IBKR authorizes SMART history. Preserve
            # conId/currency/primaryExchange: never substitute a security.
            request_contract.exchange = "SMART" if key[0] == "stock" else request_contract.exchange or "SMART"
            with self.owner.lock:
                request_id = self.next_id
                self.next_id += 1
                request = {"prices": {}, "event": threading.Event(), "error": ""}
                self.requests[request_id] = request
            try:
                # End date empty is required for ADJUSTED_LAST; no paid snapshot.
                with self.owner.lock:
                    # No subscription or paid snapshot; serialize mode+request.
                    self.owner.reqMarketDataType(3)
                    self.owner.reqHistoricalData(request_id, request_contract, "", f"{years} Y", "1 day", what, 1, 1, False, [])
                deadline = time.monotonic() + 45
                while not request["event"].wait(0.25):
                    if self.owner.stop_event.is_set() or generation != self.generation or time.monotonic() >= deadline:
                        request["error"] = "Timeout nel caricamento dello storico IBKR."
                        break
                result = {"prices": dict(request["prices"]), "error": request["error"]}
            except Exception:
                result = {"prices": {}, "error": "Richiesta dello storico IBKR non riuscita."}
            finally:
                with self.owner.lock:
                    self.requests.pop(request_id, None)
                if not request["event"].is_set() or generation != self.generation:
                    try:
                        self.owner.cancelHistoricalData(request_id)
                    except Exception:
                        pass
            if (not result["error"] and result["prices"]) or "Permessi" in result["error"]:
                break
            self.owner.stop_event.wait(2)
        with self.owner.lock:
            if generation == self.generation:
                self.cache[(key, today)] = result
        return result

    def bar(self, request_id, bar):
        with self.owner.lock:
            request = self.requests.get(request_id)
            if request is None:
                return
            try:
                day = datetime.strptime(str(bar.date), "%Y%m%d").date()
                price = positive(bar.close)
                if price is None:
                    raise ValueError("invalid close")
                request["prices"][day] = price
            except ValueError:
                request["error"] = "Dati storici IBKR non validi."

    def end(self, request_id):
        with self.owner.lock:
            request = self.requests.get(request_id)
            if request is not None:
                request["event"].set()

    def failed(self, request_id, code, message):
        # IBKR still sends delayed daily bars after this advisory. Do not close
        # the request early: only historicalDataEnd confirms a complete series.
        if code == 2188:
            return
        with self.owner.lock:
            request = self.requests.get(request_id)
            if request is None:
                return
            text = message.lower()
            permission = "permission" in text or "not subscribed" in text or code in {354, 10089, 10186}
            request["error"] = "Permessi IBKR insufficienti per lo storico richiesto. Nessun abbonamento acquistato." if permission else "Storico IBKR non disponibile per uno degli strumenti."
            request["event"].set()

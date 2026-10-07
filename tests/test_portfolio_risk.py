from datetime import date, timedelta
from statistics import mean, stdev
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from portfolio_risk import PortfolioRiskMonitor, normal_risk, cutoff


TODAY = date(2026, 10, 7)


def series(years=10, daily_change=True):
    day = cutoff(TODAY, years) - timedelta(days=5)
    prices, value, count = {}, 100.0, 0
    while day < TODAY:
        if day.weekday() < 5:
            value *= 1 + (0.01 if count % 2 else -0.01) if daily_change else 1
            prices[day] = value
            count += 1
        day += timedelta(days=1)
    return prices


class NormalRiskTests(unittest.TestCase):
    def test_95_percent_one_day_normal_formula_and_10_year_window(self):
        prices = series()
        result = normal_risk([{"exposure": 1000, "prices": prices}], 1200, TODAY)
        days = sorted(prices)
        start = cutoff(TODAY, 10)
        days = [max(d for d in days if d <= start)] + [d for d in days if d > start]
        pnl = [1000 * (prices[b] / prices[a] - 1) for a, b in zip(days, days[1:])]
        mu, sigma = mean(pnl), stdev(pnl)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["years"], 10)
        self.assertEqual(result["confidence"], .95)
        self.assertEqual(result["horizonDays"], 1)
        self.assertAlmostEqual(result["var95"], 1.6448536269514722 * sigma - mu)
        self.assertAlmostEqual(result["es95"], 2.0627128075074253 * sigma - mu)
        self.assertGreaterEqual(result["es95"], result["var95"])
        self.assertAlmostEqual(result["varPct"], result["var95"] / 1200 * 100)

    def test_fallback_to_five_years(self):
        self.assertEqual(normal_risk([{"exposure": 100, "prices": series(7)}], 100, TODAY)["years"], 5)

    def test_less_than_five_years_is_not_silently_accepted(self):
        self.assertIsNone(normal_risk([{"exposure": 100, "prices": series(4)}], 100, TODAY)["var95"])

    def test_correlated_short_exactly_offsets_long(self):
        prices = series()
        r = normal_risk([{"exposure": 100, "prices": prices}, {"exposure": -100, "prices": prices}], 100, TODAY)
        self.assertEqual(r["var95"], 0)
        self.assertEqual(r["es95"], 0)

    def test_correlated_longs_double_risk_not_root_sum_squares(self):
        prices = series()
        r1 = normal_risk([{"exposure": 100, "prices": prices}], 100, TODAY)
        r2 = normal_risk([{"exposure": 100, "prices": prices}] * 2, 200, TODAY)
        self.assertAlmostEqual(r2["var95"], 2 * r1["var95"])

    def test_fractional_position_preserves_precision(self):
        r1 = normal_risk([{"exposure": 100, "prices": series()}], 100, TODAY)
        r2 = normal_risk([{"exposure": .13, "prices": series()}], 100, TODAY)
        self.assertAlmostEqual(r2["var95"], .0013 * r1["var95"])

    def test_recent_missing_history_and_large_gap_fail_closed(self):
        for days_to_remove in (range(0, 20), range(100, 120)):
            prices = series()
            for offset in days_to_remove:
                prices.pop(TODAY - timedelta(days=offset), None)
            self.assertIsNone(normal_risk([{"exposure": 100, "prices": prices}], 100, TODAY)["es95"])

    def test_no_partial_portfolio_when_one_series_missing(self):
        r = normal_risk([{"exposure": 100, "prices": series()}, {"exposure": 20, "prices": {}}], 100, TODAY)
        self.assertIsNone(r["var95"])

    def test_invalid_price_nav_or_exposure_does_not_become_zero_risk(self):
        for value in (0, float("nan"), float("inf"), -1):
            prices = series()
            prices[max(prices)] = value
            self.assertIsNone(normal_risk([{"exposure": 100, "prices": prices}], 100, TODAY)["es95"])
            self.assertIsNone(normal_risk([], value, TODAY)["var95"])
        self.assertIsNone(normal_risk([{"exposure": float("nan"), "prices": series()}], 100, TODAY)["var95"])

    def test_current_partial_day_and_future_are_not_used(self):
        prices = series()
        original = normal_risk([{"exposure": 100, "prices": prices}], 100, TODAY)
        prices[TODAY], prices[TODAY + timedelta(days=1)] = 9999, 1
        self.assertEqual(normal_risk([{"exposure": 100, "prices": prices}], 100, TODAY), original)

    def test_eur_cash_only_zero_market_risk_is_explicit(self):
        r = normal_risk([], 100, TODAY)
        self.assertEqual(r["var95"], 0)
        self.assertEqual(r["years"], 0)
        self.assertIn("Solo liquidità EUR", r["message"])

    def test_leap_year_cutoff(self):
        self.assertEqual(cutoff(date(2024, 2, 29), 5), date(2019, 2, 28))


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.owner = SimpleNamespace(environment="LIVE", lock=threading.RLock(), ready=threading.Event(),
                                     stop_event=threading.Event(), isConnected=lambda: True,
                                     account_download_complete=threading.Event(), active_account="TEST", positions={}, account_values={})
        self.owner.ready.set()
        self.owner.reqMarketDataType = lambda mode: None
        self.monitor = PortfolioRiskMonitor(self.owner)

    def test_callbacks_ignore_unknown_and_reset_late_requests(self):
        event = threading.Event()
        self.monitor.requests[1] = {"prices": {}, "event": event, "error": ""}
        self.monitor.bar(1, SimpleNamespace(date="20261006", close=100))
        self.assertEqual(self.monitor.requests[1]["prices"], {date(2026, 10, 6): 100})
        self.monitor.end(1)
        self.assertTrue(event.is_set())
        self.monitor.reset()
        self.monitor.bar(1, SimpleNamespace(date="20261006", close=999))
        self.assertFalse(self.monitor.requests)

    def test_permissions_error_and_invalid_bars_are_explicit(self):
        self.monitor.requests[1] = {"prices": {}, "event": threading.Event(), "error": ""}
        self.monitor.failed(1, 162, "No market data permissions for STK")
        self.assertIn("Permessi", self.monitor.requests[1]["error"])
        self.monitor.bar(1, SimpleNamespace(date="bad", close=100))
        self.assertIn("non validi", self.monitor.requests[1]["error"])

    def test_history_request_adjusted_last_and_daily_cache(self):
        calls = []
        def request(*args):
            calls.append(args)
            self.monitor.bar(args[0], SimpleNamespace(date="20261006", close=100))
            self.monitor.end(args[0])
        self.owner.reqHistoricalData = request
        self.owner.cancelHistoricalData = lambda req: None
        contract = SimpleNamespace(exchange="SMART")
        a = self.monitor._history(("stock", 1), contract, "ADJUSTED_LAST", TODAY, 0)
        b = self.monitor._history(("stock", 1), contract, "ADJUSTED_LAST", TODAY, 0)
        self.assertEqual(a, b)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2:], ("", "10 Y", "1 day", "ADJUSTED_LAST", 1, 1, False, []))

    def test_delayed_history_advisory_does_not_end_the_request(self):
        event = threading.Event()
        self.monitor.requests[1] = {"prices": {}, "event": event, "error": ""}
        self.monitor.failed(1, 2188, "Up-to-the-second historical data requires additional subscription for the API.")
        self.assertFalse(event.is_set())
        self.assertEqual(self.monitor.requests[1]["error"], "")
        self.monitor.bar(1, SimpleNamespace(date="20261006", close=100))
        self.monitor.end(1)
        self.assertTrue(event.is_set())
        self.assertEqual(len(self.monitor.requests[1]["prices"]), 1)

    def test_listing_venue_is_not_used_as_direct_feed_and_contract_is_preserved(self):
        calls, modes = [], []
        self.owner.reqMarketDataType = modes.append
        def request(*args):
            calls.append(args)
            self.monitor.bar(args[0], SimpleNamespace(date="20261006", close=100))
            self.monitor.end(args[0])
        self.owner.reqHistoricalData = request
        self.owner.cancelHistoricalData = lambda req: None
        contract = SimpleNamespace(exchange="NASDAQ", primaryExchange="NASDAQ", conId=123, currency="USD")
        self.monitor._history(("stock", 123), contract, "ADJUSTED_LAST", TODAY, 0)
        self.assertEqual(modes, [3])
        requested = calls[0][1]
        self.assertEqual((requested.exchange, requested.primaryExchange, requested.conId, requested.currency), ("SMART", "NASDAQ", 123, "USD"))
        self.assertEqual(contract.exchange, "NASDAQ")

    def test_forex_keeps_idealpro_route(self):
        def request(*args):
            self.assertEqual(args[1].exchange, "IDEALPRO")
            self.monitor.bar(args[0], SimpleNamespace(date="20261006", close=1.1))
            self.monitor.end(args[0])
        self.owner.reqHistoricalData = request
        self.owner.cancelHistoricalData = lambda req: None
        self.monitor._fx("USD", TODAY, 0)

    def test_request_error_tries_five_years_but_permission_does_not_retry(self):
        for permission in (False, True):
            self.monitor.cache.clear()
            calls = []
            def request(*args):
                calls.append(args[3])
                if len(calls) == 1:
                    self.monitor.failed(args[0], 162, "No market data permissions" if permission else "invalid duration")
                else:
                    self.monitor.bar(args[0], SimpleNamespace(date="20261006", close=100))
                    self.monitor.end(args[0])
            self.owner.reqHistoricalData = request
            self.owner.cancelHistoricalData = lambda req: None
            with patch.object(self.owner.stop_event, "wait", return_value=False):
                self.monitor._history(("stock", 1), SimpleNamespace(exchange="SMART"), "ADJUSTED_LAST", TODAY, 0)
            self.assertEqual(calls, ["10 Y"] if permission else ["10 Y", "5 Y"])

    def test_fx_currency_conversion_and_foreign_cash_are_included(self):
        prices = series()
        currency_prices = {d: 1 / p for d, p in prices.items()}
        self.owner.positions[1] = {"account": "TEST", "conId": 1, "quantity": 2, "marketPrice": 100, "currency": "USD", "securityType": "STK"}
        self.monitor.contracts[1] = SimpleNamespace(exchange="SMART")
        self.monitor._inputs = lambda: (list(self.owner.positions.values()), [("USD", 10), ("EUR", 0)], {"USD": .9, "EUR": 1}, 200, "EUR")
        self.monitor._history = lambda key, *args: {"error": "", "prices": {d: 100 for d in prices} if key[0] == "stock" else currency_prices}
        with patch("portfolio_risk.datetime") as clock:
            clock.now.return_value.date.return_value = TODAY
            clock.now.return_value.isoformat.return_value = "timestamp"
            self.monitor._update()
        expected = normal_risk([{"exposure": 189, "prices": prices}], 200, TODAY)
        self.assertAlmostEqual(self.monitor.result["var95"], expected["var95"])

    def test_unsupported_positions_and_base_currency_fail_closed(self):
        for positions, currency in ([{"securityType": "OPT"}], "EUR"), ([], "USD"):
            self.monitor._inputs = lambda: (positions, [("EUR", 10)], {"EUR": 1}, 10, currency)
            self.monitor._update()
            self.assertEqual(self.monitor.result["status"], "unavailable")
            self.assertIsNone(self.monitor.result["var95"])

    def test_disconnected_snapshot_hides_cached_estimates(self):
        self.monitor.result = {"status": "ready", "var95": 2, "es95": 3}
        self.owner.ready.clear()
        self.assertIsNone(self.monitor.snapshot()["var95"])

    def test_changed_holdings_never_show_estimate_for_old_portfolio(self):
        self.monitor.result = {"status": "ready", "var95": 2, "es95": 3}
        self.monitor.result_signature = self.monitor._signature()
        self.assertEqual(self.monitor.snapshot()["var95"], 2)
        self.owner.positions[1] = {"account": "TEST", "conId": 1, "quantity": 1, "currency": "EUR", "securityType": "STK"}
        self.assertIsNone(self.monitor.snapshot()["var95"])


if __name__ == "__main__":
    unittest.main()

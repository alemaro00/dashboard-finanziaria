from datetime import date, datetime, timezone
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from closing_prices import ClosingPriceMonitor, completed_through, valuation


class ClosingPriceTests(unittest.TestCase):
    def setUp(self):
        self.position = {"account": "TEST", "conId": 42, "securityType": "STK", "quantity": 2, "averageCost": 80}
        self.owner = SimpleNamespace(environment="LIVE", lock=threading.RLock(), stop_event=threading.Event(),
                                     ready=threading.Event(), isConnected=lambda: True,
                                     active_account="TEST", positions={"TEST:42": self.position}, contract_metadata={})
        self.owner.ready.set()
        self.monitor = ClosingPriceMonitor(self.owner)
        self.contract = SimpleNamespace(conId=42, secType="STK", exchange="NASDAQ", primaryExchange="NASDAQ", currency="USD")
        self.monitor.track(self.contract)
        self.quote = {"price": 90, "date": "2026-10-06", "status": "ready"}
        self.metadata = {"timeZoneId": "US/Eastern", "liquidHours": "20261006:0930-20261006:1600;20261007:0930-20261007:1600"}

    def cutoff(self, stamp, metadata=None):
        return completed_through(metadata or self.metadata, datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc))

    def test_long_and_short_use_the_same_close(self):
        long = valuation(self.position, self.quote)
        short = valuation({**self.position, "quantity": -2}, self.quote)
        self.assertEqual(long["closingPrice"], short["closingPrice"])
        self.assertEqual((long["closingPnl"], short["closingPnl"]), (20, -20))
        self.assertNotIn("liquidationSide", long)

    def test_fractional_shares_and_average_entry_price(self):
        p = valuation({**self.position, "quantity": 0.0013, "averageCost": 92.3076923}, self.quote)
        self.assertAlmostEqual(p["closingPnl"], 0.0013 * (90 - 92.3076923))
        self.assertEqual(p["averageEntryPrice"], 92.3076923)

    def test_no_current_market_or_bid_ask_fallback(self):
        p = valuation({**self.position, "marketPrice": 100}, {"bid": {"price": 99}, "ask": {"price": 101}})
        self.assertIsNone(p["closingPrice"])
        self.assertIsNone(p["closingPnl"])

    def test_invalid_price_missing_date_and_unsupported_fail_closed(self):
        for price in (-1, 0, float("nan"), float("inf"), None):
            self.assertIsNone(valuation(self.position, {**self.quote, "price": price})["closingPnl"])
        self.assertIsNone(valuation(self.position, {"price": 90})["closingPrice"])
        for changes in ({"securityType": "FUT"}, {"quantity": 0}, {"quantity": float("nan")}, {"averageCost": float("nan")}):
            self.assertIsNone(valuation({**self.position, **changes}, self.quote)["closingPnl"])

    def test_before_close_excludes_partial_daily_bar(self):
        self.assertEqual(self.cutoff("2026-10-06T18:00:00"), date(2026, 10, 5))

    def test_close_publication_buffer_and_rome_midnight(self):
        self.assertEqual(self.cutoff("2026-10-06T20:19:59"), date(2026, 10, 5))
        self.assertEqual(self.cutoff("2026-10-06T20:20:00"), date(2026, 10, 6))
        # 00:45 in Rome is still Oct6 in New York: Oct6 close is complete.
        self.assertEqual(self.cutoff("2026-10-06T22:45:00"), date(2026, 10, 6))

    def test_split_session_waits_for_final_segment(self):
        metadata = {"timeZoneId": "Asia/Tokyo", "liquidHours": "20261007:0900-20261007:1130,1230-20261007:1530"}
        self.assertEqual(self.cutoff("2026-10-07T04:00:00", metadata), date(2026, 10, 6))
        self.assertEqual(self.cutoff("2026-10-07T06:50:00", metadata), date(2026, 10, 7))

    def test_early_close_uses_exchange_schedule(self):
        metadata = {"timeZoneId": "US/Eastern", "liquidHours": "20261127:0930-20261127:1300"}
        self.assertEqual(self.cutoff("2026-11-27T18:20:00", metadata), date(2026, 11, 27))

    def test_missing_or_invalid_schedule_conservatively_excludes_today(self):
        for hours in ("", "20261006:broken", "20261006:CLOSED"):
            self.assertEqual(self.cutoff("2026-10-06T22:00:00", {"timeZoneId": "US/Eastern", "liquidHours": hours}), date(2026, 10, 5))
        self.assertIsNone(completed_through({"timeZoneId": "invalid/timezone"}))
        self.assertIsNone(completed_through({}))

    def request_with_bars(self, cutoff=date(2026, 10, 6), fail=False):
        calls = []
        self.owner.reqMarketDataType = lambda mode: calls.append(("mode", mode))
        def request(*args):
            calls.append(args)
            rid = args[0]
            self.monitor.bar(rid, SimpleNamespace(date="20261002", close=89))
            self.monitor.bar(rid, SimpleNamespace(date="20261006", close=90))
            self.monitor.bar(rid, SimpleNamespace(date="20261007", close=999))
            if fail:
                self.monitor.failed(rid, 162, "No market data permissions")
            self.monitor.end(rid)
        self.owner.reqHistoricalData = request
        with patch.object(self.owner.stop_event, "wait", return_value=False):
            self.monitor._request(self.contract, cutoff, self.monitor.generation)
        return calls

    def test_trades_rth_completed_bars_exact_contract_no_streams(self):
        calls = self.request_with_bars()
        self.assertEqual(calls[0], ("mode", 3))
        request = calls[1]
        self.assertEqual(request[2:], ("", "2 W", "1 day", "TRADES", 1, 1, False, []))
        self.assertEqual((request[1].conId, request[1].exchange, request[1].primaryExchange, request[1].currency), (42, "SMART", "NASDAQ", "USD"))
        self.assertEqual(self.contract.exchange, "NASDAQ")
        self.assertEqual((self.monitor.quotes[42]["price"], self.monitor.quotes[42]["date"]), (90, "2026-10-06"))
        self.assertFalse(self.monitor.requests)

    def test_weekend_holiday_chooses_last_available_seduta(self):
        self.request_with_bars(cutoff=date(2026, 10, 5))
        self.assertEqual(self.monitor.quotes[42]["date"], "2026-10-02")

    def test_permission_error_never_uses_partial_received_bars(self):
        self.request_with_bars(fail=True)
        self.assertEqual(self.monitor.quotes[42]["reason"], "permissions")
        self.assertNotIn("price", self.monitor.quotes[42])

    def test_advisory_waits_for_historical_end(self):
        record = {"event": threading.Event(), "reason": "", "prices": {}}
        self.monitor.requests[1] = record
        self.monitor.failed(1, 2188, "Latest historical data requires subscription")
        self.assertFalse(record["event"].is_set())
        self.monitor.bar(1, SimpleNamespace(date="20261006", close=90))
        self.assertEqual(record["prices"], {date(2026, 10, 6): 90})
        self.monitor.end(1)
        self.assertTrue(record["event"].is_set())

    def test_refresh_no_more_than_hourly_even_after_failure(self):
        self.owner.contract_metadata[42] = self.metadata
        for status in ("ready", "unavailable"):
            self.monitor.quotes[42] = {"status": status, "checkedMonotonic": 100}
            with patch("closing_prices.time.monotonic", return_value=160), patch.object(self.monitor, "_request") as request:
                self.monitor._update()
                request.assert_not_called()
            with patch("closing_prices.time.monotonic", return_value=3700), patch.object(self.monitor, "_request") as request:
                self.monitor._update()
                request.assert_called_once()

    def test_reset_rejects_old_callbacks(self):
        self.monitor.requests[1] = {"event": threading.Event(), "reason": "", "prices": {}}
        self.monitor.quotes[42] = self.quote
        self.monitor.reset()
        self.monitor.bar(1, SimpleNamespace(date="20261006", close=999))
        self.assertEqual(self.monitor.requests, {})
        self.assertEqual(self.monitor.quotes, {})

    def test_snapshot_closing_pnl_separate_from_ibkr_pnl(self):
        from test_bridge_status import bridge
        client = bridge.IbkrAccountClient("127.0.0.1", 7496, 78, "LIVE")
        client.active_account = "TEST"
        client.ready.set()
        client.connected = True
        client.positions["TEST:42"] = {**self.position, "unrealizedPnl": 24, "marketPrice": 92}
        client.closing_prices.quotes[42] = self.quote
        p = client.snapshot()["positions"][0]
        self.assertEqual((p["closingPnl"], p["unrealizedPnl"]), (20, 24))
        self.assertFalse(hasattr(client, "liquidation_quotes"))


if __name__ == "__main__":
    unittest.main()

import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from liquidation_quotes import LiquidationMonitor, valuation


class LiquidationTests(unittest.TestCase):
    def setUp(self):
        self.owner = SimpleNamespace(environment="LIVE", lock=threading.RLock(),
                                     stop_event=threading.Event(), ready=threading.Event(),
                                     isConnected=lambda: True, positions={}, contract_metadata={})
        self.owner.ready.set()
        self.monitor = LiquidationMonitor(self.owner)
        self.monitor.requests[1] = 42
        self.position = {"conId": 42, "securityType": "STK", "quantity": 2, "averageCost": 80}

    def prices(self, kind=1):
        self.monitor.data_type(1, kind)
        with patch("liquidation_quotes.time.monotonic", return_value=100):
            self.monitor.price(1, 66 if kind in {3, 4} else 1, 90)
            self.monitor.price(1, 67 if kind in {3, 4} else 2, 91)

    def result(self, **changes):
        return valuation({**self.position, **changes}, self.monitor.quote(self.position), now=100)

    def test_long_uses_bid_not_ask(self):
        self.prices()
        result = self.result()
        self.assertEqual(result["liquidationPrice"], 90)
        self.assertEqual(result["liquidationSide"], "BID")
        self.assertEqual(result["liquidationPnl"], 20)

    def test_short_uses_ask_and_signed_quantity(self):
        self.prices()
        result = self.result(quantity=-2)
        self.assertEqual(result["liquidationPrice"], 91)
        self.assertEqual(result["liquidationSide"], "ASK")
        self.assertEqual(result["liquidationPnl"], -22)

    def test_fractional_shares_keep_precision(self):
        self.prices()
        self.assertAlmostEqual(self.result(quantity=0.0013, averageCost=92.3076923)["liquidationPnl"], 0.0013 * (90 - 92.3076923))

    def test_option_multiplier_normalizes_cost_price(self):
        self.prices()
        result = self.result(securityType="OPT", multiplier="100", averageCost=8000)
        self.assertEqual(result["averageEntryPrice"], 80)
        self.assertEqual(result["liquidationPnl"], 2000)

    def test_delayed_and_frozen_are_never_labelled_live(self):
        for kind, label in [(2, "frozen"), (3, "delayed"), (4, "delayed-frozen")]:
            self.prices(kind)
            result = self.result()
            self.assertEqual(result["liquidationDataType"], label)
            self.assertTrue(result["liquidationReceivedAt"])

    def test_unknown_type_does_not_produce_pnl(self):
        with patch("liquidation_quotes.time.monotonic", return_value=100):
            self.monitor.price(1, 1, 90)
        self.assertIsNone(self.result()["liquidationPnl"])

    def test_delayed_tick_type_proves_delayed_even_without_mode_callback(self):
        with patch("liquidation_quotes.time.monotonic", return_value=100):
            self.monitor.price(1, 66, 90)
        self.assertEqual(self.result()["liquidationDataType"], "delayed")

    def test_mode_change_drops_prices_from_the_previous_mode(self):
        self.prices(3)
        self.monitor.data_type(1, 1)
        self.assertIsNone(self.result()["liquidationPnl"])
        self.assertIsNone(self.result()["liquidationPrice"])

    def test_missing_side_never_uses_other_side_or_last(self):
        self.monitor.data_type(1, 1)
        self.monitor.price(1, 2, 91)
        self.monitor.price(1, 4, 92)  # LAST is not an exit quote.
        self.assertIsNone(self.result()["liquidationPrice"])
        self.assertIsNone(self.result()["liquidationPnl"])

    def test_invalid_price_clears_previously_valid_side(self):
        for invalid in (-1, 0, float("nan"), float("inf")):
            self.prices()
            self.monitor.price(1, 1, invalid)
            self.assertIsNone(self.result()["liquidationPnl"])

    def test_stale_quote_does_not_produce_current_estimate(self):
        self.prices()
        result = valuation(self.position, self.monitor.quote(self.position), now=3700)
        self.assertEqual(result["liquidationStatus"], "stale")
        self.assertIsNone(result["liquidationPnl"])
        self.assertEqual(result["liquidationLastKnownPnl"], 20)

    def test_silent_stream_refresh_preserves_original_receipt_and_ignores_old_callback(self):
        self.prices(3)
        self.monitor.quotes[42]["requestedAt"] = 100
        self.owner.positions["TEST:42"] = self.position
        self.monitor.track(SimpleNamespace(conId=42, secType="STK", exchange="SMART"))
        calls = []
        self.owner.cancelMktData = lambda req: calls.append(("cancel", req))
        self.owner.reqMarketDataType = lambda kind: None
        self.owner.reqMktData = lambda *args: calls.append(("request", args[0]))
        old_time = self.monitor.quotes[42]["bid"]["receivedAt"]
        with patch("liquidation_quotes.time.monotonic", return_value=3700), patch.object(self.owner.stop_event, "wait", return_value=False):
            self.monitor._subscriptions()
            self.monitor._subscriptions()
        self.assertEqual(calls, [("cancel", 1), ("request", 52000)])
        self.assertEqual(self.monitor.quotes[42]["bid"]["receivedAt"], old_time)
        self.monitor.price(1, 66, 999)
        self.assertEqual(self.monitor.quotes[42]["bid"]["price"], 90)

    def test_permission_error_does_not_retry_every_five_minutes(self):
        self.owner.positions["TEST:42"] = self.position
        self.monitor.quotes[42] = {"reason": "permissions", "requestedAt": 100}
        with patch("liquidation_quotes.time.monotonic", return_value=900):
            self.monitor._subscriptions()
        self.assertEqual(self.monitor.requests, {1: 42})

    def test_missing_new_ticks_requests_delayed_frozen_then_returns_to_streaming(self):
        self.owner.positions["TEST:42"] = self.position
        self.monitor.track(SimpleNamespace(conId=42, secType="STK", exchange="SMART"))
        self.monitor.quotes[42] = {"status": "pending", "requestedAt": 100, "requestedType": 3}
        calls = []
        self.owner.cancelMktData = lambda req: None
        self.owner.reqMarketDataType = calls.append
        self.owner.reqMktData = lambda *args: None
        with patch.object(self.owner.stop_event, "wait", return_value=False):
            with patch("liquidation_quotes.time.monotonic", return_value=130):
                self.monitor._subscriptions()
                self.monitor._subscriptions()
            with patch("liquidation_quotes.time.monotonic", return_value=3730):
                self.monitor._subscriptions()
        self.assertEqual(calls, [4, 3])

    def test_stream_ticks_do_not_change_price_or_receipt_within_one_hour(self):
        self.prices(3)
        stamp = self.monitor.quotes[42]["bid"]["receivedAt"]
        with patch("liquidation_quotes.time.monotonic", return_value=160):
            self.monitor.price(1, 66, 99)
        self.assertEqual(self.monitor.quotes[42]["bid"]["price"], 90)
        self.assertEqual(self.monitor.quotes[42]["bid"]["receivedAt"], stamp)
        with patch("liquidation_quotes.time.monotonic", return_value=3700):
            self.monitor.price(1, 66, 99)
        self.assertEqual(self.monitor.quotes[42]["bid"]["price"], 99)

    def test_no_subscription_renewal_after_one_minute(self):
        self.owner.positions["TEST:42"] = self.position
        self.monitor.quotes[42] = {"requestedAt": 100, "requestedType": 3, "bid": {"monotonic": 101}}
        with patch("liquidation_quotes.time.monotonic", return_value=160):
            self.monitor._subscriptions()
        self.assertEqual(self.monitor.requests, {1: 42})

    def test_disconnect_and_reset_invalidate_estimates(self):
        self.prices()
        self.owner.ready.clear()
        self.assertIsNone(self.result()["liquidationPnl"])
        self.monitor.reset()
        self.monitor.price(1, 1, 99)  # Late callback from the old connection.
        self.assertFalse(self.monitor.quotes)

    def test_unknown_multiplier_and_unsupported_instrument_fail_closed(self):
        self.prices()
        for changes in ({"securityType": "OPT", "multiplier": ""}, {"securityType": "BOND"}, {"averageCost": float("nan")}, {"quantity": 0}):
            self.assertIsNone(self.result(**changes)["liquidationPnl"])

    def test_permission_error_is_explicit(self):
        self.monitor.failed(1, "permissions")
        self.assertEqual(self.result()["liquidationReason"], "permissions")
        self.assertIsNone(self.result()["liquidationPnl"])

    def test_subscription_is_streaming_delayed_allowed_and_never_paid_snapshot(self):
        self.monitor.reset()
        contract = SimpleNamespace(conId=42, secType="STK", exchange="")
        self.owner.positions["TEST:42"] = self.position
        self.monitor.track(contract)
        calls = []
        self.owner.reqMarketDataType = lambda kind: calls.append(("type", kind))
        self.owner.reqMktData = lambda *args: calls.append(args)
        # Zero pacing wait without interrupting the worker loop.
        with patch.object(self.owner.stop_event, "wait", return_value=False):
            self.monitor._subscriptions()
            self.monitor._subscriptions()
        self.assertEqual(calls[0], ("type", 3))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][2:], ("", False, False, []))
        self.assertEqual(calls[1][1].exchange, "SMART")

    def test_closed_position_cancels_stream(self):
        calls = []
        self.owner.cancelMktData = lambda req: calls.append(req)
        self.monitor._subscriptions()
        self.assertEqual(calls, [1])

    def test_stock_quote_uses_smart_without_changing_security_or_listing_venue(self):
        self.monitor.reset()
        contract = SimpleNamespace(conId=42, secType="STK", exchange="NASDAQ", primaryExchange="NASDAQ", currency="USD")
        self.owner.positions["TEST:42"] = self.position
        self.monitor.track(contract)
        calls = []
        self.owner.reqMarketDataType = lambda kind: None
        self.owner.reqMktData = lambda *args: calls.append(args)
        with patch.object(self.owner.stop_event, "wait", return_value=False):
            self.monitor._subscriptions()
        quoted = calls[0][1]
        self.assertEqual((quoted.conId, quoted.exchange, quoted.primaryExchange, quoted.currency), (42, "SMART", "NASDAQ", "USD"))
        self.assertEqual(contract.exchange, "NASDAQ")
        self.assertEqual(calls[0][2:], ("", False, False, []))

    def test_no_quotes_after_frozen_timeout_is_not_infinite_pending(self):
        self.owner.positions["TEST:42"] = self.position
        self.monitor.quotes[42] = {"status": "pending", "requestedAt": 100, "requestedType": 4}
        with patch("liquidation_quotes.time.monotonic", return_value=160):
            self.monitor._subscriptions()
        self.assertEqual(self.monitor.quotes[42]["status"], "unavailable")
        self.assertEqual(self.result()["liquidationReason"], "noquotes")
        self.assertIsNone(self.result()["liquidationPnl"])
        with patch("liquidation_quotes.time.monotonic", return_value=161):
            self.monitor.price(1, 66, 90)
        self.assertNotIn("reason", self.monitor.quotes[42])

    def test_short_uses_ask_for_delayed_and_delayed_frozen_quotes(self):
        for kind in (3, 4):
            self.prices(kind)
            result = self.result(quantity=-2)
            self.assertEqual(result["liquidationSide"], "ASK")
            self.assertEqual(result["liquidationPrice"], 91)
            self.assertEqual(result["liquidationPnl"], -22)

if __name__ == "__main__":
    unittest.main()

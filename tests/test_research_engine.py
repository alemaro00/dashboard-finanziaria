"""No sockets, credentials or IB API: deterministic ledger and adversarial risk tests."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from research.engine import Limits, Order, Quote, ResearchEngine


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'research.sqlite3'
        self.engine = ResearchEngine(self.path)
        self.addCleanup(lambda: self.engine.close())
        self.engine.control('resume')

    def order(self, key='one', quantity='10', **kwargs):
        return Order(key, kwargs.pop('strategy', 'swing'), kwargs.pop('symbol', 'SPY'), kwargs.pop('side', 'BUY'), quantity, kwargs.pop('limit', '100.10'), **kwargs)

    def quote(self, at=1000, **kwargs):
        return Quote(kwargs.pop('symbol', 'SPY'), kwargs.pop('bid', '100'), kwargs.pop('ask', '100.02'), kwargs.pop('size', '100'), at, **kwargs)

    def buy(self):
        item = self.engine.submit(self.order(), self.quote(), now=1000)
        self.assertEqual(item['status'], 'accepted', item)
        return self.engine.process('one', self.quote(1001), now=1001)

    def test_decimal_rejects_nan_infinity_negative_bool_and_precision(self):
        for value in ('NaN', 'Infinity', '-1', True, '1e100'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.order(quantity=value)
        with self.assertRaises(ValueError):
            self.order(quantity='0.1')
        with self.assertRaises(ValueError):
            self.quote(ask='90')
        with self.assertRaises(ValueError):
            Limits(max_concentration='2')
        with self.assertRaises(ValueError):
            self.quote(at=float('nan'))

    def test_live_or_other_tenant_or_unknown_asset_unrepresentable(self):
        for changes in ({'account':'live'}, {'currency':'EUR'}, {'symbol':'CFD'}, {'strategy':'unknown'}):
            with self.assertRaises(ValueError):
                self.order(**changes)
        with self.assertRaises(ValueError):
            self.engine.control('enable_live')
        self.assertFalse(self.engine.snapshot()['live_enabled'])

    def test_bitcoin_is_not_routable_through_other_strategy(self):
        for changes in ({'symbol':'BTC','strategy':'swing'}, {'symbol':'SPY','strategy':'bitcoin'},
                        {'symbol':'AAPL','strategy':'momentum'}):
            with self.assertRaises(ValueError): self.order(**changes)

    def test_future_schema_is_rejected_without_mutating_it(self):
        other=Path(self.tmp.name)/'future.sqlite3'
        with sqlite3.connect(other) as db: db.execute('PRAGMA user_version=99')
        with self.assertRaisesRegex(ValueError,'future research schema'): ResearchEngine(other)
        with sqlite3.connect(other) as db: self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],99)

    def test_unvalidated_bots_and_no_performance(self):
        snapshot = self.engine.snapshot()
        self.assertEqual(len(snapshot['bots']), 6)
        self.assertIsNone(snapshot['performance'])
        self.assertTrue(all(x['validation'] == 'not_validated' for x in snapshot['bots']))

    def test_paused_order_blocked(self):
        self.engine.control('pause')
        self.assertEqual(self.engine.submit(self.order(), self.quote(), 1000)['reason'], 'paused')

    def test_stale_future_event_latency_spread_liquidity(self):
        quotes = [(self.quote(990), 'stale_or_future_quote'), (self.quote(1001), 'stale_or_future_quote'),
                  (self.quote(event_blocked=True), 'market_unavailable_or_event'),
                  (self.quote(available=False), 'market_unavailable_or_event'),
                  (self.quote(latency_ms='600'), 'latency'), (self.quote(ask='101'), 'spread'),
                  (self.quote(size='1'), 'liquidity')]
        for i, (quote, reason) in enumerate(quotes):
            self.assertEqual(self.engine.submit(self.order(str(i)), quote, 1000)['reason'], reason)

    def test_duplicate_submission_and_conflict(self):
        a = self.engine.submit(self.order(), self.quote(), 1000)
        b = self.engine.submit(self.order(), self.quote(), 1000)
        self.assertEqual(a, b)
        self.assertEqual(len(self.engine.snapshot()['orders']), 1)
        with self.assertRaisesRegex(ValueError, 'idempotency_conflict'):
            self.engine.submit(self.order(quantity='2'), self.quote(), 1000)

    def test_concurrent_duplicates_are_atomic(self):
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(lambda _: self.engine.submit(self.order(), self.quote(), 1000), range(12)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(len(self.engine.snapshot()['orders']), 1)
        self.assertTrue(self.engine.snapshot()['audit_valid'])

    def test_partial_fills_charge_costs_and_do_not_reuse_depth(self):
        self.assertEqual(self.engine.submit(self.order(quantity='19'), self.quote(), 1000)['status'], 'accepted')
        a = self.engine.process('one', self.quote(1001), 1001)
        self.assertEqual(a['status'], 'partial')
        self.assertEqual(a['filled'], '10')
        self.assertEqual(a, self.engine.process('one', self.quote(1001), 1001))
        b = self.engine.process('one', self.quote(1002), 1002)
        self.assertEqual(b['status'], 'filled')
        self.assertEqual(b['filled'], '19')
        self.assertGreater(Decimal(b['fees']), 2)
        self.assertLess(Decimal(self.engine.snapshot()['cash']), Decimal('98100'))

    def test_shared_quote_depth_across_orders(self):
        self.engine.submit(self.order('a'), self.quote(), 1000)
        self.engine.submit(self.order('b'), self.quote(), 1000)
        self.assertEqual(self.engine.process('a', self.quote(1001), 1001)['filled'], '10')
        self.assertEqual(self.engine.process('b', self.quote(1001), 1001)['filled'], '0')

    def test_latency_and_limit_no_fill(self):
        self.engine.submit(self.order(limit='100.03'), self.quote(), 1000)
        self.assertEqual(self.engine.process('one', self.quote(1000.1), 1000.1)['filled'], '0')
        self.assertEqual(self.engine.process('one', self.quote(1001), 1001)['filled'], '0')

    def test_pause_does_not_cancel_existing_but_kill_blocks_execution(self):
        self.engine.submit(self.order(), self.quote(), 1000)
        self.engine.control('pause')
        self.assertEqual(self.engine.process('one', self.quote(1001), 1001)['status'], 'filled')
        self.engine.control('resume')
        self.engine.submit(self.order('next'), self.quote(1001), 1001)
        self.engine.control('kill')
        with self.assertRaises(ValueError):
            self.engine.process('next', self.quote(1002), 1002)
        with self.assertRaises(ValueError):
            self.engine.control('resume')
        self.engine.control('cancel_pending')
        self.assertEqual(self.engine.snapshot()['orders'][-1]['status'], 'cancelled')
        self.assertEqual(self.engine.snapshot()['positions']['SPY']['quantity'], '10')

    def test_strategy_pause_kill_are_scoped(self):
        self.engine.control('pause', 'swing')
        self.assertEqual(self.engine.submit(self.order(), self.quote(), 1000)['reason'], 'paused')
        self.assertEqual(self.engine.submit(self.order('other', strategy='momentum'), self.quote(), 1000)['status'], 'accepted')
        self.engine.control('kill', 'swing')
        with self.assertRaises(ValueError):
            self.engine.control('resume', 'swing')

    def test_cancel_does_not_liquidate_and_releases_reserved_budget(self):
        self.buy()
        self.engine.submit(self.order('next'), self.quote(1001), 1001)
        self.engine.control('cancel_pending')
        self.assertEqual(self.engine.snapshot()['positions']['SPY']['quantity'], '10')
        self.assertEqual(self.engine.snapshot()['orders'][-1]['status'], 'cancelled')
        with self.assertRaises(ValueError):
            self.engine.control('close_positions')

    def test_short_and_cross_strategy_sale_blocked(self):
        self.assertEqual(self.engine.submit(self.order(side='SELL'), self.quote(), 1000)['reason'], 'short_selling_blocked')
        self.engine.submit(self.order('buy'), self.quote(), 1000)
        self.engine.process('buy', self.quote(1001), 1001)
        self.assertEqual(self.engine.submit(self.order('sell', strategy='momentum', side='SELL'), self.quote(1001), 1001)['reason'], 'short_selling_blocked')

    def test_sell_realized_and_pending_sell_reservations(self):
        self.buy()
        sell = self.order('sell', side='SELL', limit='99.90')
        self.assertEqual(self.engine.submit(sell, self.quote(1001), 1001)['status'], 'accepted')
        self.assertEqual(self.engine.submit(self.order('sell2', side='SELL', limit='99.90'), self.quote(1001), 1001)['reason'], 'short_selling_blocked')
        self.engine.process('sell', self.quote(1002), 1002)
        self.assertEqual(self.engine.snapshot()['positions']['SPY']['quantity'], '0')
        self.assertLess(Decimal(self.engine.snapshot()['realized_pnl']), 0)

    def test_pending_exposures_count_before_fill(self):
        self.engine.limits = replace(self.engine.limits, max_symbol=Decimal('1500'))
        self.assertEqual(self.engine.submit(self.order('a'), self.quote(), 1000)['status'], 'accepted')
        self.assertEqual(self.engine.submit(self.order('b'), self.quote(), 1000)['reason'], 'symbol_concentration')

    def test_daily_budget_turnover_order_count_price_collar(self):
        self.engine.limits = replace(self.engine.limits, max_orders=1)
        self.engine.submit(self.order('a'), self.quote(), 1000)
        self.assertEqual(self.engine.submit(self.order('b'), self.quote(), 1000)['reason'], 'order_count')
        self.assertEqual(self.engine.submit(self.order('c', limit='110'), self.quote(), 1000)['reason'], 'price_collar')

    def test_restart_requires_reconciliation_and_preserves_idempotency(self):
        original = self.engine.submit(self.order(), self.quote(), 1000)
        self.engine.close()
        self.engine = ResearchEngine(self.path)
        self.assertEqual(self.engine.snapshot()['status'], 'reconciliation_required')
        with self.assertRaises(ValueError):
            self.engine.control('resume')
        self.engine.control('reconcile')
        self.engine.control('resume')
        self.assertEqual(self.engine.submit(self.order(), self.quote(), 1000), original)
        self.assertEqual(self.engine.process('one', self.quote(1001), 1001)['status'], 'filled')

    def test_sql_append_only_and_out_of_band_ledger_tampering_fail_closed(self):
        with sqlite3.connect(self.path) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM audit')
            db.execute("UPDATE state SET data=replace(data,'100000','999999')")
        self.assertFalse(self.engine.snapshot()['audit_valid'])
        with self.assertRaisesRegex(ValueError, 'audit_integrity'):
            self.engine.control('resume')
        with self.assertRaisesRegex(ValueError, 'audit_integrity'):
            self.engine.submit(self.order(), self.quote(), 1000)
        self.assertFalse(self.engine.snapshot()['audit_valid'])

    def test_order_ledger_tampering_blocks_execution(self):
        self.engine.submit(self.order(), self.quote(), 1000)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE orders SET data=replace(data,'100.10','100.20')")
        with self.assertRaisesRegex(ValueError, 'audit_integrity'):
            self.engine.process('one', self.quote(1001), 1001)
        self.assertFalse(self.engine.snapshot()['audit_valid'])

    def test_audit_removed_by_admin_is_detected_with_remaining_state(self):
        with sqlite3.connect(self.path) as db:
            db.execute('DROP TRIGGER audit_no_delete')
            db.execute('DELETE FROM audit')
        self.assertFalse(self.engine.snapshot()['audit_valid'])

    def test_bitcoin_consent_and_revocation_cancel_simulated_orders(self):
        order = self.order(symbol='BTC', strategy='bitcoin', quantity='0.01', limit='50010')
        quote = self.quote(symbol='BTC', bid='50000', ask='50001')
        self.assertEqual(self.engine.submit(order, quote, 1000)['reason'], 'bitcoin_consent_required')
        self.engine.control('consent_bitcoin')
        self.assertEqual(self.engine.submit(replace(order, key='btc2'), quote, 1000)['status'], 'accepted')
        self.engine.control('revoke_bitcoin')
        self.assertEqual(self.engine.snapshot()['orders'][-1]['status'], 'cancelled')

    def test_stale_other_position_blocks_new_orders(self):
        self.buy()
        result = self.engine.submit(self.order('new', symbol='QQQ'), self.quote(1010, symbol='QQQ'), 1010)
        self.assertEqual(result['reason'], 'stale_portfolio_marks')

    def test_pending_orders_consume_next_day_budget_before_fill(self):
        self.engine.submit(self.order(),self.quote(),1000)
        self.engine.limits=replace(self.engine.limits,max_daily_notional=Decimal('500'))
        with self.assertRaisesRegex(ValueError,'daily_notional_or_turnover'):
            self.engine.process('one',self.quote(86401),86401)
        self.assertEqual(self.engine.snapshot()['positions'],{})

    def test_execution_reevaluates_limits_and_clock(self):
        self.engine.submit(self.order(), self.quote(), 1000)
        self.engine.limits = replace(self.engine.limits, max_order=Decimal('10'))
        with self.assertRaisesRegex(ValueError, 'execution_order_limit'):
            self.engine.process('one', self.quote(1001), 1001)
        with self.assertRaises(ValueError):
            self.engine.process('one', self.quote(999), 999)

    def test_fill_transaction_rolls_back_on_audit_write_failure(self):
        self.engine.submit(self.order(), self.quote(), 1000)
        before = self.engine.snapshot()
        audit = self.engine._audit
        def fail(*args):
            raise OSError('disk full')
        self.engine._audit = fail
        with self.assertRaises(OSError):
            self.engine.process('one', self.quote(1001), 1001)
        self.engine._audit = audit
        self.assertEqual(self.engine.snapshot(), before)


if __name__ == '__main__':
    unittest.main()

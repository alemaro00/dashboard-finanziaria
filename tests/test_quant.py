"""Synthetic fixtures verify safety and accounting, never profitability claims."""
import unittest
from dataclasses import replace
from math import nan

from research.strategies import (Bar, Quote, MarketFrame, Position, StrategyContext,
                                 STRATEGIES, evaluate, strategy_catalog)
from research.allocator import Candidate, allocate
from research.backtest import (Observation, Proposal, Costs, run, metrics,
                               walk_forward_windows, bootstrap_drawdowns)


def scenario(strategy_id='swing'):
    spec = next(s for s in STRATEGIES if s.id == strategy_id)
    interval = {'tick': 1, '1m': 60, '5m': 300, '4h': 14400, '1d': 86400}[spec.timeframe]
    now = 2_000_000_000.0
    bars = tuple(Bar(now-(spec.required_bars-1-i)*interval,
                     100+i*.03, 100.02+i*.03+(i % 2)*.01, 99.98+i*.03,
                     100+i*.03+(i % 2)*.005, 10000) for i in range(spec.required_bars))
    quote = Quote(now, bars[-1].close-.005, bars[-1].close+.005, 10000, 1000, 10, 'tick_l2')
    frame = MarketFrame('BTC' if strategy_id == 'bitcoin' else 'TEST_ETF',
                        'BTC_SPOT' if strategy_id == 'bitcoin' else 'ETF',
                        'USD', spec.timeframe, bars, quote, 365.25*86400/interval,
                        True, 10000, True, True, True, True, 1, 5, True, True)
    ctx = StrategyContext(now, 10000, Position(), 0, 0, 0, 0, 0, 0, 0, True, True, True, True, 1)
    return frame, ctx


class StrategyTests(unittest.TestCase):
    def test_exactly_six_research_only(self):
        catalog = strategy_catalog()
        self.assertEqual(len(catalog), 6)
        self.assertEqual(len(set(s['id'] for s in catalog)), 6)
        self.assertTrue(all(s['validation_status'] == 'research_unvalidated' for s in catalog))
        self.assertEqual(catalog[-1]['variants'], ['trend', 'breakout', 'multi_timeframe'])

    def test_every_strategy_stale_nan_unreconciled_future_fail_closed(self):
        for spec in STRATEGIES:
            frame, ctx = scenario(spec.id)
            for f, c in ((replace(frame, quote=replace(frame.quote, bid=nan)), ctx),
                         (replace(frame, quote=replace(frame.quote, timestamp=ctx.now-1000)), ctx),
                         (frame, replace(ctx, reconciled=False)),
                         (replace(frame, bars=frame.bars+(replace(frame.bars[-1], timestamp=ctx.now+1),)), ctx)):
                with self.subTest(strategy=spec.id):
                    self.assertEqual(evaluate(spec.id, f, c).action, 'BLOCKED')

    def test_mean_reversion_entry_uses_prior_vwap_and_volume(self):
        frame,ctx=scenario('mean_reversion')
        prior=tuple(replace(b,open=100,close=100+(.02 if i%2 else -.02),high=100.03,low=99.97)
                    for i,b in enumerate(frame.bars[:-1]))
        last=replace(frame.bars[-1],open=100,close=99.92,high=100.03,low=99.90)
        frame=replace(frame,bars=prior+(last,),quote=replace(frame.quote,bid=99.915,ask=99.925))
        self.assertEqual(evaluate('mean_reversion',frame,ctx).action,'ENTER')
        self.assertEqual(evaluate('mean_reversion',replace(frame,event_clear=False),ctx).action,'BLOCKED')

    def test_breakout_and_swing_require_real_cross_and_breakout_volume(self):
        for key in ('breakout','swing'):
            frame,ctx=scenario(key)
            self.assertEqual(evaluate(key,frame,ctx).action,'HOLD')
            last=frame.bars[-1]
            last=replace(last,close=last.close+.1,high=last.high+.1,volume=20000)
            frame=replace(frame,bars=frame.bars[:-1]+(last,),quote=replace(frame.quote,bid=last.close-.005,ask=last.close+.005))
            self.assertEqual(evaluate(key,frame,ctx).action,'ENTER')
            if key=='breakout':
                lowvol=replace(frame,bars=frame.bars[:-1]+(replace(last,volume=1000),))
                self.assertEqual(evaluate(key,lowvol,ctx).action,'HOLD')

    def test_bitcoin_never_substitutes_an_etf_or_other_crypto(self):
        frame, ctx = scenario('bitcoin')
        for bad in (replace(frame, symbol='ETH'), replace(frame, asset_type='ETF')):
            self.assertEqual(evaluate('bitcoin', bad, ctx).action, 'BLOCKED')
        self.assertEqual(evaluate('bitcoin', frame, replace(ctx, bitcoin_permission=False)).action, 'BLOCKED')
        self.assertEqual(evaluate('bitcoin', replace(frame, long_trend=None), ctx).action, 'BLOCKED')

    def test_bitcoin_three_variants_are_deterministic_and_capped(self):
        frame, ctx = scenario('bitcoin')
        # Explicit final breakout above the previous high plus ATR buffer.
        last = frame.bars[-1]
        last = replace(last, close=last.close+.08, high=last.high+.08)
        frame = replace(frame, bars=frame.bars[:-1]+(last,),
                        quote=replace(frame.quote, bid=last.close-.005, ask=last.close+.005))
        for variant in ('trend', 'breakout', 'multi_timeframe'):
            signal = evaluate('bitcoin', frame, ctx, variant)
            self.assertEqual(signal, evaluate('bitcoin', frame, ctx, variant))
            self.assertEqual(signal.action, 'ENTER')
            self.assertLessEqual(signal.target_weight, .05)
            self.assertGreater(signal.stop_price, 0)
        self.assertEqual(evaluate('bitcoin', frame, replace(ctx, week_loss_fraction=.02)).action, 'BLOCKED')

    def test_no_averaging_and_stop_exit(self):
        frame, ctx = scenario('swing')
        position = Position(1, frame.quote.bid, ctx.now-86400, frame.quote.bid)
        self.assertNotEqual(evaluate('swing', frame, replace(ctx, position=position)).action, 'ENTER')
        position = replace(position, entry_price=200, high_water=210)
        self.assertEqual(evaluate('swing', frame, replace(ctx, position=position)).action, 'EXIT')

    def test_intraday_close_and_event_filter(self):
        frame, ctx = scenario('breakout')
        self.assertEqual(evaluate('breakout', replace(frame, event_clear=False), ctx).action, 'BLOCKED')
        frame = replace(frame, seconds_to_close=60)
        self.assertEqual(evaluate('breakout', frame, ctx).action, 'BLOCKED')
        ctx = replace(ctx, position=Position(1, frame.quote.bid, ctx.now-100, frame.quote.bid))
        self.assertEqual(evaluate('breakout', frame, ctx).reason, 'session_end_exit_proposal')

    def test_scalping_rejects_ohlc_and_latency(self):
        frame, ctx = scenario('scalping')
        for q in (replace(frame.quote, source='ohlc'), replace(frame.quote, latency_ms=101)):
            self.assertEqual(evaluate('scalping', replace(frame, quote=q), ctx).action, 'BLOCKED')

    def test_momentum_requires_ranking_and_rebalance(self):
        frame, ctx = scenario('momentum')
        self.assertEqual(evaluate('momentum', replace(frame, momentum_rank=None), ctx).action, 'BLOCKED')
        self.assertEqual(evaluate('momentum', replace(frame, rebalance_due=False), ctx).action, 'HOLD')
        self.assertEqual(evaluate('momentum', frame, ctx).action, 'ENTER')


class AllocationTests(unittest.TestCase):
    def candidates(self, validated=True):
        return [Candidate('swing', .15, .01, 10000, 10000, 'USD', 'equity', validated, True),
                Candidate('momentum', .10, .01, 10000, 10000, 'EUR', 'mixed', validated, True)]

    def corr(self, rho=.5):
        return {('swing', 'swing'): 1., ('momentum', 'momentum'): 1.,
                ('swing', 'momentum'): rho, ('momentum', 'swing'): rho}

    def test_unvalidated_cash_and_missing_correlations_block(self):
        a = allocate(self.candidates(False), self.corr(), 'balanced', 10000, 10000, {}, {})
        self.assertEqual(a.amounts, {})
        a = allocate(self.candidates(), {}, 'balanced', 10000, 10000, {}, {})
        self.assertEqual(a.status, 'blocked')
        corrupt = self.corr()
        corrupt[('momentum', 'swing')] = None
        self.assertEqual(allocate(self.candidates(), corrupt, 'balanced', 10000, 10000, {}, {}).status, 'blocked')

    def test_unlevered_caps_and_correlation_risk(self):
        a = allocate(self.candidates(), self.corr(), 'conservative', 10000, 10000, {}, {})
        self.assertLessEqual(sum(a.amounts.values()), 3500)
        self.assertLessEqual(a.estimated_volatility, .05+1e-8)
        self.assertGreaterEqual(a.cash, 6500)
        full = allocate(self.candidates(), self.corr(1), 'conservative', 10000, 10000, {}, {})
        self.assertGreaterEqual(full.estimated_volatility, a.estimated_volatility)

    def test_existing_exposure_consumes_budget_and_must_reconcile(self):
        a = allocate(self.candidates(), self.corr(), 'dynamic', 10000, 5000, {}, {}, 5000)
        self.assertEqual(a.reason, 'incomplete_exposure_breakdown')
        a = allocate(self.candidates(), self.corr(), 'dynamic', 10000, 5000,
                     {'USD': 5000}, {'equity': 5000}, 5000)
        self.assertTrue(all(v == 0 for v in a.amounts.values()))

    def test_non_psd_matrix_rejected(self):
        cs = self.candidates()+[Candidate('bitcoin', .5, .01, 1000, 1000, 'USD', 'crypto', True, True)]
        ids = [c.strategy_id for c in cs]
        corr = {(a, b): 1.0 if a == b else -.9 for a in ids for b in ids}
        self.assertEqual(allocate(cs, corr, 'dynamic', 10000, 10000, {}, {}).reason,
                         'correlation_not_positive_semidefinite')


class BacktestTests(unittest.TestCase):
    def observations(self):
        return [Observation(100+i*10, 99, 100, 100, 1, corporate_actions_normalized=True) for i in range(5)]

    def test_no_same_observation_fill_and_no_lookahead(self):
        seen = []
        def propose(prefix):
            seen.append(len(prefix))
            return [Proposal('a', prefix[-1].timestamp, 'BUY', 10, 101, 1000)] if len(prefix) == 1 else []
        result = run(self.observations(), propose, 10000)
        self.assertEqual(seen, [1, 2, 3, 4, 5])
        self.assertTrue(all(f.timestamp > 100 for f in result.fills))
        self.assertLess(result.position, 10)  # Conservative volume participation creates partial fills.
        self.assertLess(result.equity[-1][1], 10000)
        self.assertTrue(any(status == 'partial' for _, status in result.statuses))

    def test_no_fill_without_crossing_or_during_outage(self):
        def propose(prefix):
            return [Proposal('a', 100, 'BUY', 1, 99, 130)] if len(prefix) == 1 else []
        result = run(self.observations(), propose, 1000)
        self.assertFalse(result.fills)
        self.assertIn(('a', 'expired_unfilled'), result.statuses)
        obs = [replace(o, available=False) for o in self.observations()]
        self.assertFalse(run(obs, propose, 1000).fills)

    def test_duplicate_nan_and_ohlc_rejected(self):
        def duplicate(prefix):
            return [Proposal('a', prefix[-1].timestamp, 'BUY', 1, 101, 1000)]
        with self.assertRaises(ValueError):
            run(self.observations(), duplicate, 1000)
        with self.assertRaises(ValueError):
            run(self.observations(), lambda _: [], nan)
        with self.assertRaises(ValueError):
            run(self.observations(), lambda _: [], 1000, microstructure=True, data_kind='quotes')
        with self.assertRaises(ValueError):
            run([replace(self.observations()[0], corporate_actions_normalized=False)], lambda _: [], 1000)

    def test_no_short_and_shared_liquidity_and_cost_stress(self):
        def buy(prefix):
            return [Proposal('a', 100, 'BUY', 100, 110, 1000), Proposal('b', 100, 'BUY', 100, 110, 1000)] if len(prefix) == 1 else []
        first = run(self.observations(), buy, 10000)
        worse = run(self.observations(), buy, 10000, Costs(commission_bps=20, slippage_bps=10))
        self.assertLessEqual(first.position, 3)
        self.assertLess(worse.equity[-1][1], first.equity[-1][1])
        def short(prefix):
            return [Proposal('s', 100, 'SELL', 100, 90, 1000)] if len(prefix) == 1 else []
        self.assertFalse(run(self.observations(), short, 10000).fills)

    def test_weekend_liquidity_and_rejection(self):
        def buy(prefix):
            return [Proposal('a', 100, 'BUY', 100, 110, 1000)] if len(prefix) == 1 else []
        normal = run(self.observations(), buy, 10000)
        weekend = run([replace(o, weekend=True) for o in self.observations()], buy, 10000)
        self.assertLess(weekend.position, normal.position)
        rejection = run([replace(o, reject=True) for o in self.observations()], buy, 10000)
        self.assertFalse(rejection.fills)
        self.assertIn(('a', 'rejected_scenario'), rejection.statuses)

    def test_metrics_report_undefined_not_invented(self):
        values = [(i*86400., v) for i, v in enumerate([100., 110., 88., 100.])]
        result = metrics(values, 365.25)
        self.assertAlmostEqual(result['max_drawdown'], .2)
        self.assertIsNone(result['profit_factor'])
        self.assertIsNone(result['benchmark_correlation'])
        flat = metrics([(0., 100.), (86400., 100.)], 365.25)
        self.assertIsNone(flat['sharpe_zero_rf'])
        with self.assertRaises(ValueError):
            metrics(values, 252)

    def test_recovery_measures_time_since_previous_peak(self):
        result=metrics([(0.,100.),(86400.,110.),(172800.,88.),(259200.,110.)],365.25)
        self.assertEqual(result['max_completed_recovery_seconds'],172800)

    def test_walkforward_embargo_and_seeded_stress(self):
        folds = walk_forward_windows(100, 30, 10, 10, 2)
        for training, validation, test in folds:
            self.assertLess(training[1], validation[0])
            self.assertLess(validation[1], test[0])
        self.assertEqual(bootstrap_drawdowns([.01, -.02, .01]*5, seed=5),
                         bootstrap_drawdowns([.01, -.02, .01]*5, seed=5))


if __name__ == '__main__':
    unittest.main()

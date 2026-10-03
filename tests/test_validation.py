from dataclasses import replace
import unittest

from research.validation import Evidence, TradeResult, assess, wilson_interval


class ValidationTests(unittest.TestCase):
    def evidence(self, **changes):
        sample = Evidence('swing', 'ibkr_paper', 'a' * 64, 'b' * 64)
        return replace(sample, **changes)

    def test_empty_history_has_no_profit_or_reliability(self):
        result = assess(self.evidence())
        self.assertIsNone(result['net_pnl'])
        self.assertIsNone(result['win_rate_interval_95'])
        self.assertFalse(result['live_enabled'])
        self.assertFalse(result['automatic_promotion'])

    def test_positive_gross_can_fail_net_and_double_costs(self):
        trade = TradeResult('1', 1, 2, 3, 2, 2)
        result = assess(self.evidence(trades=(trade,)))
        self.assertEqual(result['net_pnl'], -1)
        self.assertIn('net_positive', result['blockers'])
        self.assertIn('double_costs_positive', result['blockers'])

    def test_win_rate_is_not_future_probability(self):
        result = wilson_interval(10, 10)
        self.assertLess(result[0], 0.8)
        self.assertAlmostEqual(result[1], 1)

    def test_synthetic_success_never_meets_broker_gate(self):
        trades = tuple(TradeResult(str(i), i * 2, i * 2 + 1, 20, 1, 1) for i in range(45))
        result = assess(self.evidence(source='synthetic', trades=trades, equity=((0, 1000), (90, 1810)),
                                     observed_sessions=200, reconciliation_complete=True, costs_complete=True,
                                     data_quality_verified=True, independent_oos_passed=True, stress_tests_passed=True))
        self.assertIn('broker_paper_observed', result['blockers'])
        self.assertFalse(result['live_enabled'])

    def test_even_all_passed_means_review_not_live_activation(self):
        trades = tuple(TradeResult(str(i), i * 2, i * 2 + 1, 20, 1, 1) for i in range(45))
        result = assess(self.evidence(trades=trades, equity=((0, 1000), (90, 1810)),
                                     observed_sessions=200, reconciliation_complete=True, costs_complete=True,
                                     data_quality_verified=True, independent_oos_passed=True, stress_tests_passed=True))
        self.assertEqual(result['status'], 'ready_for_independent_review')
        self.assertFalse(result['live_enabled'])

    def test_duplicate_execs_or_nan_cannot_inflate_sample(self):
        trade = TradeResult('duplicate', 1, 2, 20, 1, 1)
        for trades in ((trade, trade), (replace(trade, gross_pnl=float('nan')),)):
            with self.assertRaises(ValueError):
                assess(self.evidence(trades=trades))

    def test_drawdown_and_equity_coverage(self):
        result = assess(self.evidence(equity=((0, 1000), (1, 800), (2, 1100))))
        self.assertEqual(result['maximum_drawdown'], .2)
        self.assertIn('drawdown_within_limit', result['blockers'])
        with self.assertRaises(ValueError):
            assess(self.evidence(trades=(TradeResult('x', 0, 5, 10, 1, 1),), equity=((1, 100), (6, 110))))


if __name__ == '__main__':
    unittest.main()

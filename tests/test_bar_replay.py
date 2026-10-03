from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from research.bar_replay import normalize, replay, screen_all
from research.strategies import Signal


def dataset(next_open=90, count=90):
    beginning = datetime(2020, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(count):
        opened = next_open if i == 62 else 100
        bars.append({'date': (beginning + timedelta(days=i)).strftime('%Y%m%d'), 'open': opened,
                     'high': max(102, opened), 'low': min(98, opened), 'close': 100, 'volume': 100000})
    return {'strategy': 'swing', 'symbol': 'AAPL', 'bar_size': '1 day', 'complete': True, 'errors': [], 'bars': bars}


class ReplayTests(unittest.TestCase):
    def test_scalping_never_uses_ohlc(self):
        self.assertEqual(replay('scalping', [dataset()], 2000000000)['status'], 'not_run')

    def test_future_and_invalid_bars(self):
        data = dataset()
        now = datetime(2020, 1, 3, tzinfo=timezone.utc).timestamp()
        self.assertEqual(len(normalize(data, now)), 2)
        data['bars'][0]['close'] = float('nan')
        with self.assertRaises(ValueError): normalize(data, now)

    def test_fill_only_next_bar_and_limit_price_respected(self):
        for opened, expected_filled in [(90, True), (110, False)]:
            seen = []
            def propose(strategy, frame, context):
                seen.append(context.position.quantity)
                return Signal(strategy, frame.symbol, context.now, 'ENTER' if len(seen) == 1 else 'HOLD', 'test', .01, 100.03)
            with patch('research.bar_replay.evaluate', side_effect=propose):
                result = replay('swing', [dataset(opened)], 2000000000, out_of_sample=False)
            self.assertEqual(seen[0], 0)
            self.assertEqual(seen[1] > 0, expected_filled)
            self.assertFalse(result['paper_eligible'])
            self.assertFalse(result['live_enabled'])

    def test_missing_momentum_universe_fails_closed(self):
        data = dataset(); data['strategy'] = 'momentum'
        result = replay('momentum', [data], 2000000000)
        self.assertEqual(result['status'], 'not_run')

    def test_holdout_metadata_and_signal_ledger_are_explicit(self):
        result = replay('swing', [dataset()], 2000000000)
        design = result['sample_design']
        self.assertEqual(design['method'], 'fixed_parameters_single_holdout')
        self.assertFalse(design['parameters_trained'])
        self.assertFalse(design['parameters_optimized'])
        self.assertFalse(design['separate_validation_segment'])
        self.assertEqual(design['history_observations'] + design['test_observations'], design['total_common_observations'])
        self.assertEqual(len(result['signal_events']), result['observations'])
        self.assertEqual(sum(result['signals'].values()), len(result['signal_events']))
        self.assertEqual({'timestamp', 'symbol', 'action', 'reason', 'price', 'position_open'}, set(result['signal_events'][0]))

    def test_invalid_source_does_not_create_performance(self):
        data = dataset(); data['complete'] = False
        result = screen_all([data], 2000000000)
        self.assertEqual(len(result), 6)
        self.assertEqual(next(v for v in result if v['strategy'] == 'swing')['baseline']['status'], 'not_run')

    def test_three_chronological_segments_do_not_overlap(self):
        result = next(item for item in screen_all([dataset(count=180)], 2000000000) if item['strategy'] == 'swing')
        segments = result['segments']
        self.assertLess(segments['in_sample']['end'], segments['validation']['start'])
        self.assertLess(segments['validation']['end'], segments['out_of_sample']['start'])
        self.assertEqual(result['protocol']['chronological_split'], [60, 20, 20])
        self.assertFalse(result['protocol']['parameters_trained'])
        self.assertIs(result['baseline'], segments['out_of_sample'])


if __name__ == '__main__':
    unittest.main()

import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_bridge_status import fake_modules

spec = importlib.util.spec_from_file_location('paper_data_test', Path(__file__).resolve().parents[1] / 'paper_data.py')
module = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, fake_modules):
    spec.loader.exec_module(module)


class PaperDataTests(unittest.TestCase):
    def test_daily_research_uses_six_year_window_but_intraday_stays_bounded(self):
        daily = [job for job in module.JOBS if job[2] == '1 day']
        intraday = [job for job in module.JOBS if job[2] != '1 day']
        self.assertTrue(daily)
        self.assertTrue(all(job[3] == '6 Y' for job in daily))
        self.assertTrue(all(job[3] == '1 M' for job in intraday))

    def test_ports_and_hosts_fail_closed_before_connect(self):
        client = module.PaperDataClient()
        for host, port in [('127.0.0.1', 7496), ('127.0.0.1', 4001), ('example.com', 7497), ('::1', 7497), ('127.0.0.1', True)]:
            with self.assertRaises(ValueError):
                client.connect(host, port, 182)

    def test_live_mixed_and_missing_accounts_rejected(self):
        for accounts in ('U1234', '', 'DU1234,U456', 'DU1234,DU5678', 'DUanything'):
            client = module.PaperDataClient()
            client.managedAccounts(accounts)
            self.assertFalse(client.identity_verified)

    def test_paper_identity_does_not_enable_orders(self):
        client = module.PaperDataClient()
        client.managedAccounts('DU12345')
        self.assertTrue(client.identity_verified)
        for operation in (client.placeOrder, client.cancelOrder, client.reqGlobalCancel):
            with self.assertRaises(PermissionError):
                operation()
        client.connectionClosed()
        self.assertFalse(client.identity_verified)

    def test_historical_nan_rejected(self):
        client = module.PaperDataClient()
        client.request_id = 1
        client.historicalData(1, SimpleNamespace(date='20260101', open=1, high=2, low=1, close=float('nan'), volume=100))
        self.assertFalse(client.bars)
        self.assertTrue(client.current_errors)

    def test_lab_no_orders_no_performance_from_bars(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = module.PaperLab(directory)
            result = lab.snapshot()
            self.assertFalse(result['orders_enabled'])
            self.assertEqual(len(result['validation']), 6)
            self.assertTrue(all(v['net_pnl'] is None for v in result['validation']))
            with self.assertRaises(ValueError):
                lab.start(7496)

    def test_collection_persists_and_does_not_retry_orders(self):
        class Fake:
            errors = []
            def open_session(self, port): pass
            def history(self, *args): return {'bars': [{'close': 1}], 'complete': True, 'errors': []}
            def close(self): pass
        with tempfile.TemporaryDirectory() as directory:
            lab = module.PaperLab(directory, Fake)
            with patch.object(lab.cancel, 'wait', return_value=False):
                lab._collect(7497)
            restored = module.PaperLab(directory).snapshot()
            self.assertEqual(sum(d['bars_count'] for d in restored['datasets']), 8)
            self.assertIsNotNone(restored['last_collection_at'])
            self.assertFalse(restored['orders_enabled'])


if __name__ == '__main__':
    unittest.main()

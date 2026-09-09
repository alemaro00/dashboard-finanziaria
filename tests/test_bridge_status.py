"""Offline callback tests; the fake API cannot open sockets or place orders."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


class FakeClient:
    def __init__(self, wrapper):
        self.connected = False

    def isConnected(self):
        return self.connected

    def connect(self, *args):
        pass

    def disconnect(self):
        self.connected = False

    def reqManagedAccts(self):
        pass

    def reqAccountSummary(self, *args):
        pass

    def reqPositions(self):
        pass

    def reqAccountUpdates(self, *args):
        pass


fake_modules = {}
for name, attribute, value in [('client', 'EClient', FakeClient),
                               ('wrapper', 'EWrapper', type('EWrapper', (), {})),
                               ('contract', 'Contract', type('Contract', (), {}))]:
    module = types.ModuleType('ibapi.' + name)
    setattr(module, attribute, value)
    fake_modules['ibapi.' + name] = module
fake_modules['ibapi'] = types.ModuleType('ibapi')
spec = importlib.util.spec_from_file_location('bridge_under_test', Path(__file__).resolve().parents[1] / 'ibkr_paper_bridge.py')
bridge = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, fake_modules):
    spec.loader.exec_module(bridge)


class DataStatusTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(bridge.time, 'monotonic', return_value=1000.0)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.client = bridge.IbkrAccountClient('127.0.0.1', 7497, 71, 'PAPER')

    def begin(self):
        self.client.connect_to_tws()
        self.assertEqual(self.client.snapshot()['dataStatus'], 'connecting')
        self.client.nextValidId(1)
        self.client.managedAccounts('TEST')

    def synchronize(self):
        self.begin()
        self.client.accountSummary(9101, 'TEST', 'NetLiquidation', '12', 'EUR')
        self.client.accountSummaryEnd(9101)
        self.client.accountDownloadEnd('TEST')

    def test_handshake_and_one_end_do_not_claim_current(self):
        self.assertEqual(self.client.snapshot()['dataStatus'], 'disconnected')
        self.begin()
        self.assertEqual(self.client.snapshot()['status'], 'connected')
        self.assertEqual(self.client.snapshot()['dataStatus'], 'synchronizing')
        self.client.accountDownloadEnd('OTHER')
        self.client.accountSummaryEnd(123)
        self.assertFalse(self.client.account_download_complete.is_set())
        self.assertFalse(self.client.account_summary_complete.is_set())
        self.client.accountDownloadEnd('TEST')
        self.assertEqual(self.client.snapshot()['dataStatus'], 'synchronizing')
        self.client.accountSummaryEnd(9101)
        self.assertEqual(self.client.snapshot()['dataStatus'], 'current')

    def test_stale_boundary_and_account_stream_recovery(self):
        self.synchronize()
        self.now.return_value = 1299.9
        self.assertEqual(self.client.snapshot()['dataStatus'], 'current')
        self.now.return_value = 1300
        self.client._touch()  # Nonfinancial metadata/activity is not account freshness.
        self.assertEqual(self.client.snapshot()['dataStatus'], 'stale')
        self.client.updateAccountValue('NetLiquidation', '13', 'EUR', 'OTHER')
        self.assertEqual(self.client.snapshot()['dataStatus'], 'stale')
        self.client.updateAccountTime('12:00')
        snapshot = self.client.snapshot()
        self.assertEqual(snapshot['dataStatus'], 'current')
        self.assertEqual(snapshot['dataAgeSeconds'], 0)
        self.assertTrue(snapshot['lastDataUpdate'])

    def test_reconnect_clears_financial_data_and_requires_both_new_ends(self):
        self.synchronize()
        self.client.positions['TEST:123'] = {'account': 'TEST', 'conId': 123}
        self.client.connectionClosed()
        self.assertEqual(self.client.snapshot()['dataStatus'], 'disconnected')
        self.begin()
        self.assertEqual(self.client.snapshot()['metrics']['netLiquidation'], 0)
        self.assertEqual(self.client.snapshot()['positions'], [])
        self.assertIsNone(self.client.snapshot()['dataAgeSeconds'])
        self.client.accountSummaryEnd(9101)
        self.assertEqual(self.client.snapshot()['dataStatus'], 'synchronizing')
        self.client.accountDownloadEnd('TEST')
        self.assertEqual(self.client.snapshot()['dataStatus'], 'current')

    def test_connection_error_invalidates_sync(self):
        self.synchronize()
        self.client.connected = True
        self.client.error(-1, 1100, 'Connection lost')
        self.assertFalse(self.client.connected)
        self.assertEqual(self.client.snapshot()['dataStatus'], 'disconnected')
        self.assertFalse(self.client.snapshot()['initialSyncComplete'])
        self.assertFalse(self.client.ready.is_set())

    def test_wait_does_not_accept_handshake_only(self):
        self.begin()
        self.assertEqual(bridge.wait_for_snapshot(self.client, 0)['dataStatus'], 'synchronizing')
        self.synchronize()
        self.assertEqual(bridge.wait_for_snapshot(self.client, 1)['dataStatus'], 'current')

    def test_cash_balances_are_exposed_per_currency_in_base_value(self):
        self.synchronize()
        self.client.accountSummary(9101, 'TEST', 'Currency', 'EUR', 'EUR')
        self.client.updateAccountValue('CashBalance', '8', 'EUR', 'TEST')
        self.client.updateAccountValue('ExchangeRate', '1', 'EUR', 'TEST')
        self.client.updateAccountValue('$LEDGER-CashBalance', '3', 'USD', 'TEST')
        self.client.updateAccountValue('$LEDGER-ExchangeRate', '0.9', 'USD', 'TEST')

        balances = {item['currency']: item for item in self.client.snapshot()['cashBalances']}

        self.assertEqual(balances['EUR']['amount'], 8)
        self.assertEqual(balances['EUR']['baseValue'], 8)
        self.assertEqual(balances['USD']['amount'], 3)
        self.assertAlmostEqual(balances['USD']['baseValue'], 2.7)


class DashboardStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.data_directory = Path(self.temporary_directory.name)
        self.file_patch = patch.object(bridge, 'APP_DATA_DIR', self.data_directory)
        self.state_file_patch = patch.object(bridge, 'APP_STATE_FILE', self.data_directory / 'dashboard-state.json')
        self.file_patch.start()
        self.state_file_patch.start()
        self.addCleanup(self.file_patch.stop)
        self.addCleanup(self.state_file_patch.stop)

    def test_round_trip_keeps_open_month_and_draft_entry(self):
        payload = {
            'state': {'monthName': 'Settembre', 'income': '2450', 'monthlyHistory': []},
            'entry': {'label': 'Affitto', 'amount': '900'},
            'editingMonthId': '2026-settembre',
            'ui': {'monthlyInputOpen': True},
        }
        saved = bridge.save_dashboard_state(payload)
        loaded = bridge.load_dashboard_state()
        self.assertEqual(loaded, saved)
        self.assertEqual(loaded['state']['income'], '2450')
        self.assertEqual(loaded['entry']['label'], 'Affitto')
        self.assertEqual(loaded['editingMonthId'], '2026-settembre')

    def test_invalid_state_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Stato dashboard non valido'):
            bridge.save_dashboard_state({'state': {'monthlyHistory': 'non-lista'}})


if __name__ == '__main__':
    unittest.main()

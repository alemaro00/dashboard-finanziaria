"""Offline security and persistence regressions. Never loads personal data."""
import io
import json
from email.message import Message
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from local_security import RequestGuard, verify_csrf, validate_json_tree
from test_bridge_status import bridge


class BoundaryTests(unittest.TestCase):
    def test_exact_origin_and_host_blocks_rebinding_and_cross_origin(self):
        g = RequestGuard()
        for h in [
            {'Host':'evil.example:8765'},
            {'Host':'127.0.0.1:8765','Origin':'https://evil.example'},
            {'Host':'127.0.0.1:8765','Origin':'null'},
            {'Host':'127.0.0.1:8765','Origin':'http://127.0.0.1:8765.evil.example'},
            {'Host':'127.0.0.1:8765','Origin':'http://127.0.0.1:9999'},
            {'Host':'127.0.0.1:8765','Sec-Fetch-Site':'cross-site'},
        ]:
            self.assertFalse(g.allowed(h,8765), h)
        self.assertTrue(g.allowed({'Host':'127.0.0.1:8765','Origin':'http://127.0.0.1:8765'},8765))
        self.assertTrue(g.allowed({'Host':'localhost:8765','Sec-Fetch-Site':'none'},8765))

    def test_bank_callback_accepts_navigation_but_rejects_origins_and_rebinding(self):
        g = RequestGuard()
        self.assertTrue(g.allowed_callback({'Host':'127.0.0.1:8767','Sec-Fetch-Mode':'navigate','Sec-Fetch-Site':'cross-site'},8767))
        self.assertFalse(g.allowed_callback({'Host':'evil.example:8767','Sec-Fetch-Mode':'navigate'},8767))
        self.assertFalse(g.allowed_callback({'Host':'127.0.0.1:8767','Origin':'https://attacker.invalid','Sec-Fetch-Mode':'navigate'},8767))
        self.assertFalse(g.allowed_callback({'Host':'127.0.0.1:8767','Sec-Fetch-Mode':'cors'},8767))

    def test_rate_limit_and_token(self):
        g = RequestGuard()
        with patch('local_security.time.monotonic',return_value=100):
            for _ in range(600): self.assertTrue(g.admit())
            self.assertFalse(g.admit())
        with patch('local_security.time.monotonic',return_value=161): self.assertTrue(g.admit())
        self.assertFalse(verify_csrf('secret',None))
        self.assertFalse(verify_csrf('secret','wrong'))
        self.assertTrue(verify_csrf('secret','secret'))

    def test_nonfinite_deep_and_oversize_json(self):
        for v in [float('nan'),float('inf'),{'a':'x'*100001}]:
            with self.assertRaises(ValueError): validate_json_tree(v)
        v = {}
        for _ in range(26): v={'a':v}
        with self.assertRaises(ValueError): validate_json_tree(v)

    def handler(self,payload,csrf=None,content_type='application/json'):
        h=bridge.DashboardHandler.__new__(bridge.DashboardHandler)
        body=json.dumps(payload).encode()
        h.headers=Message()
        h.headers['Content-Length']=str(len(body))
        h.headers['Content-Type']=content_type
        if csrf: h.headers['X-CSRF-Token']=csrf
        h.csrf_token='known'
        h.rfile=io.BytesIO(body)
        h.connection=type('Connection',(),{'settimeout':lambda *args:None})()
        return h

    def test_mutations_require_json_and_csrf_including_beacon(self):
        with self.assertRaises(ValueError): self.handler({'state':{}})._read_json_body()
        with self.assertRaises(ValueError): self.handler({},'known','text/plain')._read_json_body()
        self.assertEqual(self.handler({'_csrf':'known','state':{}})._read_json_body(),{'state':{}})
        self.assertEqual(self.handler({'state':{}},'known')._read_json_body(),{'state':{}})

    def test_default_startup_never_starts_a_broker(self):
        from test_bridge_status import fake_modules
        with tempfile.TemporaryDirectory() as temp:
            server=MagicMock()
            with patch.dict(sys.modules, fake_modules), \
                 patch.object(bridge,'APP_DATA_DIR',Path(temp)), \
                 patch.object(bridge,'ThreadingHTTPServer',return_value=server), \
                 patch.object(bridge.IbkrAccountClient,'start') as start, \
                 patch.object(sys,'argv', ['bridge','--no-browser']):
                self.assertEqual(bridge.main(),0)
                start.assert_not_called()
                server.serve_forever.assert_called_once()

    def test_sdk_order_methods_blocked(self):
        client=bridge.IbkrAccountClient('127.0.0.1',7496,70,'LIVE')
        for method in ('placeOrder','cancelOrder','reqGlobalCancel'):
            with self.assertRaises(PermissionError): getattr(client,method)()


class SafeStorageTests(unittest.TestCase):
    def test_backup_permissions_and_corrupt_state_preservation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            target=root/'dashboard-state.json'
            with patch.object(bridge,'APP_DATA_DIR',root),patch.object(bridge,'APP_STATE_FILE',target):
                first=bridge.save_dashboard_state({'state':{'monthlyHistory':[],'income':10}})
                bridge.save_dashboard_state({'state':{'monthlyHistory':[],'income':20}})
                self.assertEqual(json.loads(target.with_suffix('.json.bak').read_text()),first)
                self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o600)
                target.write_text('{broken')
                with self.assertRaises(ValueError): bridge.save_dashboard_state({'state':{'monthlyHistory':[]}})
                self.assertEqual(target.read_text(),'{broken')

    def test_frontend_does_not_enable_autosave_after_load_error(self):
        source=(Path(__file__).parents[1]/'salary-planner-react.html').read_text()
        self.assertIn('persistenceReady.current = false;\n                setPersistenceStatus("error")',source)

if __name__=='__main__': unittest.main()

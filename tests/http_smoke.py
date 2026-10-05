"""Loopback HTTP integration. Temporary data, fake broker incapable of network I/O.
Run separately because opening a test listener requires local socket permission.
"""
import http.client
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_bridge_status import bridge
from local_security import RequestGuard


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.directory=Path(cls.tmp.name)
        cls.patches=[patch.object(bridge,'APP_DATA_DIR',cls.directory),
                     patch.object(bridge,'APP_STATE_FILE',cls.directory/'dashboard-state.json')]
        for p in cls.patches: p.start()
        cls.handler=type('TestHandler',(bridge.DashboardHandler,),{'guard':RequestGuard(),
            'clients':{k:bridge.IbkrAccountClient('127.0.0.1',p,i,k.upper()) for k,p,i in [('live',7496,70),('paper',7497,71)]}})
        cls.server=bridge.ThreadingHTTPServer(('127.0.0.1',0),cls.handler)
        cls.port=cls.server.server_port
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.worker.join()
        for p in cls.patches:p.stop()
        cls.tmp.cleanup()

    def request(self,method,path,body=None,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        c.request(method,path,body=body,headers=headers or {})
        response=c.getresponse()
        result=response.status,dict(response.getheaders()),response.read()
        c.close()
        return result

    def test_page_assets_csp_and_no_cdn(self):
        code,headers,body=self.request('GET','/')
        self.assertEqual(code,200)
        self.assertNotIn('Access-Control-Allow-Origin',headers)
        self.assertIn("script-src 'self'",headers['Content-Security-Policy'])
        self.assertNotIn(b'text/babel',body)
        for asset in re.findall(rb'<script src="([^"]+)"',body):
            self.assertTrue(asset.startswith(b'/assets/'))
            self.assertEqual(self.request('GET',asset.decode())[0],200)
        self.assertEqual(self.request('GET','/assets/../../ibkr_paper_bridge.py')[0],404)

    def test_retired_wallet_routes_are_unavailable(self):
        self.assertEqual(self.request('GET', '/api/wallet/snapshot')[0], 404)
        headers = {'Content-Type': 'application/json', 'X-CSRF-Token': self.handler.csrf_token}
        for action in ('sync', 'create', 'update'):
            self.assertEqual(self.request('POST', '/api/wallet/control',
                json.dumps({'action': action}), headers)[0], 404)

    def test_cross_origin_reads_and_dns_rebinding_denied(self):
        for path in ('/api/state','/api/live/snapshot','/'):
            self.assertEqual(self.request('GET',path,headers={'Origin':'https://attacker.invalid'})[0],403)
            self.assertEqual(self.request('GET',path,headers={'Host':f'rebound.invalid:{self.port}'})[0],403)

    def test_save_reload_boat_draft_and_missing_csrf(self):
        _,_,body=self.request('GET','/')
        token=re.search(rb'name="csrf-token" content="([^"]+)"',body)[1].decode()
        document={'state':{'monthName':'Test only','monthlyHistory':[]},'entry':{'label':'Draft fixture'}}
        headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}'}
        self.assertEqual(self.request('POST','/api/state',json.dumps(document),headers)[0],400)
        headers['X-CSRF-Token']=token
        self.assertEqual(self.request('POST','/api/state',json.dumps(document),headers)[0],200)
        stored=json.loads(self.request('GET','/api/state')[2])
        self.assertEqual(stored['entry'],document['entry'])
        self.assertEqual(stored['state'],document['state'])

    def test_removed_laboratory_routes_and_live_order_routes_are_unavailable(self):
        headers={'Content-Type':'application/json','X-CSRF-Token':self.handler.csrf_token}
        for path in ('/api/research/snapshot', '/api/research/strategies', '/api/paper-lab/snapshot'):
            self.assertEqual(self.request('GET',path)[0],404)
        for path in ('/api/research/control', '/api/paper-lab/control'):
            self.assertEqual(self.request('POST',path,json.dumps({'action':'pause'}),headers)[0],404)
        self.assertEqual(self.request('POST','/api/live/orders','{}',headers)[0],404)
        health=json.loads(self.request('GET','/api/health')[2])
        self.assertTrue(health['readOnlyBridge'])
        self.assertTrue(all(c['status']=='disconnected' for c in health['connections'].values()))

    def test_portable_backup_http_requires_csrf_and_confirm_and_restores_classifications(self):
        headers = {'Content-Type': 'application/json', 'X-CSRF-Token': self.handler.csrf_token}
        fixture = {'state': {'monthlyHistory': [{'monthName': 'Test', 'notes': [{'bankTransactionIds': ['fixture-id'], 'category': 'Costo Fisso'}]}]}, 'entry': {}}
        self.assertEqual(self.request('POST', '/api/state', json.dumps(fixture), headers)[0], 200)
        password = 'fixture password only'
        self.assertEqual(self.request('POST', '/api/backup/export', json.dumps({'password': password}), {'Content-Type': 'application/json'})[0], 400)
        code, _, body = self.request('POST', '/api/backup/export', json.dumps({'password': password}), headers)
        self.assertEqual(code, 200)
        self.assertNotIn(b'fixture-id', body)
        archive = json.loads(body)
        self.assertEqual(set(archive), {'format', 'version', 'salt', 'nonce', 'data'})
        payload = {'archive': archive, 'password': password}
        self.assertEqual(self.request('POST', '/api/backup/import', json.dumps(payload), headers)[0], 400)
        payload['confirmReplace'] = True
        payload['password'] = 'wrong fixture password'
        self.assertEqual(self.request('POST', '/api/backup/import', json.dumps(payload), headers)[0], 400)
        self.assertEqual(json.loads(self.request('GET', '/api/state')[2])['state'], fixture['state'])
        payload['password'] = password
        self.assertEqual(self.request('POST', '/api/backup/import', json.dumps(payload), headers)[0], 200)
        self.assertEqual(json.loads(self.request('GET', '/api/state')[2])['state'], fixture['state'])

    def test_banking_callback_is_automatic_and_cross_origin_posts_stay_blocked(self):
        class FakeBanking:
            redirect_url=f'http://127.0.0.1:{self.port}/api/enable-banking/callback'
            completed=[]
            def complete_authorization(inner, url):
                inner.completed.append(url)
                return {'status':'ok'}
        service=FakeBanking()
        self.handler.enable_banking_service=service
        try:
            status,headers,body=self.request('GET','/api/enable-banking/callback?code=test&state=safe',headers={'Sec-Fetch-Mode':'navigate','Sec-Fetch-Site':'cross-site'})
            self.assertEqual(status,200)
            self.assertIn(b'Conto collegato',body)
            self.assertEqual(service.completed,[service.redirect_url+'?code=test&state=safe'])
            self.assertEqual(self.request('GET','/api/enable-banking/callback?code=x&state=y',headers={'Origin':'https://attacker.invalid','Sec-Fetch-Mode':'navigate'})[0],403)
        finally:
            self.handler.enable_banking_service=None

if __name__=='__main__':unittest.main()

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
from research.engine import ResearchEngine
from local_security import RequestGuard


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.directory=Path(cls.tmp.name)
        cls.patches=[patch.object(bridge,'APP_DATA_DIR',cls.directory),
                     patch.object(bridge,'APP_STATE_FILE',cls.directory/'dashboard-state.json')]
        for p in cls.patches: p.start()
        cls.engine=ResearchEngine(cls.directory/'research.sqlite3')
        class FakePaperLab:
            def snapshot(self): return {'mode':'paper_data_readonly','live_enabled':False,'orders_enabled':False}
            def start(self,port):
                if port not in (7497,4002): raise ValueError('Paper port required')
                return self.snapshot()
            def stop(self): return self.snapshot()
        class FakeWalletService:
            def snapshot(self):
                return {'provider':'Wallet by BudgetBakers','configured':True,'readOnly':False,
                        'writesEnabled':True,'writeScope':'dashboard-managed-records-only','expenses':[],'incomes':[],'records':[]}
            def sync(self): return self.snapshot()
            def create_record(self,record):
                if record.get('amount') != 12.5: raise ValueError('fixture')
                return self.snapshot()
            def update_record(self,record):
                if record.get('walletRecordId') != 'managed-1': raise ValueError('not managed')
                return self.snapshot()
        cls.handler=type('TestHandler',(bridge.DashboardHandler,),{'research_engine':cls.engine,'guard':RequestGuard(),
            'paper_lab':FakePaperLab(),
            'wallet_service':FakeWalletService(),
            'clients':{k:bridge.IbkrAccountClient('127.0.0.1',p,i,k.upper()) for k,p,i in [('live',7496,70),('paper',7497,71)]}})
        cls.server=bridge.ThreadingHTTPServer(('127.0.0.1',0),cls.handler)
        cls.port=cls.server.server_port
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.worker.join();cls.engine.close()
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

    def test_paper_collection_has_no_trading_or_live_switch(self):
        self.assertEqual(self.request('GET','/api/paper-lab/snapshot')[0],200)
        _,_,body=self.request('GET','/')
        token=re.search(rb'name="csrf-token" content="([^"]+)"',body)[1].decode()
        headers={'Content-Type':'application/json','X-CSRF-Token':token}
        for payload in ({'action':'live'}, {'action':'submit'}, {'action':'collect','port':7496}, {'action':'collect','account':'U123'}):
            self.assertEqual(self.request('POST','/api/paper-lab/control',json.dumps(payload),headers)[0],400)
        code,_,body=self.request('POST','/api/paper-lab/control',json.dumps({'action':'collect'}),headers)
        self.assertEqual(code,200)
        self.assertFalse(json.loads(body)['orders_enabled'])

    def test_wallet_manual_mutations_require_csrf_and_reject_unknown_actions(self):
        code,_,body=self.request('GET','/api/wallet/snapshot')
        self.assertEqual(code,200)
        snapshot=json.loads(body)
        self.assertFalse(snapshot['readOnly'])
        self.assertTrue(snapshot['writesEnabled'])
        headers={'Content-Type':'application/json'}
        self.assertEqual(self.request('POST','/api/wallet/control',json.dumps({'action':'sync'}),headers)[0],400)
        headers['X-CSRF-Token']=self.handler.csrf_token
        code,_,body=self.request('POST','/api/wallet/control',json.dumps({'action':'sync'}),headers)
        self.assertEqual(code,200)
        self.assertTrue(json.loads(body)['writesEnabled'])
        self.assertEqual(self.request('POST','/api/wallet/control',json.dumps({'action':'create','record':{'amount':12.5}}),headers)[0],200)
        self.assertEqual(self.request('POST','/api/wallet/control',json.dumps({'action':'update','record':{'walletRecordId':'managed-1'}}),headers)[0],200)
        for action in ('delete','write','transfer'):
            self.assertEqual(self.request('POST','/api/wallet/control',json.dumps({'action':action}),headers)[0],400)

    def test_cross_origin_reads_and_dns_rebinding_denied(self):
        for path in ('/api/state','/api/research/snapshot','/api/live/snapshot','/'):
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

    def test_research_controls_and_no_live_routes(self):
        headers={'Content-Type':'application/json','X-CSRF-Token':self.handler.csrf_token}
        snapshot=json.loads(self.request('GET','/api/research/snapshot')[2])
        self.assertFalse(snapshot['live_enabled'])
        self.assertEqual(len(snapshot['bots']),6)
        self.assertEqual(len(json.loads(self.request('GET','/api/research/strategies')[2])['strategies']),6)
        self.assertEqual(self.request('POST','/api/research/control',json.dumps({'action':'pause'}),headers)[0],200)
        self.assertEqual(self.request('POST','/api/research/control',json.dumps({'action':'enable_live'}),headers)[0],400)
        self.assertEqual(self.request('POST','/api/live/orders','{}',headers)[0],404)
        health=json.loads(self.request('GET','/api/health')[2])
        self.assertTrue(health['readOnlyBridge'])
        self.assertTrue(all(c['status']=='disconnected' for c in health['connections'].values()))

if __name__=='__main__':unittest.main()

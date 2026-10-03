"""Bounded TWS paper data collection. This client cannot submit broker orders.

Account identity plus a paper-only port are required before requesting data.
This is a diagnostic/data collector, not a certification of market-data quality.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import threading
import time

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper

from research.strategies import SPECS
from research.validation import Evidence, assess
from research.bar_replay import screen_all

JOBS = (
    ('mean_reversion', 'AAPL', '1 min', '1 M'),
    ('breakout', 'AAPL', '5 mins', '1 M'),
    ('swing', 'AAPL', '1 day', '6 Y'),
    ('momentum', 'SPY', '1 day', '6 Y'),
    ('momentum', 'QQQ', '1 day', '6 Y'),
    ('momentum', 'IWM', '1 day', '6 Y'),
    ('momentum', 'TLT', '1 day', '6 Y'),
    ('momentum', 'GLD', '1 day', '6 Y'),
)


class PaperDataClient(EWrapper, EClient):
    def __init__(self):
        EWrapper.__init__(self)
        EClient.__init__(self, self)
        self.ready = threading.Event()
        self.finished = threading.Event()
        self.lock = threading.RLock()
        self.accounts = []
        self.identity_verified = False
        self.fatal = None
        self.errors = []
        self.bars = []
        self.request_id = None
        self.current_errors = []
        self.reader = None

    def connect(self, host, port, clientId):
        if host != '127.0.0.1' or type(port) is not int or port not in (7497, 4002):
            raise ValueError('Paper collector only permits loopback 7497/4002')
        return super().connect(host, port, clientId)

    def placeOrder(self, *args, **kwargs):
        raise PermissionError('Data collector: broker orders are disabled')

    def cancelOrder(self, *args, **kwargs):
        raise PermissionError('Data collector: broker cancellations are disabled')

    def reqGlobalCancel(self, *args, **kwargs):
        raise PermissionError('Data collector: global cancellation is disabled')

    def nextValidId(self, orderId):
        self.reqManagedAccts()

    def managedAccounts(self, accountsList):
        accounts = [account.strip() for account in accountsList.split(',') if account.strip()]
        with self.lock:
            self.accounts = accounts
            # DU* alone is not a live-execution permission. No such capability exists here.
            self.identity_verified = len(accounts) == 1 and bool(re.fullmatch(r'DU[A-Z]?[0-9]+', accounts[0]))
            if not self.identity_verified:
                self.fatal = 'paper_account_identity_not_verified'
            self.ready.set()
        if not self.identity_verified:
            self.disconnect()

    def error(self, reqId, errorCode, errorString, *extra):
        with self.lock:
            item = {'request': reqId, 'code': errorCode, 'message': str(errorString)[:700]}
            self.errors.append(item)
            self.errors = self.errors[-40:]
            if reqId == self.request_id:
                self.current_errors.append(item)
                self.finished.set()
            if errorCode in (502, 504, 1100, 1300):
                self.fatal = 'connection_unavailable'
                self.ready.set()
                self.finished.set()

    def connectionClosed(self):
        self.identity_verified = False
        self.fatal = 'connection_closed'
        self.finished.set()

    def historicalData(self, reqId, bar):
        with self.lock:
            if reqId != self.request_id:
                return
            values = [float(getattr(bar, key)) for key in ('open', 'high', 'low', 'close', 'volume')]
            if len(self.bars) >= 10000 or not all(math.isfinite(v) for v in values) or min(values[:4]) <= 0 or values[4] < 0:
                self.current_errors.append({'code': 'invalid_bar'})
                return
            self.bars.append(dict(date=str(bar.date), **dict(zip(('open', 'high', 'low', 'close', 'volume'), values))))

    def historicalDataEnd(self, reqId, start, end):
        if reqId == self.request_id:
            self.finished.set()

    def open_session(self, port=7497, timeout=8):
        self.connect('127.0.0.1', port, clientId=182)
        if not self.isConnected():
            raise ValueError('TWS non espone API sulla porta paper selezionata')
        self.reader = threading.Thread(target=self.run, daemon=True, name='paper-data-reader')
        self.reader.start()
        if not self.ready.wait(timeout) or not self.identity_verified or self.fatal:
            raise ValueError(self.fatal or 'Paper handshake timeout')

    def history(self, index, symbol, size, duration, timeout=20):
        if not self.identity_verified or self.fatal or not self.isConnected():
            raise ValueError('Paper identity/connection not current')
        if (symbol, size, duration) not in [(job[1], job[2], job[3]) for job in JOBS]:
            raise ValueError('Request not allowlisted')
        contract = Contract()
        contract.symbol = symbol
        contract.secType = 'STK'
        contract.exchange = 'SMART'
        contract.currency = 'USD'
        contract.primaryExchange = 'NASDAQ' if symbol in ('AAPL', 'QQQ', 'TLT') else 'ARCA'
        with self.lock:
            self.request_id = 31000 + index
            self.bars = []
            self.current_errors = []
            self.finished.clear()
        self.reqHistoricalData(self.request_id, contract, '', duration, size, 'TRADES', 1, 2, False, [])
        complete = self.finished.wait(timeout)
        self.cancelHistoricalData(self.request_id)
        with self.lock:
            if not complete:
                self.current_errors.append({'code': 'request_timeout', 'message': 'Risposta storica non completata entro il timeout'})
            result = {'symbol': symbol, 'bar_size': size, 'duration': duration,
                      'what_to_show': 'TRADES', 'use_rth': True, 'format_date': 2,
                      'bars': list(self.bars), 'errors': list(self.current_errors),
                      'complete': complete and not self.current_errors and self.identity_verified and not self.fatal}
            self.request_id = None
        return result

    def close(self):
        self.disconnect()
        if self.reader and self.reader is not threading.current_thread():
            self.reader.join(timeout=2)


class PaperLab:
    def __init__(self, directory, client_factory=PaperDataClient):
        self.directory = Path(directory)
        self.factory = client_factory
        self.lock = threading.RLock()
        self.worker = None
        self.cancel = threading.Event()
        self.last_started = 0.0
        self.current = {'status': 'not_connected', 'message': 'Verifica TWS paper per iniziare la raccolta dati.', 'datasets': []}
        self.last_report = None
        path = self.directory / 'latest.json'
        if path.is_file() and path.stat().st_size <= 10 * 1024 * 1024:
            try:
                self.last_report = json.loads(path.read_text())
            except (ValueError, OSError):
                self.current['message'] = 'Report precedente non leggibile: nessuna promozione consentita.'

    def snapshot(self):
        with self.lock:
            datasets = self.current.get('datasets', [])
            if not datasets and self.last_report:
                datasets = self.last_report.get('datasets', [])
            report_hash = hashlib.sha256(json.dumps(datasets, sort_keys=True).encode()).hexdigest()
            assessments = []
            for strategy, spec in SPECS.items():
                spec_hash = hashlib.sha256(json.dumps(asdict(spec), sort_keys=True).encode()).hexdigest()
                result = assess(Evidence(strategy, 'historical_research', spec_hash, report_hash))
                result['bars_collected'] = sum(len(item.get('bars', [])) for item in datasets if item.get('strategy') == strategy)
                result['data_blockers'] = (
                    ['Tick e book consolidato, latenza e costi da validare'] if strategy == 'scalping' else
                    ['Permessi e feed Bitcoin spot da verificare; nessuno strumento sostitutivo'] if strategy == 'bitcoin' else
                    ['OHLC di ricerca: mancano eseguiti, bid/ask storico, validazione OOS e stress test'])
                assessments.append(result)
            return {**{k: v for k, v in self.current.items() if k != 'datasets'},
                    'mode': 'paper_data_readonly', 'orders_enabled': False, 'live_enabled': False,
                    'datasets': [{k: v for k, v in item.items() if k != 'bars'} | {'bars_count': len(item.get('bars', []))} for item in datasets],
                    'validation': assessments,
                    'screening': self.last_report.get('screening', []) if self.last_report else [],
                    'last_collection_at': self.last_report.get('collected_at') if self.last_report else None}

    def start(self, port=7497):
        if type(port) is not int or port not in (7497, 4002):
            raise ValueError('Only paper ports 7497/4002 are accepted')
        with self.lock:
            if self.worker and self.worker.is_alive():
                return self.snapshot()
            if time.monotonic() - self.last_started < 60:
                raise ValueError('Attendi 60 secondi fra raccolte per rispettare il pacing IBKR')
            self.last_started = time.monotonic()
            self.cancel.clear()
            self.current = {'status': 'connecting', 'message': 'Verifica identità paper…', 'datasets': [], 'port': port}
            self.worker = threading.Thread(target=self._collect, args=(port,), daemon=True, name='paper-data-collection')
            self.worker.start()
        return self.snapshot()

    def _collect(self, port):
        client = self.factory()
        report = {'collected_at': datetime.now(timezone.utc).isoformat(), 'source': 'ibkr_paper_api', 'datasets': []}
        try:
            client.open_session(port)
            with self.lock:
                self.current.update(status='collecting', message='Conto paper riconosciuto. Raccolta dati di ricerca; nessun ordine.')
            for index, (strategy, symbol, size, duration) in enumerate(JOBS):
                if self.cancel.is_set():
                    break
                dataset = client.history(index, symbol, size, duration)
                dataset['strategy'] = strategy
                report['datasets'].append(dataset)
                with self.lock:
                    self.current['datasets'] = list(report['datasets'])
                if self.cancel.wait(1):
                    break
            report['cancelled'] = self.cancel.is_set()
            report['screening'] = screen_all(report['datasets'], time.time())
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            name = 'collection-' + str(time.time_ns()) + '.json'
            path = self.directory / name
            payload = json.dumps(report, ensure_ascii=False, allow_nan=False)
            with path.open('x', encoding='utf-8') as handle:
                path.chmod(0o600)
                handle.write(payload)
            temporary = self.directory / 'latest.json.tmp'
            temporary.write_text(payload, encoding='utf-8')
            temporary.chmod(0o600)
            temporary.replace(self.directory / 'latest.json')
            with self.lock:
                self.last_report = report
                self.current.update(status=('collected' if all(d.get('complete') for d in report['datasets']) else 'partial') if not report['cancelled'] else 'stopped',
                                    message='Raccolta terminata. Dati e qualità da validare prima degli ordini paper.')
        except Exception as error:
            with self.lock:
                self.current.update(status='blocked', message=str(error), errors=list(client.errors))
        finally:
            client.close()

    def stop(self):
        self.cancel.set()
        return self.snapshot()

"""Bounded read-only quote probe; no orders or paid/regulatory snapshots."""
from copy import copy
from datetime import datetime, timedelta, timezone
import json
import threading
import sys
from urllib.request import urlopen

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper
import ibapi.client as client_protocol


class Probe(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.ready = threading.Event()
        self.positions_done = threading.Event()
        self.tick = threading.Event()
        self.contracts = {}

    def nextValidId(self, orderId):
        self.ready.set()

    def position(self, account, contract, pos, avgCost):
        if pos and contract.secType == "STK":
            self.contracts[contract.conId] = copy(contract)

    def positionEnd(self):
        self.positions_done.set()

    def marketDataType(self, reqId, marketDataType):
        print(json.dumps({"request": reqId, "type": marketDataType}), flush=True)

    def tickPrice(self, reqId, tickType, price, attrib):
        if tickType in {1, 2, 66, 67}:
            print(json.dumps({"request": reqId, "tick": tickType, "price": price}), flush=True)
            if price > 0:
                self.tick.set()

    def historicalData(self, reqId, bar):
        self.contracts[reqId] = {'date': bar.date, 'price': bar.close}

    def historicalDataEnd(self, reqId, start, end):
        print(json.dumps({'request': reqId, 'lastHistoricalQuote': self.contracts.get(reqId)}), flush=True)
        self.tick.set()

    def error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson=""):
        if reqId >= 7000000:
            print(json.dumps({"request": reqId, "code": errorCode, "message": errorString}), flush=True)


probe = Probe()
try:
    if '--legacy' in sys.argv:
        client_protocol.MAX_CLIENT_VER = 178
    probe.connect("127.0.0.1", 7496, 947553)
    threading.Thread(target=probe.run, daemon=True).start()
    if not probe.ready.wait(10):
        raise SystemExit("TWS unavailable")
    print(json.dumps({'serverVersion': probe.serverVersion()}), flush=True)
    with urlopen('http://127.0.0.1:8767/api/live/snapshot', timeout=5) as response:
        snapshot = json.load(response)
    for position in snapshot.get('positions', [])[:1]:
        contract = Contract()
        contract.conId = position['conId']
        contract.symbol = position['symbol']
        contract.secType = position['securityType']
        contract.currency = position['currency']
        contract.exchange = position.get('exchange') or 'SMART'
        venues = ('IEX', 'NASDAQ') if '--iex' in sys.argv else ('SMART', contract.exchange or 'SMART')
        for index, exchange in enumerate(venues):
            request_id = 7000000 + index
            quoted = copy(contract)
            quoted.exchange = exchange
            print(json.dumps({"request": request_id, "exchange": exchange}), flush=True)
            if '--historical' in sys.argv:
                quoted.exchange = 'SMART'
                probe.tick.clear()
                end = (datetime.now(timezone.utc) - timedelta(minutes=20)).strftime('%Y%m%d-%H:%M:%S')
                probe.reqHistoricalData(request_id, quoted, end, '1 D', '1 min', 'BID' if index == 0 else 'ASK', 0, 2, False, [])
                if not probe.tick.wait(20):
                    print(json.dumps({'request': request_id, 'timeout': True}), flush=True)
                    probe.cancelHistoricalData(request_id)
            else:
                probe.reqMarketDataType(1 if '--iex' in sys.argv else 4)
                probe.reqMktData(request_id, quoted, "", False, False, [])
        if '--historical' in sys.argv:
            continue
        probe.tick.wait(15)
        probe.cancelMktData(7000000)
        probe.cancelMktData(7000001)
finally:
    probe.disconnect()

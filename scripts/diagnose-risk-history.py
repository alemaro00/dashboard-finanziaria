"""Bounded, read-only IBKR history probe; never orders or paid snapshots."""
from copy import copy
import json
import threading

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper


class Probe(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.ready = threading.Event()
        self.positions_done = threading.Event()
        self.contracts = {}
        self.requests = {}

    def nextValidId(self, orderId):
        self.ready.set()

    def position(self, account, contract, pos, avgCost):
        if pos and contract.secType == "STK":
            self.contracts[contract.conId] = copy(contract)

    def positionEnd(self):
        self.positions_done.set()

    def historicalData(self, reqId, bar):
        record = self.requests.get(reqId)
        if record is not None:
            record["bars"] += 1
            day = str(bar.date)
            record["first"] = min(record.get("first", day), day)
            record["last"] = max(record.get("last", day), day)

    def historicalDataEnd(self, reqId, start, end):
        if reqId in self.requests:
            self.requests[reqId]["event"].set()

    def error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson=""):
        if errorCode in {10285, 2188, 2176}:
            print(json.dumps({"warning": errorCode, "message": errorString}), flush=True)
            return
        if reqId in self.requests:
            record = self.requests[reqId]
            record["code"] = errorCode
            record["permissionDenied"] = "permission" in errorString.lower() or "subscribed" in errorString.lower()
            record["event"].set()


def main():
    probe = Probe()
    try:
        probe.connect("127.0.0.1", 7496, 947551)
        threading.Thread(target=probe.run, daemon=True).start()
        if not probe.ready.wait(10):
            print(json.dumps({"status": "TWS connection unavailable"}))
            return
        probe.reqPositions()
        if not probe.positions_done.wait(10):
            print(json.dumps({"status": "positions unavailable"}))
            return
        probe.cancelPositions()
        # A separate API client avoids altering the dashboard quote mode.
        probe.reqMarketDataType(3)
        for index, contract in enumerate(list(probe.contracts.values())[:1]):
            for offset, exchange in enumerate(dict.fromkeys([contract.exchange or "SMART", "SMART"])):
                request_id = 8000000 + index * 10 + offset
                record = {"event": threading.Event(), "bars": 0, "exchange": exchange, "mode": "delayed", "series": "ADJUSTED_LAST"}
                probe.requests[request_id] = record
                contract.exchange = exchange
                probe.reqHistoricalData(request_id, contract, "", "10 Y", "1 day", "ADJUSTED_LAST", 1, 1, False, [])
                if not record["event"].wait(25):
                    record["timeout"] = True
                    probe.cancelHistoricalData(request_id)
                print(json.dumps({k: v for k, v in record.items() if k != "event"}), flush=True)
        contract = Contract()
        contract.symbol, contract.currency, contract.secType, contract.exchange = "EUR", "USD", "CASH", "IDEALPRO"
        request_id = 8000100
        record = {"event": threading.Event(), "bars": 0, "exchange": "IDEALPRO", "series": "MIDPOINT"}
        probe.requests[request_id] = record
        probe.reqHistoricalData(request_id, contract, "", "10 Y", "1 day", "MIDPOINT", 1, 1, False, [])
        if not record["event"].wait(25):
            record["timeout"] = True
            probe.cancelHistoricalData(request_id)
        print(json.dumps({k: v for k, v in record.items() if k != "event"}), flush=True)
    finally:
        probe.disconnect()


if __name__ == "__main__":
    main()

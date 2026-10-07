"""Bounded read-only TRADES/RTH close probe; no orders or quote subscriptions."""
import json
from pathlib import Path
import sys
import threading
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from closing_prices import ClosingPriceMonitor, completed_through
from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper


class Probe(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.lock = threading.RLock()
        self.ready = threading.Event()
        self.stop_event = threading.Event()
        self.metadata_done = threading.Event()
        self.metadata = {}
        self.closes = ClosingPriceMonitor(self)

    def nextValidId(self, orderId):
        self.ready.set()

    def contractDetails(self, reqId, details):
        self.metadata = {"timeZoneId": details.timeZoneId, "liquidHours": details.liquidHours}
        self.contract = details.contract

    def contractDetailsEnd(self, reqId):
        self.metadata_done.set()

    def historicalData(self, reqId, bar):
        self.closes.bar(reqId, bar)

    def historicalDataEnd(self, reqId, start, end):
        self.closes.end(reqId)

    def error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson=""):
        if reqId in self.closes.requests:
            print(json.dumps({"code": errorCode, "message": errorString}), flush=True)
            self.closes.failed(reqId, errorCode, errorString)


def main():
    data = json.load(urllib.request.urlopen("http://127.0.0.1:8767/api/live/snapshot", timeout=10))
    positions = [p for p in data.get("positions", []) if p.get("quantity") and p.get("securityType") == "STK"]
    if not positions:
        print("No stock positions")
        return
    probe = Probe()
    try:
        probe.connect("127.0.0.1", 7496, 947555)
        threading.Thread(target=probe.run, daemon=True).start()
        if not probe.ready.wait(10):
            print("TWS connection unavailable")
            return
        p = positions[0]
        contract = Contract()
        contract.conId, contract.secType, contract.exchange, contract.currency = p["conId"], "STK", "SMART", p["currency"]
        probe.reqContractDetails(8800000, contract)
        if not probe.metadata_done.wait(10):
            print("Contract metadata unavailable")
            return
        cutoff = completed_through(probe.metadata)
        if cutoff is None:
            print("Exchange timezone unavailable")
            return
        probe.closes._request(probe.contract, cutoff, probe.closes.generation)
        print(json.dumps({"symbol": p["symbol"], "currency": p["currency"], "completedThrough": cutoff.isoformat(),
                          "close": probe.closes.quotes.get(p["conId"], {})}), flush=True)
    finally:
        probe.disconnect()


if __name__ == "__main__":
    main()

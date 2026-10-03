import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

from wallet_sync import WalletClient, WalletSyncService, normalize_wallet_expense, normalize_wallet_record


class FakeClient:
    def __init__(self):
        self.records = [
            {"id":"expense-1","recordType":"expense","recordDate":"2026-09-12T10:30:00Z","amount":{"value":-24.90,"currencyCode":"EUR"},"counterParty":"ESSELUNGA","category":{"id":"food","name":"Groceries"},"accountId":"cash","accountName":"Revolut","source":"backend"},
            {"id":"income-1","recordType":"income","recordDate":"2026-09-12T10:30:00Z","amount":{"value":2000,"currencyCode":"EUR"},"counterParty":"Employer","category":{"id":"salary","name":"Salary"},"accountId":"cash","accountName":"Revolut","source":"backend"},
        ]
        self.last_patch = None
    def get(self,path,query=None):
        if path=="/v1/api/records": return {"records":self.records},{"X-Last-Data-Change-At":"2026-09-12T10:31:00Z"}
        if path=="/v1/api/accounts": return {"accounts":[{"id":"cash","name":"Revolut","balance":{"currencyCode":"EUR"},"isBankSync":True}]},{}
        if path=="/v1/api/categories": return {"categories":[{"id":"food","name":"Groceries","group":{"name":"Food"},"enabled":True},{"id":"salary","name":"Salary","group":{"name":"Income"},"enabled":True}]},{}
        raise AssertionError(path)
    def post(self,path,payload):
        self.assert_path(path); item=payload[0]; created={"id":"manual-1","recordType":"expense" if item["amount"]["value"]<0 else "income","source":"rest","accountName":"Revolut","category":{"id":item.get("categoryId"),"name":"Groceries"},**item}
        self.records.append(created); return {"results":[{"success":True,"id":"manual-1","record":created}]},{}
    def patch(self,path,payload,query=None):
        self.assert_path(path); self.last_patch=(payload,query); item=payload[0]
        target=next(x for x in self.records if x["id"]==item["id"]); target.update(item); target["recordType"]="expense" if item["amount"]["value"]<0 else "income"
        return {"results":[{"success":True,"id":item["id"],"record":target}]},{}
    def assert_path(self,path):
        if path!="/v1/api/records": raise AssertionError(path)


class WalletSyncTests(unittest.TestCase):
    def test_normalizes_income_and_expense(self):
        expense=normalize_wallet_expense({"id":"a","recordType":"expense","recordDate":"2026-09-11","amount":{"value":-12.5,"currencyCode":"EUR"},"category":{"name":"Food"}})
        income=normalize_wallet_record({"id":"b","recordType":"income","recordDate":"2026-09-11","amount":{"value":100,"currencyCode":"EUR"},"category":{"name":"Salary"}})
        self.assertEqual(expense["amount"],12.5); self.assertEqual(income["recordType"],"income"); self.assertEqual(income["signedAmount"],100)

    def test_rejects_transfer_nan_and_zero(self):
        base={"id":"x","recordDate":"2026-09-11","amount":{"value":-10,"currencyCode":"EUR"}}
        self.assertIsNone(normalize_wallet_record({**base,"recordType":"transfer"}))
        self.assertIsNone(normalize_wallet_record({**base,"amount":{"value":"NaN"}}))
        self.assertIsNone(normalize_wallet_record({**base,"amount":{"value":0}}))

    def test_sync_reads_income_expense_accounts_categories(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ,{"WALLET_API_TOKEN":"x"*40}):
            service=WalletSyncService(Path(temporary)); client=FakeClient(); service._client=lambda:client
            snapshot=service.sync()
            self.assertEqual(len(snapshot["records"]),2); self.assertEqual(len(snapshot["expenses"]),1); self.assertEqual(len(snapshot["incomes"]),1)
            self.assertEqual(snapshot["accounts"][0]["currency"],"EUR"); self.assertFalse(snapshot["readOnly"]); self.assertTrue(snapshot["writesEnabled"])

    def test_create_then_update_only_dashboard_managed_record(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ,{"WALLET_API_TOKEN":"x"*40}):
            service=WalletSyncService(Path(temporary)); client=FakeClient(); service._client=lambda:client; service.sync()
            record={"recordType":"expense","accountId":"cash","categoryId":"food","date":"2026-09-12","amount":8.5,"counterParty":"Bar","note":"Caffè","paymentType":"debit_card"}
            created=service.create_record(record); manual=next(x for x in created["records"] if x["walletRecordId"]=="manual-1")
            self.assertTrue(manual["editable"])
            service.update_record({**record,"walletRecordId":"manual-1","amount":9})
            self.assertEqual(client.last_patch[1],{"validation":"strict"})
            with self.assertRaises(ValueError): service.update_record({**record,"walletRecordId":"expense-1"})

    def test_invalid_account_and_fields_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ,{"WALLET_API_TOKEN":"x"*40}):
            service=WalletSyncService(Path(temporary)); service._client=lambda:FakeClient(); service.sync()
            with self.assertRaises(ValueError): service.create_record({"recordType":"expense","accountId":"bad","date":"2026-09-12","amount":2,"paymentType":"cash"})
            with self.assertRaises(ValueError): service.create_record({"recordType":"expense","accountId":"cash","date":"2026-09-12","amount":2,"paymentType":"cash","delete":True})

    def test_token_validation(self):
        with self.assertRaises(ValueError): WalletClient("too-short")

if __name__=="__main__": unittest.main()

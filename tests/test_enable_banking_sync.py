import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from enable_banking_sync import EnableBankingClient, EnableBankingService, normalize_account, normalize_transaction


class FakeClient:
    def __init__(self):
        self.posts = []

    def _validate_key(self):
        return None

    def get(self, path, query=None):
        if path == "/application":
            return {"name": "Dashboard Finanziaria", "environment": "PRODUCTION", "active": True, "services": ["AIS"]}
        if path == "/aspsps":
            return {"aspsps": [{"name": "Revolut", "country": "IT", "maximum_consent_validity": 180}, {"name": "UniCredit", "country": "IT"}]}
        if path == "/sessions/session-1":
            return {"accounts": ["eur-account", "usd-account"], "aspsp": {"name": "Revolut", "country": "IT"}}
        if path.endswith("/details"):
            account_id = path.split("/")[2]
            currency = "USD" if account_id == "usd-account" else "EUR"
            return {"uid": account_id, "currency": currency, "name": f"Revolut {currency}", "account_id": {"iban": "IT00TEST0001"}}
        if path.endswith("/balances"):
            currency = "USD" if "usd-account" in path else "EUR"
            return {"balances": [{"balance_amount": {"amount": "100.25", "currency": currency}}]}
        if path.endswith("/transactions"):
            account_id = path.split("/")[2]
            currency = "USD" if account_id == "usd-account" else "EUR"
            return {"transactions": [{
                "transaction_id": f"tx-{account_id}", "booking_date": "2026-10-02",
                "credit_debit_indicator": "DBIT", "transaction_amount": {"amount": "12.50", "currency": currency},
                "creditor": {"name": "Negozio"},
            }]}
        raise AssertionError((path, query))

    def post(self, path, payload):
        self.posts.append((path, payload))
        if path == "/auth":
            return {"url": "https://tilisy.enablebanking.com/ais/start/example"}
        if path == "/sessions":
            return {"session_id": "session-1", "accounts": ["eur-account", "usd-account"]}
        raise AssertionError((path, payload))


class EnableBankingTests(unittest.TestCase):
    def test_normalizes_debit_credit_and_multicurrency_accounts(self):
        eur = normalize_account({"uid": "a", "currency": "EUR", "account_id": {"iban": "IT001234"}}, "Revolut")
        usd = normalize_account({"uid": "b", "currency": "USD", "account_id": {"iban": "IT001234"}}, "Revolut")
        debit = normalize_transaction({"transaction_id": "d", "booking_date": "2026-10-01", "credit_debit_indicator": "DBIT", "transaction_amount": {"amount": "8.4", "currency": "EUR"}}, eur)
        credit = normalize_transaction({"transaction_id": "c", "booking_date": "2026-10-01", "credit_debit_indicator": "CRDT", "transaction_amount": {"amount": "10", "currency": "EUR"}}, eur)
        self.assertNotEqual(eur["id"], usd["id"])
        self.assertEqual((eur["currency"], usd["currency"]), ("EUR", "USD"))
        self.assertEqual((debit["signedAmount"], credit["signedAmount"]), (-8.4, 10.0))

    def test_private_key_permissions_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            key = Path(temporary) / "key.pem"
            key.write_text("x" * 1800)
            key.chmod(0o644)
            with self.assertRaises(ValueError):
                EnableBankingClient(key)._validate_key()
            key.chmod(0o600)
            EnableBankingClient(key)._validate_key()

    def test_state_mismatch_and_expiry_are_rejected_before_exchange(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = EnableBankingService(Path(temporary), Path(temporary) / "unused.pem", "http://127.0.0.1:8767/api/enable-banking/callback")
            service._save({**service._empty(), "pending": {"stateHash": "wrong", "createdAt": time.time()}})
            with self.assertRaisesRegex(ValueError, "Stato"):
                service.complete_authorization("http://127.0.0.1:8767/api/enable-banking/callback?code=abc&state=bad")

    def test_authorization_and_sync_preserve_same_iban_accounts_by_uid(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = EnableBankingService(Path(temporary), Path(temporary) / "unused.pem", "http://127.0.0.1:8767/api/enable-banking/callback")
            client = FakeClient()
            service._client = lambda: client
            with patch("enable_banking_sync.secrets.token_urlsafe", return_value="state-value"):
                result = service.start_authorization("Revolut", "IT")
            self.assertEqual(result["status"], "authorization_required")
            snapshot = service.complete_authorization("http://127.0.0.1:8767/api/enable-banking/callback?code=abc&state=state-value")
            self.assertEqual(len(snapshot["accounts"]), 2)
            self.assertEqual({a["currency"] for a in snapshot["accounts"]}, {"EUR", "USD"})
            self.assertEqual(len(snapshot["records"]), 2)
            self.assertTrue(snapshot["readOnly"])
            self.assertFalse(snapshot["writesEnabled"])

    def test_verify_stores_only_safe_application_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = EnableBankingService(Path(temporary), Path(temporary) / "unused.pem")
            service._client = lambda: FakeClient()
            snapshot = service.verify()
            self.assertTrue(snapshot["application"]["active"])
            self.assertEqual(snapshot["application"]["services"], ["AIS"])

    def test_available_banks_are_normalized_for_simple_setup(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = EnableBankingService(Path(temporary), Path(temporary) / "unused.pem")
            service._client = lambda: FakeClient()
            result = service.list_banks("it")
            self.assertEqual([item["name"] for item in result["banks"]], ["Revolut", "UniCredit"])
            self.assertEqual(result["banks"][0]["maximumConsentDays"], 180)

    def test_callback_must_match_configured_loopback_exactly(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = EnableBankingService(Path(temporary), Path(temporary) / "unused.pem", "http://127.0.0.1:8767/api/enable-banking/callback")
            service._save({**service._empty(), "pending": {"stateHash": "wrong", "createdAt": time.time()}})
            for callback in (
                "https://127.0.0.1:8767/api/enable-banking/callback?code=a&state=b",
                "http://127.0.0.1:8766/api/enable-banking/callback?code=a&state=b",
                "http://localhost:8767/api/enable-banking/callback?code=a&state=b",
                "http://127.0.0.1:8767/other?code=a&state=b",
            ):
                with self.assertRaisesRegex(ValueError, "Indirizzo"):
                    service.complete_authorization(callback)

    def test_custom_name_is_local_and_survives_sync(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = EnableBankingService(Path(temporary), Path(temporary) / "unused.pem")
            client = FakeClient()
            service._client = lambda: client
            service._save({**service._empty(), "sessions": [{"id": "session-1", "bank": "Revolut"}]})
            first = service.sync()
            record = first["records"][0]
            original_description = record["description"]
            renamed = service.rename_record(record["id"], "Pantaloni Zalando")
            self.assertEqual(next(item for item in renamed["records"] if item["id"] == record["id"])["customName"], "Pantaloni Zalando")
            refreshed = service.sync()
            matching = next(item for item in refreshed["records"] if item["id"] == record["id"])
            self.assertEqual(matching["customName"], "Pantaloni Zalando")
            self.assertEqual(matching["description"], original_description)


if __name__ == "__main__":
    unittest.main()

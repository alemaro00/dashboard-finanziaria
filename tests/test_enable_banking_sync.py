import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from enable_banking_sync import (
    EnableBankingAPIError,
    EnableBankingClient,
    EnableBankingService,
    normalize_account,
    normalize_transaction,
)


class FakeClient:
    def __init__(self):
        self.posts = []

    def _validate_key(self):
        return None

    def get(self, path, query=None):
        if path == "/application":
            return {"name": "Dashboard Finanziaria", "environment": "PRODUCTION", "active": True, "services": ["AIS"]}
        if path == "/aspsps":
            return {"aspsps": [{"name": "Revolut", "country": "IT", "maximum_consent_validity": 180 * 86400}, {"name": "UniCredit", "country": "IT"}]}
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
    def test_expired_pending_is_not_shown_and_can_be_cancelled(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = EnableBankingService(Path(temporary), Path(temporary) / "unused.pem")
            service._client = lambda: FakeClient()
            service._save({**service._empty(), "pending": {"createdAt": time.time() - 1201}})
            self.assertFalse(service.snapshot()["authorizationPending"])
            self.assertFalse(service.cancel_authorization()["authorizationPending"])

    def test_bank_limit_in_seconds_and_decoupled_auth_without_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = EnableBankingService(Path(temporary), Path(temporary) / "unused.pem")
            client = FakeClient()
            original_get = client.get
            client.get = lambda path, query=None: {"aspsps": [{"name": "Revolut", "country": "IT", "maximum_consent_validity": 30 * 86400, "auth_methods": [{"name": "app", "approach": "DECOUPLED", "psu_type": "personal", "credentials": []}]}]} if path == "/aspsps" else original_get(path, query)
            service._client = lambda: client
            service.start_authorization("Revolut", "IT", 180)
            payload = client.posts[-1][1]
            self.assertEqual(payload["auth_method"], "app")
            self.assertLessEqual(datetime.fromisoformat(payload["access"]["valid_until"]) - datetime.now(timezone.utc), timedelta(days=30))

    def test_same_remote_reference_from_different_accounts_does_not_collide(self):
        raw = {"transaction_id": "same", "booking_date": "2026-10-01", "transaction_amount": {"amount": "8", "currency": "EUR"}}
        self.assertNotEqual(normalize_transaction(raw, {"id": "a"})["id"], normalize_transaction(raw, {"id": "b"})["id"])

    def test_short_consent_limit_is_not_rounded_up_to_a_day(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = EnableBankingService(Path(temporary), Path(temporary) / "unused.pem")
            client = FakeClient()
            service._client = lambda: client
            service.list_banks = lambda country: {"banks": [{"name": "Revolut", "maximumConsentDays": 1, "maximumConsentSeconds": 3600}]}
            service.start_authorization("Revolut", "IT", 180)
            expiry = datetime.fromisoformat(client.posts[-1][1]["access"]["valid_until"])
            self.assertLessEqual(expiry - datetime.now(timezone.utc), timedelta(seconds=3600))

    def test_selected_accounts_only_are_read_and_old_identifiers_survive_renewal(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = EnableBankingService(Path(temporary), Path(temporary) / "unused.pem")
            client = FakeClient()
            service._client = lambda: client
            account = normalize_account(client.get('/accounts/eur-account/details'), 'Revolut')
            old_record = normalize_transaction(client.get('/accounts/eur-account/transactions')['transactions'][0], account)
            old_record['id'] = 'legacy-classification-id'
            old_record['customName'] = 'Nome classificato'
            service._save({**service._empty(), 'sessions': [{'id': 'session-1', 'bank': 'Revolut', 'accounts': [account], 'selectionRequired': True}], 'accounts': [account], 'records': [old_record]})
            reads = []
            original = client.get
            def tracked(path, query=None):
                reads.append(path)
                return original(path, query)
            client.get = tracked
            result = service.select_accounts(['eur-account'])
            self.assertNotIn('/accounts/usd-account/transactions', reads)
            self.assertNotIn('/accounts/usd-account/balances', reads)
            record = next(item for item in result['records'] if item['accountId'] == 'eur-account')
            self.assertEqual(record['id'], 'legacy-classification-id')
            self.assertEqual(record['customName'], 'Nome classificato')

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
            self.assertTrue(snapshot["selectionRequired"])
            self.assertEqual(snapshot["records"], [])
            snapshot = service.select_accounts([item["id"] for item in snapshot["accounts"]])
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

    def test_sync_retries_supported_transaction_period_and_preserves_older_history(self):
        class LimitedHistoryClient(FakeClient):
            def __init__(self):
                super().__init__()
                self.transaction_queries = []

            def get(self, path, query=None):
                if path == "/sessions/session-1":
                    return {"accounts": ["eur-account"], "aspsp": {"name": "Revolut", "country": "IT"}}
                if path.endswith("/transactions"):
                    self.transaction_queries.append(query.copy())
                    minimum = (datetime.now(timezone.utc) - timedelta(days=60)).date().isoformat()
                    if query["date_from"] < minimum:
                        raise EnableBankingAPIError(422, "Requested time period out of bound", "WRONG_TRANSACTIONS_PERIOD")
                return super().get(path, query)

        with tempfile.TemporaryDirectory() as temporary:
            service = EnableBankingService(Path(temporary), Path(temporary) / "unused.pem")
            client = LimitedHistoryClient()
            service._client = lambda: client
            old_record = {
                "id": "old-record",
                "accountId": "eur-account",
                "date": "2020-01-02",
                "recordType": "expense",
                "customName": "Storico conservato",
            }
            service._save({
                **service._empty(),
                "sessions": [{"id": "session-1", "bank": "Revolut"}],
                "records": [old_record],
            })

            snapshot = service.sync()

            expected_start = (datetime.now(timezone.utc) - timedelta(days=60)).date().isoformat()
            self.assertEqual([item["date_from"] for item in client.transaction_queries], [
                (datetime.now(timezone.utc) - timedelta(days=90)).date().isoformat(),
                expected_start,
            ])
            self.assertEqual(snapshot["transactionHistoryFrom"], expected_start)
            self.assertIn("old-record", {item["id"] for item in snapshot["records"]})
            self.assertIn("tx-eur-account", {item.get("bankRecordId") for item in snapshot["records"]})

    def test_rate_limit_keeps_cached_accounts_and_returns_non_destructive_warning(self):
        class RateLimitedClient(FakeClient):
            def get(self, path, query=None):
                raise EnableBankingAPIError(429, "Limite temporaneo", "RATE_LIMIT")

        with tempfile.TemporaryDirectory() as temporary:
            service = EnableBankingService(Path(temporary), Path(temporary) / "unused.pem")
            service._client = lambda: RateLimitedClient()
            cached_account = {
                "id": "eur-account",
                "name": "Revolut EUR",
                "bank": "Revolut",
                "currency": "EUR",
            }
            cached_record = {
                "id": "old-record",
                "accountId": "eur-account",
                "date": "2026-09-02",
                "recordType": "expense",
            }
            service._save({
                **service._empty(),
                "sessions": [{"id": "session-1", "bank": "Revolut"}],
                "accounts": [cached_account],
                "records": [cached_record],
                "lastSync": "2026-10-03T01:38:00+00:00",
            })

            snapshot = service.sync()

            self.assertEqual(snapshot["accounts"], [cached_account])
            self.assertEqual(snapshot["records"], [cached_record])
            self.assertEqual(snapshot["error"], "")
            self.assertIn("pausa temporanea", snapshot["warning"])


if __name__ == "__main__":
    unittest.main()

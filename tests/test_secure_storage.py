import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import secure_storage as storage


class StorageTests(unittest.TestCase):
    def test_encrypted_write_migration_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(storage, "local_key", return_value=b"k" * 32):
            path = Path(directory) / "state.json"
            path.write_bytes(b'{"sensitive":"monthly-data"}')
            storage.migrate(path)
            self.assertTrue(path.read_bytes().startswith(storage.MAGIC))
            self.assertNotIn(b"monthly-data", path.read_bytes())
            self.assertEqual(json.loads(storage.read_bytes(path))["sensitive"], "monthly-data")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            damaged = bytearray(path.read_bytes()); damaged[-1] ^= 1
            path.write_bytes(damaged)
            with self.assertRaises(ValueError): storage.read_bytes(path)

    def test_portable_backup_roundtrip_password_and_tampering(self):
        document = {"format": "dashboard-auto-state", "state": {"monthlyHistory": [{"monthName": "Settembre", "notes": [{"category": "Costo Fisso", "bankTransactionIds": ["stable-id"]}]}]}}
        archive = storage.export_backup(document, "una password sicura")
        self.assertNotIn("Settembre", json.dumps(archive))
        self.assertEqual(storage.import_backup(archive, "una password sicura"), document)
        with self.assertRaises(ValueError): storage.import_backup(archive, "una password errata")
        archive["data"] = "AAAA"
        with self.assertRaises(ValueError): storage.import_backup(archive, "una password sicura")

    def test_missing_key_cannot_read_encrypted_data_or_overwrite_on_failed_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state"
            with patch.object(storage, "local_key", return_value=b"a" * 32): storage.atomic_write(path, b"original")
            previous = path.read_bytes()
            with patch.object(storage, "local_key", side_effect=RuntimeError("locked")):
                with self.assertRaises(RuntimeError): storage.atomic_write(path, b"replacement")
            self.assertEqual(path.read_bytes(), previous)
            with patch.object(storage, "local_key", return_value=None):
                with self.assertRaises(RuntimeError): storage.read_bytes(path)

    def test_symlink_rejected_and_password_minimum(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"; target.write_bytes(b"original")
            link = Path(directory) / "link"; link.symlink_to(target)
            with self.assertRaises(ValueError): storage.atomic_write(link, b"overwrite")
            self.assertEqual(target.read_bytes(), b"original")
        with self.assertRaises(ValueError): storage.export_backup({}, "short")

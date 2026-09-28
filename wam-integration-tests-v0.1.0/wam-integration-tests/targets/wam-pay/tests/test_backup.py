import sqlite3
from pathlib import Path

from scripts.backup import backup
from tests.helpers import ServiceCase


class BackupTests(ServiceCase):
    def test_live_database_backup_preserves_invoices_and_receipts(self):
        inv = self.invoice(); self.pay(inv)
        destination = Path(self.tmp.name) / "backup.sqlite3"
        backup(self.cfg.database, destination)
        db = sqlite3.connect(destination)
        try:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("SELECT status,confirmed_units FROM invoices").fetchone(), ("paid", 1_000_000_000))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM payments").fetchone()[0], 1)
        finally:
            db.close()

    def test_existing_backup_never_overwritten(self):
        destination = Path(self.tmp.name) / "existing.sqlite3"
        destination.write_bytes(b"keep me")
        with self.assertRaises(FileExistsError): backup(self.cfg.database, destination)
        self.assertEqual(destination.read_bytes(), b"keep me")

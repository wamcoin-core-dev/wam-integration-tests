import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.errors import ConflictError

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS invoices (
 id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
 request_hash TEXT NOT NULL, address TEXT NOT NULL UNIQUE,
 amount_units INTEGER NOT NULL CHECK(amount_units > 0), memo TEXT NOT NULL,
 created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
 required_confirmations INTEGER NOT NULL CHECK(required_confirmations >= 1),
 status TEXT NOT NULL DEFAULT 'pending', received_units INTEGER NOT NULL DEFAULT 0,
 confirmed_units INTEGER NOT NULL DEFAULT 0, needs_review INTEGER NOT NULL DEFAULT 0,
 checked_at INTEGER, checked_tip TEXT
);
CREATE TABLE IF NOT EXISTS payments (
 txid TEXT NOT NULL, vout INTEGER NOT NULL, invoice_id TEXT NOT NULL REFERENCES invoices(id),
 amount_units INTEGER NOT NULL CHECK(amount_units > 0), confirmations INTEGER NOT NULL,
 active INTEGER NOT NULL, first_seen_at INTEGER NOT NULL,
 PRIMARY KEY(txid, vout)
);
CREATE INDEX IF NOT EXISTS payments_invoice ON payments(invoice_id);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id TEXT NOT NULL REFERENCES invoices(id),
 at INTEGER NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path, binding):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ConflictError("Unsupported database schema version")
            db.executescript(SCHEMA)
            encoded = json.dumps(binding, sort_keys=True)
            old = db.execute("SELECT value FROM meta WHERE key='binding'").fetchone()
            if old and old[0] != encoded:
                raise ConflictError("Database belongs to another mode, network or wallet; use a separate database")
            db.execute("INSERT OR IGNORE INTO meta VALUES ('binding', ?)", (encoded,))
            db.execute("PRAGMA user_version=1")
        try:
            Path(path).chmod(0o600)
        except OSError:
            pass

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def event(db, invoice_id, now, kind, detail):
        db.execute("INSERT INTO events(invoice_id,at,kind,detail) VALUES (?,?,?,?)",
                   (invoice_id, now, kind, json.dumps(detail, sort_keys=True)))

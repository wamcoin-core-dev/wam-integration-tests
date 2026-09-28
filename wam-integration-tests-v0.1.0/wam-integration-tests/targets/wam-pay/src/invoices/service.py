import hashlib
import json
import logging
import re
import threading
import time
import uuid

from src.errors import ConflictError, NodeUnavailable, ValidationError
from src.invoices.amounts import format_amount, parse_amount
from src.payments.state import derive_state

LOG = logging.getLogger("wam_pay")


class InvoiceService:
    def __init__(self, store, wallet, cfg, clock=time.time):
        self.store, self.wallet, self.cfg, self.clock = store, wallet, cfg, clock
        self.lock = threading.RLock()
        self.last_sync = None
        self.sync_error = "not_synced"
        if cfg.mode == "demo":
            with store.connect() as db:
                wallet.hydrate(db.execute("SELECT * FROM payments").fetchall())

    def create(self, body, key):
        if not isinstance(body, dict) or set(body) - {"amount", "memo", "expires_in_seconds"}:
            raise ValidationError("Allowed fields: amount, memo, expires_in_seconds")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key):
            raise ValidationError("Idempotency-Key must be 8–128 URL-safe characters")
        amount = parse_amount(body.get("amount"))
        memo = body.get("memo", "")
        ttl = body.get("expires_in_seconds", self.cfg.invoice_ttl_seconds)
        if not isinstance(memo, str) or len(memo) > 240 or any(ord(c) < 32 for c in memo):
            raise ValidationError("memo must be at most 240 characters without control characters")
        if type(ttl) is not int or not 60 <= ttl <= 604800:
            raise ValidationError("expires_in_seconds must be 60–604800")
        fingerprint = hashlib.sha256(json.dumps([amount, memo, ttl]).encode()).hexdigest()
        with self.lock, self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM invoices WHERE idempotency_key=?", (key,)).fetchone()
            if old:
                if old["request_hash"] != fingerprint:
                    raise ConflictError("Idempotency-Key already used with different input")
                return self._view(db, old), False
            invoice_id = uuid.uuid4().hex
            # A crash after address allocation may leave an unused address, never reuse it.
            try:
                address = self.wallet.new_address("wam-pay:" + invoice_id)
            except Exception as exc:
                self.sync_error = "node_unavailable"
                raise NodeUnavailable("Cannot allocate a verified wallet address") from exc
            now = int(self.clock())
            db.execute("""INSERT INTO invoices
                (id,idempotency_key,request_hash,address,amount_units,memo,created_at,
                 expires_at,required_confirmations) VALUES (?,?,?,?,?,?,?,?,?)""",
                       (invoice_id, key, fingerprint, address, amount, memo, now,
                        now + ttl, self.cfg.min_confirmations))
            self.store.event(db, invoice_id, now, "created", {"amount": format_amount(amount)})
            row = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            return self._view(db, row), True

    def sync(self):
        with self.lock:
            try:
                with self.store.connect() as db:
                    invoices = db.execute("SELECT * FROM invoices").fetchall()
                    txids = {r[0] for r in db.execute("SELECT DISTINCT txid FROM payments")}
                tip, outputs = self.wallet.snapshot(invoices, txids)
                now = int(self.clock())
                with self.store.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("UPDATE payments SET active=0, confirmations=-1")
                    for p in outputs:
                        old = db.execute("SELECT * FROM payments WHERE txid=? AND vout=?",
                                         (p["txid"], p["vout"])).fetchone()
                        if old and (old["invoice_id"] != p["invoice_id"] or old["amount_units"] != p["amount_units"]):
                            raise NodeUnavailable("Transaction output changed identity")
                        db.execute("""INSERT INTO payments
                            (txid,vout,invoice_id,amount_units,confirmations,active,first_seen_at)
                            VALUES (?,?,?,?,?,1,?) ON CONFLICT(txid,vout) DO UPDATE SET
                            confirmations=excluded.confirmations, active=1""",
                                   (p["txid"], p["vout"], p["invoice_id"], p["amount_units"], p["confirmations"], now))
                        if old is None:
                            self.store.event(db, p["invoice_id"], now, "payment_seen",
                                             {"txid": p["txid"], "vout": p["vout"], "amount": format_amount(p["amount_units"])})
                    for inv in invoices:
                        payments = db.execute("SELECT * FROM payments WHERE invoice_id=?", (inv["id"],)).fetchall()
                        state, total, confirmed = derive_state(inv["amount_units"], inv["expires_at"],
                                                              inv["required_confirmations"], payments, now)
                        review = inv["needs_review"] or (
                            inv["status"] in ("paid", "late_paid") and confirmed < inv["amount_units"])
                        if (state, total, confirmed, int(review)) != (
                                inv["status"], inv["received_units"], inv["confirmed_units"], inv["needs_review"]):
                            self.store.event(db, inv["id"], now, "reconciled", {
                                "from": inv["status"], "to": state, "received": format_amount(total),
                                "confirmed": format_amount(confirmed), "needs_review": bool(review), "tip": tip})
                        db.execute("""UPDATE invoices SET status=?,received_units=?,confirmed_units=?,
                            needs_review=?,checked_at=?,checked_tip=? WHERE id=?""",
                                   (state, total, confirmed, int(review), now, tip, inv["id"]))
                self.last_sync, self.sync_error = now, None
                return True
            except Exception as exc:
                self.sync_error = "reconciliation_failed"
                # No RPC error bodies, wallet credentials, addresses or customer memos in logs.
                LOG.warning("Reconciliation failed (%s); invoice snapshot was preserved", type(exc).__name__)
                return False

    def health(self):
        with self.lock:
            now = int(self.clock())
            fresh = self.last_sync is not None and 0 <= now - self.last_sync <= self.cfg.stale_seconds
            return {"mode": self.cfg.mode, "ready": bool(fresh and not self.sync_error),
                    "last_sync_at": self.last_sync, "error": self.sync_error,
                    "required_confirmations": self.cfg.min_confirmations,
                    "poll_seconds": self.cfg.poll_seconds}

    def _view(self, db, inv, detail=False):
        now = int(self.clock())
        fresh = bool(self.health()["ready"] and inv["checked_at"] is not None and
                     0 <= now - inv["checked_at"] <= self.cfg.stale_seconds)
        status = inv["status"]
        # Expiry is wall-clock policy, independent of node availability.
        if now >= inv["expires_at"]:
            status = {"pending": "expired", "partially_paid": "partial_expired"}.get(status, status)
        result = {"id": inv["id"], "mode": self.cfg.mode, "address": inv["address"],
                  "amount": format_amount(inv["amount_units"]), "memo": inv["memo"],
                  "status": status, "received": format_amount(inv["received_units"]),
                  "confirmed": format_amount(inv["confirmed_units"]),
                  "remaining": format_amount(max(0, inv["amount_units"] - inv["received_units"])),
                  "overpaid": format_amount(max(0, inv["confirmed_units"] - inv["amount_units"])),
                  "required_confirmations": inv["required_confirmations"],
                  "created_at": inv["created_at"], "expires_at": inv["expires_at"],
                  "checked_at": inv["checked_at"], "checked_tip": inv["checked_tip"],
                  "fresh": fresh, "needs_review": bool(inv["needs_review"]),
                  "eligible_for_fulfillment": bool(self.cfg.mode == "rpc" and fresh and
                                                   status == "paid" and not inv["needs_review"])}
        if detail:
            result["payments"] = [{"txid": p["txid"], "vout": p["vout"],
                "amount": format_amount(p["amount_units"]), "confirmations": p["confirmations"],
                "active": bool(p["active"]), "first_seen_at": p["first_seen_at"]}
                for p in db.execute("SELECT * FROM payments WHERE invoice_id=? ORDER BY first_seen_at,txid,vout", (inv["id"],))]
            result["events"] = [{"id": e["id"], "at": e["at"], "kind": e["kind"],
                "detail": json.loads(e["detail"])} for e in db.execute(
                    "SELECT * FROM events WHERE invoice_id=? ORDER BY id DESC LIMIT 100", (inv["id"],))]
        return result

    def get(self, invoice_id):
        with self.lock, self.store.connect() as db:
            row = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            return self._view(db, row, detail=True) if row else None

    def list(self, limit=50, offset=0):
        with self.lock, self.store.connect() as db:
            rows = db.execute("SELECT * FROM invoices ORDER BY created_at DESC,rowid DESC LIMIT ? OFFSET ?", (limit, offset))
            return [self._view(db, row) for row in rows]

    def demo_payment(self, invoice_id, body):
        if self.cfg.mode != "demo":
            raise ValidationError("Demo actions are disabled in RPC mode")
        if not isinstance(body, dict) or set(body) - {"amount", "confirmations", "txid"}:
            raise ValidationError("Invalid demo fields")
        conf = body.get("confirmations", 0)
        if type(conf) is not int or not -1 <= conf <= 1000:
            raise ValidationError("confirmations must be -1–1000")
        with self.lock:
            if not self.get(invoice_id):
                raise ValidationError("Unknown invoice")
            if "txid" in body:
                if "amount" in body or not isinstance(body["txid"], str):
                    raise ValidationError("Changing a demo transaction accepts txid and confirmations only")
                txid = body["txid"]
                self.wallet.change(invoice_id, txid, conf)
            else:
                if conf < 0:
                    raise ValidationError("New payments cannot have negative confirmations")
                txid = self.wallet.receive(invoice_id, parse_amount(body.get("amount")), conf)
            if not self.sync():
                raise NodeUnavailable("Demo reconciliation failed")
            return {"txid": txid, "invoice": self.get(invoice_id)}

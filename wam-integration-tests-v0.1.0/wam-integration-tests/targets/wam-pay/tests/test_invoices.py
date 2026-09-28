from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch

from src.errors import ConflictError, NodeUnavailable, ValidationError
from src.invoices.service import InvoiceService
from src.invoices.store import Store
from src.wallet.demo import DemoWallet
from tests.helpers import ServiceCase


class InvoiceTests(ServiceCase):
    def test_idempotency_replay_and_conflict(self):
        inv = self.invoice()
        self.assertEqual(self.invoice()["id"], inv["id"])
        with self.assertRaises(ConflictError): self.invoice(amount="11")
        self.assertEqual(len(self.service.list()), 1)

    def test_concurrent_retries_create_one_invoice(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(lambda _: self.invoice()["id"], range(12)))
        self.assertEqual(len(set(ids)), 1)

    def test_unique_addresses(self):
        a, b = self.invoice(), self.invoice(key="order-0002")
        self.assertNotEqual(a["address"], b["address"])

    def test_creation_rpc_failure_leaves_no_invoice(self):
        with patch.object(self.wallet, "new_address", side_effect=NodeUnavailable("offline")):
            with self.assertRaises(NodeUnavailable): self.invoice()
        self.assertEqual(self.service.list(), [])

    def test_partial_multiple_and_overpayment(self):
        inv = self.invoice()
        self.assertEqual(self.pay(inv, "3")["invoice"]["status"], "partially_paid")
        result = self.pay(inv, "8")["invoice"]
        self.assertEqual(result["status"], "paid")
        self.assertEqual(result["confirmed"], "11.00000000")
        self.assertEqual(result["overpaid"], "1.00000000")
        self.assertFalse(result["eligible_for_fulfillment"])  # demo cannot authorize real fulfillment

    def test_zero_confirmation_never_paid(self):
        inv = self.invoice()
        result = self.pay(inv, confirmations=0)
        self.assertEqual(result["invoice"]["status"], "confirming")
        self.assertEqual(result["invoice"]["confirmed"], "0.00000000")
        result = self.service.demo_payment(inv["id"], {"txid": result["txid"], "confirmations": 6})
        self.assertEqual(result["invoice"]["status"], "paid")

    def test_repeated_sync_does_not_double_count_or_duplicate_events(self):
        inv = self.invoice()
        self.pay(inv)
        before = self.service.get(inv["id"])
        for _ in range(3): self.assertTrue(self.service.sync())
        after = self.service.get(inv["id"])
        self.assertEqual(after["confirmed"], "10.00000000")
        self.assertEqual(len(after["events"]), len(before["events"]))
        self.assertEqual(len(after["payments"]), 1)

    def test_reorg_downgrades_and_keeps_review_sticky(self):
        inv = self.invoice()
        paid = self.pay(inv)
        result = self.service.demo_payment(inv["id"], {"txid": paid["txid"], "confirmations": 1})["invoice"]
        self.assertEqual(result["status"], "confirming")
        self.assertTrue(result["needs_review"])
        result = self.service.demo_payment(inv["id"], {"txid": paid["txid"], "confirmations": 6})["invoice"]
        self.assertEqual(result["status"], "paid")
        self.assertTrue(result["needs_review"])

    def test_evicted_payment_disappears_from_totals_but_audit_remains(self):
        inv = self.invoice()
        paid = self.pay(inv, confirmations=0)
        result = self.service.demo_payment(inv["id"], {"txid": paid["txid"], "confirmations": -1})["invoice"]
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["received"], "0.00000000")
        self.assertFalse(result["payments"][0]["active"])

    def test_expiry_and_late_payment(self):
        inv = self.invoice(ttl=60)
        self.now += 60
        self.assertEqual(self.service.get(inv["id"])["status"], "expired")
        self.assertEqual(self.pay(inv)["invoice"]["status"], "late_paid")

    def test_seen_before_deadline_confirmed_after_deadline_is_paid(self):
        inv = self.invoice(ttl=60)
        payment = self.pay(inv, confirmations=0)
        self.now += 61
        result = self.service.demo_payment(inv["id"], {"txid": payment["txid"], "confirmations": 6})["invoice"]
        self.assertEqual(result["status"], "paid")

    def test_partial_late_topup_needs_manual_review(self):
        inv = self.invoice(ttl=60)
        self.pay(inv, "1")
        self.now += 60
        self.assertTrue(self.service.sync())
        self.assertEqual(self.service.get(inv["id"])["status"], "partial_expired")
        self.assertEqual(self.pay(inv, "9")["invoice"]["status"], "late_paid")

    def test_disconnection_preserves_last_snapshot_but_marks_stale(self):
        inv = self.invoice()
        self.pay(inv)
        with patch.object(self.wallet, "snapshot", side_effect=NodeUnavailable("offline")):
            self.assertFalse(self.service.sync())
        result = self.service.get(inv["id"])
        self.assertEqual(result["status"], "paid")
        self.assertFalse(result["fresh"])
        self.assertFalse(result["eligible_for_fulfillment"])

    def test_snapshot_transaction_rolls_back_on_mid_write_failure(self):
        inv = self.invoice()
        self.pay(inv)
        original = self.wallet.snapshot([], set())[1][0]
        broken = dict(original, amount_units=99)
        with patch.object(self.wallet, "snapshot", return_value=("f" * 64, [broken])):
            self.assertFalse(self.service.sync())
        self.assertEqual(self.service.get(inv["id"])["confirmed"], "10.00000000")
        self.assertTrue(self.service.get(inv["id"])["payments"][0]["active"])

    def test_stale_clock_and_restart_require_fresh_sync(self):
        inv = self.invoice()
        self.pay(inv)
        self.now += self.cfg.stale_seconds + 1
        self.assertFalse(self.service.get(inv["id"])["fresh"])
        restarted = InvoiceService(self.store, DemoWallet(), self.cfg, clock=lambda: self.now)
        self.assertFalse(restarted.get(inv["id"])["fresh"])
        self.assertTrue(restarted.sync())
        self.assertEqual(restarted.get(inv["id"])["confirmed"], "10.00000000")

    def test_confirmation_policy_is_pinned_per_invoice(self):
        inv = self.invoice()
        self.service.cfg = replace(self.cfg, min_confirmations=1)
        self.assertEqual(self.pay(inv, confirmations=1)["invoice"]["status"], "confirming")

    def test_database_binding_prevents_network_or_mode_mix(self):
        with self.assertRaises(ConflictError): Store(self.cfg.database, {"mode": "rpc"})

    def test_reject_invalid_fields_and_idempotency_key(self):
        for body, key in [({"amount":"1", "address":"attacker"}, "order-123"),
                          ({"amount":"1"}, "tiny"), ({"amount":"1", "expires_in_seconds":True}, "order-123"),
                          ({"amount":"1", "memo":"x\n"}, "order-123")]:
            with self.subTest(body=body), self.assertRaises(ValidationError): self.service.create(body, key)

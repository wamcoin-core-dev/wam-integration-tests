import unittest
from decimal import Decimal

from src.config import Config
from src.errors import NodeUnavailable, ValidationError
from src.rpc.client import RPCError
from src.wallet.gateway import WalletGateway
from tests.helpers import ADDRESS, NOW, TXID, FakeRPC


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.rpc = FakeRPC()
        self.gateway = WalletGateway(self.rpc, Config(), clock=lambda: NOW)
        self.invoices = [{"address": ADDRESS, "id": "invoice1"}]

    def scan(self):
        return self.gateway.snapshot(self.invoices, set())[1]

    def test_network_sync_peers_wallet_and_stale_tip_gates(self):
        cases = [("chain","test"),("genesis","0" * 64),("initial",True), ("peers",0),
                 ("tip_time",NOW-4000),("wallet_tip","e"*64),("scanning",{}),("owned",False)]
        for key, value in cases:
            with self.subTest(key=key):
                rpc = FakeRPC(); setattr(rpc, key, value)
                with self.assertRaises(NodeUnavailable):
                    WalletGateway(rpc, Config(), clock=lambda: NOW).snapshot(self.invoices, set())

    def test_duplicate_txids_and_vouts_are_counted_once(self):
        self.rpc.txids = [TXID, TXID]
        self.rpc.details.append(dict(self.rpc.details[0]))
        self.assertEqual(len(self.scan()), 1)
        self.assertEqual([m for m,p in self.rpc.calls].count("gettransaction"), 1)

    def test_multiple_outputs_in_same_transaction(self):
        self.rpc.details.append(dict(self.rpc.details[0], amount=Decimal("0.00000001"), vout=1))
        self.assertEqual(sum(p["amount_units"] for p in self.scan()), 1_000_000_001)

    def test_spent_receipts_do_not_depend_on_unspent_balance(self):
        result = self.scan()
        self.assertEqual(result[0]["amount_units"], 1_000_000_000)
        self.assertNotIn("listunspent", [method for method,params in self.rpc.calls])

    def test_unconfirmed_must_be_in_mempool(self):
        self.rpc.conf = 0
        self.assertEqual(len(self.scan()), 1)
        self.rpc.mempool = False
        self.assertEqual(self.scan(), [])

    def test_mempool_errors_other_than_missing_abort_snapshot(self):
        original = self.rpc.call
        def call(method, params=None):
            if method == "getmempoolentry": raise RPCError(-28)
            return original(method, params)
        self.rpc.call = call; self.rpc.conf = 0
        with self.assertRaises(RPCError): self.scan()

    def test_conflicts_and_coinbase_excluded(self):
        self.rpc.conf = -1
        self.assertEqual(self.scan(), [])
        self.rpc.conf = 101; self.rpc.generated = True
        self.assertEqual(self.scan(), [])

    def test_missing_old_txid_is_still_rechecked(self):
        self.rpc.txids = []
        self.rpc.conf = -1
        self.assertEqual(self.gateway.snapshot(self.invoices, {TXID})[1], [])
        self.assertIn(("gettransaction", [TXID, True]), self.rpc.calls)

    def test_wrong_output_identity_and_precision_abort(self):
        self.rpc.details.append(dict(self.rpc.details[0], amount=Decimal("20")))
        with self.assertRaises(NodeUnavailable): self.scan()
        self.rpc.details = [dict(self.rpc.details[0], amount=Decimal("0.000000001"))]
        with self.assertRaises(ValidationError): self.scan()

    def test_chain_tip_change_aborts_snapshot(self):
        self.rpc.change_tip = True
        with self.assertRaises(NodeUnavailable): self.scan()

    def test_new_address_checks_network_and_ownership(self):
        self.assertEqual(self.gateway.new_address("invoice"), ADDRESS)
        self.assertIn(("getnewaddress", ["invoice", "bech32"]), self.rpc.calls)

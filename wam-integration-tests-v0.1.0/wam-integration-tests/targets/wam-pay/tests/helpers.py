import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from src.config import Config
from src.invoices.service import InvoiceService
from src.invoices.store import Store
from src.rpc.client import RPCError
from src.wallet.demo import DemoWallet

NOW = 1_800_000_000
TIP = "a" * 64
TXID = "b" * 64
ADDRESS = "wam1qfixtureaddressnotforpayments"


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = NOW
        self.cfg = replace(Config(), database=str(Path(self.tmp.name) / "test.sqlite3"), api_token="t" * 48)
        self.store = Store(self.cfg.database, {"mode": "demo"})
        self.wallet = DemoWallet()
        self.service = InvoiceService(self.store, self.wallet, self.cfg, clock=lambda: self.now)
        self.assertTrue(self.service.sync())

    def invoice(self, amount="10", ttl=1800, key="order-0001", memo=""):
        return self.service.create({"amount": amount, "memo": memo, "expires_in_seconds": ttl}, key)[0]

    def pay(self, invoice, amount="10", confirmations=6):
        return self.service.demo_payment(invoice["id"], {"amount": amount, "confirmations": confirmations})


class FakeRPC:
    def __init__(self):
        self.calls = []
        self.chain = "main"
        self.genesis = Config().expected_genesis
        self.tip = TIP
        self.initial = False
        self.peers = 3
        self.tip_time = NOW
        self.wallet_tip = TIP
        self.scanning = False
        self.owned = True
        self.txids = [TXID]
        self.mempool = True
        self.conf = 6
        self.generated = False
        self.details = [{"address": ADDRESS, "category": "receive", "amount": Decimal("10.00000000"), "vout": 0}]
        self.tip_calls = 0
        self.change_tip = False

    def call(self, method, params=None):
        self.calls.append((method, params))
        if method == "getblockchaininfo":
            self.tip_calls += 1
            tip = "c" * 64 if self.change_tip and self.tip_calls > 1 else self.tip
            return {"chain": self.chain, "initialblockdownload": self.initial,
                    "blocks": 100, "headers": 100, "bestblockhash": tip}
        if method == "getblockhash": return self.genesis
        if method == "getblockheader": return {"time": self.tip_time}
        if method == "getconnectioncount": return self.peers
        if method == "getwalletinfo":
            return {"walletname": "wam-pay", "scanning": self.scanning,
                    "lastprocessedblock": {"hash": self.wallet_tip}}
        if method == "getaddressinfo": return {"ismine": self.owned, "iswatchonly": False}
        if method == "getnewaddress": return ADDRESS
        if method == "listreceivedbyaddress": return [{"address": ADDRESS, "txids": self.txids}]
        if method == "gettransaction":
            return {"txid": params[0], "confirmations": self.conf, "generated": self.generated,
                    "lastprocessedblock": {"hash": self.tip}, "details": self.details}
        if method == "getmempoolentry":
            if not self.mempool: raise RPCError(-5)
            return {}
        raise AssertionError("Unexpected RPC " + method)

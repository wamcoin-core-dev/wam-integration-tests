"""Shared chain fixture with isolated per-case application wallets/databases."""

from contextlib import contextmanager
from dataclasses import replace
import secrets
import threading

from .node import Node
from .privacy import PrivateWorkspace
from .rpc import GENESIS
from .targets import load_targets


class Context:
    def __init__(self, binary, digest):
        self.binary, self.digest = binary, digest
        self.nodes, self.counter = [], 0

    def __enter__(self):
        self.workspace = PrivateWorkspace()
        self.workspace.__enter__()
        self.path = self.workspace.path
        try:
            self.pay, self.wt = load_targets()
            for i in range(2):
                n = Node(self.binary, self.digest, self.path, i)
                self.nodes.append(n)  # Register BEFORE start so failure cleanup owns it.
                n.start()
            self.a, self.b = self.nodes
            self.funder = self.a.wallet("synthetic-funder")
            self.receiver = self.b.wallet("synthetic-receiver")
            self.mining_address = self.funder.call("getnewaddress", ["", "bech32m"])
            self.a.connect(self.b)
            self.mine(110)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        failed = False
        for node in reversed(self.nodes):
            try: node.stop()
            except Exception: failed = True
        try: self.workspace.__exit__(None, None, None)
        except Exception: failed = True
        if failed:
            from .errors import HarnessError
            raise HarnessError("CLEANUP_FAILED")

    def mine(self, blocks=1):
        hashes = self.funder.call("generatetoaddress", [blocks, self.mining_address])
        self.a.sync_with(self.b)
        return hashes

    def payment(self, address, amount):
        # The only funds used are freshly mined, worthless regtest coins.
        return self.funder.call("sendtoaddress", [address, amount])

    @contextmanager
    def pay_app(self):
        self.counter += 1
        wallet_name = f"synthetic-pay-{self.counter}"
        self.a.wallet(wallet_name)
        cfg = self.pay["Config"](
            mode="rpc", rpc_url=self.a.rpc.url, rpc_cookie_file=str(self.a.cookie_path),
            rpc_wallet=wallet_name, expected_chain="regtest", expected_genesis=GENESIS,
            database=str(self.path / f"pay-{self.counter}.sqlite3"), port=8787,
            api_token=secrets.token_urlsafe(32), min_confirmations=2,
        )
        binding = {"mode":"rpc", "chain":"regtest", "genesis":GENESIS, "wallet":wallet_name}
        store = self.pay["Store"](cfg.database, binding)
        gateway = self.pay["WalletGateway"](self.pay["RPCClient"](cfg), cfg)
        service = self.pay["InvoiceService"](store, gateway, cfg)
        server = self.pay["make_server"](service, cfg, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield cfg, store, service, server.server_port
        finally:
            server.shutdown(); server.server_close(); thread.join(5)

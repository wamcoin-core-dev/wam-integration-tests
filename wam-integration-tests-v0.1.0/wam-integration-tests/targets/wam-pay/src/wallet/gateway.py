import re
import time

from src.errors import NodeUnavailable
from src.invoices.amounts import rpc_units
from src.rpc.client import RPCError

HASH = re.compile(r"[0-9a-f]{64}")


class WalletGateway:
    def __init__(self, rpc, cfg, clock=time.time):
        self.rpc, self.cfg, self.clock = rpc, cfg, clock

    def ready(self):
        cfg = self.cfg
        info = self.rpc.call("getblockchaininfo")
        if info["chain"] != cfg.expected_chain or self.rpc.call("getblockhash", [0]) != cfg.expected_genesis:
            raise NodeUnavailable("Node network/genesis mismatch")
        if (info["initialblockdownload"] is not False or
                type(info["blocks"]) is not int or info["blocks"] != info["headers"]):
            raise NodeUnavailable("Node is not fully synchronized")
        tip = info["bestblockhash"]
        if not isinstance(tip, str) or not HASH.fullmatch(tip):
            raise NodeUnavailable("Invalid node tip")
        header = self.rpc.call("getblockheader", [tip])
        if cfg.expected_chain != "regtest":
            if self.rpc.call("getconnectioncount") < 1:
                raise NodeUnavailable("Node has no peers")
            age = self.clock() - header["time"]
            if not -7200 <= age <= cfg.max_tip_age_seconds:
                raise NodeUnavailable("Node tip is stale or clock is incorrect")
        self.check_wallet(tip)
        return tip

    def check_wallet(self, tip):
        wallet = self.rpc.call("getwalletinfo")
        if wallet["walletname"] != self.cfg.rpc_wallet or wallet.get("scanning") is not False:
            raise NodeUnavailable("Selected wallet is unavailable or rescanning")
        if wallet.get("lastprocessedblock", {}).get("hash") != tip:
            raise NodeUnavailable("Wallet has not processed the current tip")

    def check_address(self, address):
        info = self.rpc.call("getaddressinfo", [address])
        if not (info.get("ismine") is True or info.get("iswatchonly") is True):
            raise NodeUnavailable("Invoice address is not owned/watched by the selected wallet")

    def new_address(self, label):
        self.ready()
        address = self.rpc.call("getnewaddress", [label, "bech32"])
        if not isinstance(address, str) or not re.fullmatch(r"[A-Za-z0-9]{14,100}", address):
            raise NodeUnavailable("Invalid receiving address")
        self.check_address(address)
        return address

    def snapshot(self, invoices, known_txids):
        """Re-read wallet receipts, including already spent outputs and old conflicts."""
        tip = self.ready()
        address_map = {row["address"]: row["id"] for row in invoices}
        for address in address_map:
            self.check_address(address)
        rows = self.rpc.call("listreceivedbyaddress", [0, False, True])
        if not isinstance(rows, list):
            raise NodeUnavailable("Invalid receipt list")
        txids = set(known_txids)
        for row in rows:
            if row.get("address") in address_map:
                txids.update(row["txids"])
        if len(txids) > 20_000:
            raise NodeUnavailable("Snapshot exceeds this MVP's 20000-transaction capacity")
        outputs = {}
        for txid in sorted(txids):
            if not HASH.fullmatch(txid):
                raise NodeUnavailable("Invalid transaction id")
            tx = self.rpc.call("gettransaction", [txid, True])
            if tx["txid"] != txid or tx.get("lastprocessedblock", {}).get("hash") != tip:
                raise NodeUnavailable("Inconsistent wallet transaction snapshot")
            conf = tx["confirmations"]
            if type(conf) is not int:
                raise NodeUnavailable("Invalid confirmation count")
            if tx.get("generated") or conf < 0 or tx.get("abandoned"):
                continue
            if conf == 0:
                try:
                    self.rpc.call("getmempoolentry", [txid])
                except RPCError as exc:
                    if exc.code == -5:  # Transaction is not in this node's mempool.
                        continue
                    raise
            for output in tx["details"]:
                address = output.get("address")
                if (output.get("category") != "receive" or address not in address_map
                        or output.get("abandoned")):
                    continue
                vout = output["vout"]
                if type(vout) is not int or not 0 <= vout < 2**32:
                    raise NodeUnavailable("Invalid transaction output index")
                item = {"txid": txid, "vout": vout, "invoice_id": address_map[address],
                        "amount_units": rpc_units(output["amount"]), "confirmations": conf}
                key = (txid, vout)
                if key in outputs and outputs[key] != item:
                    raise NodeUnavailable("Inconsistent duplicate transaction output")
                outputs[key] = item
        if self.ready() != tip:
            raise NodeUnavailable("Chain tip changed during scan; retry next poll")
        return tip, list(outputs.values())

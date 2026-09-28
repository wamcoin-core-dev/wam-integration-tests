import json
import urllib.error
from unittest.mock import patch

from wam_it.cases import case, require
from wam_it.testing import CANARY, fake_rpc, reply


def audit(c, wallet):
    wt = c.wt
    cfg = wt.RPCConfig(url=c.a.rpc.url, cookie_file=str(c.a.cookie_path))
    privacy = wt.PrivacyConfig(node_config_file=str(c.a.conf), wallet=wallet, show_addresses=False)
    return wt.assess_privacy(wt.RPCClient(cfg), cfg, privacy)


@case("regtest", "WT-001", "Watchtower reads a real wallet and masks reused receiving addresses")
def address_masking(c):
    wallet = c.a.wallet("synthetic-watchtower")
    addr = wallet.call("getnewaddress", ["", "bech32m"])
    txids = [c.payment(addr, 0.1), c.payment(addr, 0.2)]
    c.mine(1)
    report = audit(c, "synthetic-watchtower")
    data = json.dumps(report)
    require(addr not in data and all(txid not in data for txid in txids))
    require("synthetic-watchtower" not in data)
    rows = report["wallet"]["wallets"]
    require(len(rows) == 1 and rows[0]["reused_receiving_addresses"] == 1)


@case("regtest", "WT-002", "Audit makes only the declared read-only RPC calls")
def read_only(c):
    wt = c.wt
    cfg = wt.RPCConfig(url=c.a.rpc.url, cookie_file=str(c.a.cookie_path))
    calls = []
    class Recorder:
        def __init__(self, inner): self.inner = inner
        def call(self, method, *params):
            calls.append(method)
            return self.inner.call(method, *params)
        def for_wallet(self, name): return Recorder(self.inner.for_wallet(name))
    privacy = wt.PrivacyConfig(node_config_file=str(c.a.conf), wallet="synthetic-watchtower")
    wt.assess_privacy(Recorder(wt.RPCClient(cfg)), cfg, privacy)
    require(set(calls) <= {"getnetworkinfo", "getpeerinfo", "listwallets", "getwalletinfo", "listreceivedbyaddress"})
    require("listreceivedbyaddress" in calls)


@case("regtest", "WT-003", "Default pseudonyms cannot link the same receiving address across independent reports")
def unlinkable_reports(c):
    # Strict privacy criterion, intentionally fails on the supplied v0.3 snapshot.
    first = audit(c, "synthetic-watchtower")
    second = audit(c, "synthetic-watchtower")
    a = first["wallet"]["wallets"][0]["examples"][0]["address"]
    b = second["wallet"]["wallets"][0]["examples"][0]["address"]
    require(a != b)


@case("regtest", "WT-004", "Remote error text cannot be embedded in a shareable Watchtower report")
def report_error_leak(c):
    wt = c.wt
    cfg = wt.RPCConfig(url=c.a.rpc.url, cookie_file=str(c.a.cookie_path))
    real = wt.RPCClient(cfg)
    class Fault:
        def call(self, method, *params):
            if method == "listwallets": raise wt.WatchtowerError(CANARY)
            return real.call(method, *params)
    privacy = wt.PrivacyConfig(node_config_file=str(c.a.conf))
    result = wt.assess_privacy(Fault(), cfg, privacy)
    require(CANARY not in json.dumps(result))


@case("regtest", "WT-005", "Watchtower transport rejects redirects before contacting the target")
def redirect_boundary(c):
    destination_hits = []
    def destination(q): destination_hits.append(q); return reply(q, {})
    with fake_rpc(destination) as (target, _, _):
        for status in (301, 302, 303, 307, 308):
            def redirect(q): return status, b"", {"Location":target.url}
            with fake_rpc(redirect) as (source, _, cookie):
                cfg = c.wt.RPCConfig(url=source.url, cookie_file=str(cookie))
                try: c.wt.RPCClient(cfg).call("getnetworkinfo")
                except c.wt.WatchtowerError: pass
    require(not destination_hits)


@case("regtest", "WT-006", "Watchtower does not report Tor anonymity merely because RPC is local")
def no_false_tor_claim(c):
    report = audit(c, "synthetic-watchtower")
    findings = {f["check"]:f["severity"] for f in report["findings"]}
    require(findings["rpc_endpoint"] == "PASS")
    require(findings["tor_proxy"] != "PASS")

from decimal import Decimal
import http.client
import json
import os

from wam_it.cases import case, require
from wam_it.node import wait_until
from wam_it.rpc import GENESIS


@case("regtest", "CORE-001", "Both owned nodes are on the pinned WAM regtest chain")
def chain_identity(c):
    for n in c.nodes:
        require(n.rpc.call("getblockchaininfo")["chain"] == "regtest")
        require(n.rpc.call("getblockhash", [0]) == GENESIS)


@case("regtest", "CORE-002", "Cookie-authenticated RPC refuses an unauthenticated request")
def rpc_auth(c):
    conn = http.client.HTTPConnection("127.0.0.1", c.a.rpc_port, timeout=5)
    try:
        conn.request("POST", "/", json.dumps({"jsonrpc":"2.0", "id":1,
                                             "method":"getblockcount", "params":[]}))
        resp = conn.getresponse(); require(resp.status == 401); resp.read()
    finally: conn.close()


@case("regtest", "CORE-003", "All observed peers are local and no public node address is advertised")
def private_network(c):
    for n in c.nodes:
        peers = n.rpc.call("getpeerinfo")
        require(len(peers) >= 1)
        require(all(p["addr"].startswith("127.0.0.1:") for p in peers))
        require(n.rpc.call("getnetworkinfo")["localaddresses"] == [])


@case("regtest", "CORE-004", "Fresh descriptor wallet produces distinct valid Taproot addresses")
def taproot_addresses(c):
    wallet = c.a.wallet("synthetic-taproot")
    addresses = [wallet.call("getnewaddress", ["", "bech32m"]) for _ in range(24)]
    require(len(set(addresses)) == len(addresses))
    for a in addresses:
        info = wallet.call("getaddressinfo", [a])
        require(a.startswith("wamrt1p") and info["witness_version"] == 1 and info["ismine"])
    require(wallet.call("getwalletinfo")["descriptors"] is True)


@case("regtest", "CORE-005", "Payment reaches the second node mempool and receives confirmations")
def transfer(c):
    address = c.receiver.call("getnewaddress", ["", "bech32m"])
    txid = c.payment(address, 1.125)
    wait_until(lambda: txid in c.b.rpc.call("getrawmempool"))
    require(c.receiver.call("gettransaction", [txid])["confirmations"] == 0)
    c.mine(2)
    tx = c.receiver.call("gettransaction", [txid])
    require(tx["confirmations"] == 2 and tx["amount"] == Decimal("1.125"))


@case("regtest", "CORE-006", "Cookie rotates across node restart and the wallet preserves its receipt")
def restart(c):
    address = c.receiver.call("getnewaddress", ["", "bech32m"])
    txid = c.payment(address, 0.75); c.mine(1)
    old = c.b.cookie_path.read_bytes()
    c.b.stop(); c.b.start()
    if "synthetic-receiver" not in c.b.rpc.call("listwallets"):
        c.b.rpc.call("loadwallet", ["synthetic-receiver"])
    require(c.b.cookie_path.read_bytes() != old)
    c.a.connect(c.b); c.a.sync_with(c.b)
    tx = c.receiver.call("gettransaction", [txid])
    require(tx["amount"] == Decimal("0.75") and tx["confirmations"] >= 1)


@case("regtest", "CORE-007", "Mined coinbase pays the consensus treasury amount using exact decimals")
def treasury(c):
    block_hash = c.mine(1)[0]
    audit = c.a.rpc.call("getdevfeeinfo", [block_hash])
    require(audit["block"]["compliant"] is True)
    block = c.a.rpc.call("getblock", [block_hash, 2])
    outs = block["tx"][0]["vout"]
    treasury = sum((o["value"] for o in outs if o["scriptPubKey"]["hex"] == audit["script"]), Decimal(0))
    require(treasury == Decimal("2.5"))  # below regtest's first halving


@case("regtest", "CORE-008", "Private datadir and cookie have owner-only POSIX permissions")
def filesystem_permissions(c):
    if os.name == "nt":
        # The Windows ACL claim is explicitly NOT covered by this POSIX test.
        import unittest
        raise unittest.SkipTest("POSIX only")
    for node in c.nodes:
        require(node.path.stat().st_mode & 0o077 == 0)
        require(node.cookie_path.stat().st_mode & 0o077 == 0)


@case("regtest", "CORE-009", "Supply reporting remains under the WAM cap")
def supply(c):
    supply = c.a.rpc.call("getsupplyinfo")
    require(Decimal(str(supply["circulating"])) <= Decimal("22000000"))
    require(Decimal(str(supply["premine"])) == Decimal("2000000"))


@case("regtest", "CORE-010", "Two isolated branches converge to the longer valid branch")
def partition_reorg(c):
    c.b.rpc.call("setnetworkactive", [False])
    ancestor = c.a.rpc.call("getbestblockhash")
    try:
        short = c.funder.call("generatetoaddress", [1, c.mining_address])[-1]
        address = c.receiver.call("getnewaddress", ["", "bech32m"])
        long = c.receiver.call("generatetoaddress", [3, address])[-1]
        require(short != long and ancestor != short)
    finally:
        c.b.rpc.call("setnetworkactive", [True])
        c.a.connect(c.b)
        c.a.sync_with(c.b)
    require(c.a.rpc.call("getbestblockhash") == long)
    require(c.a.rpc.call("getblockheader", [short])["confirmations"] == -1)


@case("regtest", "CORE-011", "Immediately restored blocks have RPC header-height compatibility with Pay")
def reconsider_height_contract(c):
    blocks = c.mine(2)
    try:
        c.a.rpc.call("invalidateblock", [blocks[0]])
        c.a.rpc.call("reconsiderblock", [blocks[0]])
        c.a.sync_with(c.b)
        info = c.a.rpc.call("getblockchaininfo")
        require(info["blocks"] == info["headers"])
    finally:
        # Preserve the observation as a FAILURE, then restore shared fixture health.
        c.a.rpc.call("reconsiderblock", [blocks[0]])
        c.mine(1)

import base64
import json
import os
import time
from unittest.mock import patch

from wam_it.cases import case, require
from wam_it.errors import HarnessError, RPCError
from wam_it.rpc import GENESIS, Cookie, RPC, endpoint
from wam_it.testing import CANARY, fake_rpc, reply


def expect(code, fn):
    try:
        fn()
    except HarnessError as exc:
        require(exc.code == code)
        require(CANARY not in str(exc))
        return
    raise AssertionError("expected safe rejection")


@case("selftest", "RPC-001", "Reject remote hosts, credentials, alternate IP encodings and URL injection")
def endpoint_rejections(_):
    for host in ("localhost", "example.com", "0.0.0.0", "::1", "127.1", "2130706433",
                 "0177.0.0.1", "127.0.0.1.evil", "192.0.2.1", "[::ffff:127.0.0.1]"):
        expect("INVALID_ENDPOINT", lambda: endpoint(f"http://{host}:1234"))
    for u in ("https://127.0.0.1:1234", "http://u:p@127.0.0.1:1234",
              "http://127.0.0.1:0", "http://127.0.0.1:65536", "http://127.0.0.1:1234/x",
              "http://127.0.0.1:1234?x", "http://127.0.0.1:1234#x", " http://127.0.0.1:1234",
              "http://127.0.0.1:01234", "http://127.0.0.1:1234\n"):
        expect("INVALID_ENDPOINT", lambda: endpoint(u))
    require(endpoint("http://127.0.0.1:1234/") == 1234)


@case("selftest", "RPC-002", "Ignore ambient HTTP proxy configuration")
def ignores_proxy(_):
    with fake_rpc(lambda q: reply(q, 7)) as (rpc, _, _cookie):
        with patch.dict(os.environ, {"HTTP_PROXY": "http://192.0.2.1:1",
                                    "http_proxy": "http://192.0.2.1:1", "NO_PROXY": ""}):
            require(rpc.call("getblockcount") == 7)


@case("selftest", "RPC-003", "Reject HTTP redirects without a second request")
def no_redirects(_):
    with fake_rpc(lambda q: (302, b"", {"Location": "http://127.0.0.1:1/"})) as (rpc, calls, _cookie):
        expect("RPC_HTTP", lambda: rpc.call("getblockcount"))
        require(len(calls) == 1)


@case("selftest", "RPC-004", "Remote error messages never enter exception text")
def hides_errors(_):
    def respond(q):
        return 500, {"jsonrpc": "2.0", "id": q["id"], "error": {"code": -5, "message": CANARY}}, {}
    with fake_rpc(respond) as (rpc, _, _cookie):
        try:
            rpc.call("getblockcount")
        except RPCError as exc:
            require(exc.rpc_code == -5 and str(exc) == "RPC_REMOTE")
        else:
            raise AssertionError


@case("selftest", "RPC-005", "Reject mismatched response IDs")
def bad_id(_):
    with fake_rpc(lambda q: (200, {"jsonrpc": "2.0", "id": "wrong", "result": CANARY}, {})) as (rpc, _, _cookie):
        expect("RPC_ENVELOPE", lambda: rpc.call("getblockcount"))


@case("selftest", "RPC-006", "Reject duplicate JSON keys")
def duplicates(_):
    with fake_rpc(lambda q: (200, ('{"jsonrpc":"2.0","id":"'+q['id']+'","result":1,"result":2}').encode(), {})) as (rpc, _, _cookie):
        expect("RPC_ENVELOPE", lambda: rpc.call("getblockcount"))


@case("selftest", "RPC-007", "Reject NaN and Infinity in RPC responses")
def finite_numbers(_):
    for val in ("NaN", "Infinity", "-Infinity"):
        with fake_rpc(lambda q: (200, ('{"jsonrpc":"2.0","id":"'+q['id']+'","result":'+val+'}').encode(), {})) as (rpc, _, _cookie):
            expect("RPC_ENVELOPE", lambda: rpc.call("getblockcount"))


@case("selftest", "RPC-008", "Bound response bytes")
def oversize(_):
    with fake_rpc(lambda q: reply(q, "x" * 5000), max_response=2048) as (rpc, _, _cookie):
        expect("RPC_OVERSIZE", lambda: rpc.call("getblockcount"))


@case("selftest", "RPC-009", "Malformed and ambiguous RPC envelopes fail closed")
def malformed(_):
    for result in (b"no json " + CANARY.encode(), b"[]", b"null", b'{"error":true}'):
        with fake_rpc(lambda q: (200, result, {})) as (rpc, _, _cookie):
            expect("RPC_ENVELOPE", lambda: rpc.call("getblockcount"))


@case("selftest", "RPC-010", "Rotate cookie authentication without caching old credentials")
def cookie_rotation(_):
    with fake_rpc(lambda q: reply(q, 7)) as (rpc, calls, cookie):
        rpc.call("getblockcount")
        cookie.write_text("__cookie__:replacement-synthetic")
        rpc.call("getblockcount")
        require(calls[0][2] != calls[1][2])
        require(calls[1][2] == "Basic " + base64.b64encode(b"__cookie__:replacement-synthetic").decode())


@case("selftest", "RPC-011", "Percent-encode wallet routing without leaking labels")
def wallet_routing(_):
    with fake_rpc(lambda q: reply(q, {})) as (rpc, calls, _cookie):
        rpc.wallet("synthetic/name ?#").call("getwalletinfo")
        require(calls[0][1] == "/wallet/synthetic%2Fname%20%3F%23")


@case("selftest", "RPC-012", "Private-key export and unlisted methods are denied before transport")
def forbidden_methods(_):
    with fake_rpc(lambda q: reply(q, {})) as (rpc, calls, _cookie):
        for method in ("dumpprivkey", "dumpwallet", "walletpassphrase", "importprivkey", "importdescriptors", "unknown"):
            expect("RPC_METHOD_DENIED", lambda: rpc.call(method))
        require(not calls)


@case("selftest", "RPC-013", "Refuse mutations when the node reports mainnet")
def mainnet_guard(_):
    def respond(q):
        return reply(q, {"chain": "main"} if q["method"] == "getblockchaininfo" else GENESIS)
    with fake_rpc(respond) as (rpc, calls, _cookie):
        expect("CHAIN_MISMATCH", lambda: rpc.call("sendtoaddress", [CANARY, 1]))
        require(all(q[0]["method"] != "sendtoaddress" for q in calls))


@case("selftest", "RPC-014", "Refuse mutations on a regtest chain with the wrong genesis")
def genesis_guard(_):
    def respond(q):
        return reply(q, {"chain": "regtest"} if q["method"] == "getblockchaininfo" else "0" * 64)
    with fake_rpc(respond) as (rpc, calls, _cookie):
        expect("CHAIN_MISMATCH", lambda: rpc.call("invalidateblock", [CANARY]))
        require(all(q[0]["method"] != "invalidateblock" for q in calls))


@case("selftest", "RPC-015", "Re-attest chain identity before each mutating request")
def repeated_guard(_):
    chain = ["regtest"]
    def respond(q):
        return reply(q, {"chain": chain[0]} if q["method"] == "getblockchaininfo" else GENESIS)
    with fake_rpc(respond) as (rpc, calls, _cookie):
        rpc.call("getnewaddress")
        chain[0] = "main"
        expect("CHAIN_MISMATCH", lambda: rpc.call("getnewaddress"))
        require(sum(q[0]["method"] == "getnewaddress" for q in calls) == 1)


@case("selftest", "RPC-016", "Timeout does not retry a mutating RPC")
def no_retry(_):
    def respond(q):
        if q["method"] == "getblockchaininfo": return reply(q, {"chain":"regtest"})
        if q["method"] == "getblockhash": return reply(q, GENESIS)
        time.sleep(0.15)
        return reply(q, CANARY)
    with fake_rpc(respond, timeout=0.05) as (rpc, calls, _cookie):
        expect("RPC_TRANSPORT", lambda: rpc.call("sendtoaddress", [CANARY, 1]))
        require(sum(q[0]["method"] == "sendtoaddress" for q in calls) == 1)


@case("selftest", "RPC-017", "Reject malformed and oversized cookies")
def malformed_cookie(_):
    with fake_rpc(lambda q: reply(q, {})) as (rpc, calls, cookie):
        for value in ("no-colon", "user:one\ntwo", "x:" + "y" * 5000):
            cookie.write_text(value)
            expect("RPC_CREDENTIALS", lambda: rpc.call("getblockcount"))
        require(not calls)


@case("selftest", "RPC-018", "Reject an HTTP error masquerading as a successful RPC")
def http_error_success(_):
    def respond(q):
        status, body, headers = reply(q, True)
        return 500, body, headers
    with fake_rpc(respond) as (rpc, _, _cookie):
        expect("RPC_ENVELOPE", lambda: rpc.call("getblockcount"))

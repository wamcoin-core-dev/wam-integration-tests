from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
import io
import json
import logging

from wam_it.cases import case, require
from wam_it.testing import CANARY, http_request


def headers(cfg, key=None):
    h = {"Authorization": "Bearer " + cfg.api_token, "Content-Type": "application/json"}
    if key: h["Idempotency-Key"] = key
    return h


def invoice(service, amount="1.25", key="synthetic-order-001"):
    inv, created = service.create({"amount":amount, "memo":CANARY}, key)
    require(created)
    return inv


@case("regtest", "PAY-001", "Unauthenticated invoice API reveals no wallet, memo, token or customer data")
def auth(c):
    with c.pay_app() as (cfg, store, service, port):
        inv = invoice(service)
        status, response_headers, body = http_request(port, "/api/invoices")
        require(status == 401)
        for value in (inv["address"], inv["id"], CANARY, cfg.api_token, cfg.rpc_wallet):
            require(value.encode() not in body)
        require(response_headers["Cache-Control"] == "no-store")
        require(response_headers["Referrer-Policy"] == "no-referrer")


@case("regtest", "PAY-002", "Create invoice over HTTP, pay on-chain, and gate fulfillment on confirmations")
def full_payment(c):
    with c.pay_app() as (cfg, store, service, port):
        status, _, body = http_request(port, "/api/invoices", "POST", {"amount":"1.25"}, headers(cfg,"synthetic-order-001"))
        require(status == 201); inv = json.loads(body)
        txid = c.payment(inv["address"], 1.25)
        require(service.sync())
        require(service.get(inv["id"])["eligible_for_fulfillment"] is False)
        c.mine(1); require(service.sync())
        require(service.get(inv["id"])["eligible_for_fulfillment"] is False)
        c.mine(1); require(service.sync())
        status, h, body = http_request(port, "/api/invoices/"+inv["id"], headers=headers(cfg))
        paid = json.loads(body)
        require(status == 200 and paid["status"] == "paid" and paid["eligible_for_fulfillment"])
        require(paid["confirmed"] == "1.25000000")


@case("regtest", "PAY-003", "Different invoices receive different owned addresses and no memo enters wallet labels")
def fresh_addresses(c):
    with c.pay_app() as (cfg, store, service, port):
        invoices = [invoice(service, key=f"synthetic-order-{i:03d}") for i in range(12)]
        require(len({i["address"] for i in invoices}) == 12)
        wallet = c.a.rpc.wallet(cfg.rpc_wallet)
        for inv in invoices:
            info = wallet.call("getaddressinfo", [inv["address"]])
            require(info["ismine"] is True)
            require(CANARY not in json.dumps(info))


@case("regtest", "PAY-004", "Concurrent HTTP retries produce exactly one invoice and address")
def concurrent_idempotency(c):
    with c.pay_app() as (cfg, store, service, port):
        def request(_):
            return http_request(port, "/api/invoices", "POST", {"amount":"2"}, headers(cfg,"synthetic-retry-001"))
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(request, range(6)))
        require(sum(status == 201 for status, _, _ in responses) == 1)
        require(all(status in (200,201) for status, _, _ in responses))
        require(len({json.loads(body)["address"] for _,_,body in responses}) == 1)
        require(len(service.list()) == 1)


@case("regtest", "PAY-005", "Partial payments and overpayment reconcile without double counting")
def partial_and_overpay(c):
    with c.pay_app() as (cfg, store, service, port):
        inv = invoice(service, "2")
        c.payment(inv["address"], 0.5); c.mine(2); require(service.sync())
        require(service.get(inv["id"])["status"] == "partially_paid")
        c.payment(inv["address"], 1.75); c.mine(2); require(service.sync())
        value = service.get(inv["id"])
        require(value["status"] == "paid" and value["confirmed"] == "2.25000000")
        require(value["overpaid"] == "0.25000000")
        require(service.sync())
        require(service.get(inv["id"])["confirmed"] == "2.25000000")


@case("regtest", "PAY-006", "Invalidating a paid block revokes fulfillment and latches manual review")
def reorg(c):
    with c.pay_app() as (cfg, store, service, port):
        inv = invoice(service)
        c.payment(inv["address"], 1.25)
        blocks = c.mine(2); require(service.sync())
        require(service.get(inv["id"])["eligible_for_fulfillment"])
        try:
            c.a.rpc.call("invalidateblock", [blocks[0]])
            require(service.sync())
            changed = service.get(inv["id"])
            require(not changed["eligible_for_fulfillment"] and changed["needs_review"])
            require(Decimal(changed["confirmed"]) == 0)
        finally:
            c.a.rpc.call("reconsiderblock", [blocks[0]])
            c.a.sync_with(c.b)
            # v0.1.11 can leave best-header height stale after reconsiderblock.
            # CORE-011 records that incompatibility before any fixture repair.
            # Mine a fresh block here to restore the fixture for subsequent cases.
            c.mine(1)
        require(service.sync())
        require(service.get(inv["id"])["needs_review"])
        require(not service.get(inv["id"])["eligible_for_fulfillment"])


@case("regtest", "PAY-007", "Node outage preserves prior accounting while disabling fulfillment")
def outage(c):
    with c.pay_app() as (cfg, store, service, port):
        inv = invoice(service); c.payment(inv["address"], 1.25); c.mine(2)
        require(service.sync()); old = service.get(inv["id"])
        c.a.stop()
        try:
            require(service.sync() is False)
            failed = service.get(inv["id"])
            require(failed["confirmed"] == old["confirmed"] and failed["status"] == "paid")
            require(not failed["eligible_for_fulfillment"])
        finally:
            c.a.start()
            for name in ("synthetic-funder", cfg.rpc_wallet):
                if name not in c.a.rpc.call("listwallets"): c.a.rpc.call("loadwallet", [name])
            c.a.connect(c.b); c.a.sync_with(c.b)
        require(service.sync())
        require(service.get(inv["id"])["eligible_for_fulfillment"])


@case("regtest", "PAY-008", "Service restart recovers invoices and requires a fresh sync before fulfillment")
def persistence(c):
    with c.pay_app() as (cfg, store, service, port):
        inv = invoice(service); c.payment(inv["address"], 1.25); c.mine(2); require(service.sync())
        new = c.pay["InvoiceService"](store, service.wallet, cfg)
        require(new.get(inv["id"])["status"] == "paid")
        require(not new.get(inv["id"])["eligible_for_fulfillment"])
        require(new.sync() and new.get(inv["id"])["eligible_for_fulfillment"])


@case("regtest", "PAY-009", "Reject cross-origin and forged Host requests even with a valid API token")
def browser_boundary(c):
    with c.pay_app() as (cfg, store, service, port):
        for extra in ({"Origin":"https://example.invalid"}, {"Host":"example.invalid"}):
            status, _, body = http_request(port, "/api/invoices", headers={**headers(cfg),**extra})
            require(status == 403 and cfg.api_token.encode() not in body)


@case("regtest", "PAY-010", "Client precision violations cannot allocate an invoice")
def exact_precision(c):
    with c.pay_app() as (cfg, store, service, port):
        for amount in ("0.000000001", "NaN", "-1", 1.2):
            status, _, body = http_request(port, "/api/invoices", "POST", {"amount":amount}, headers(cfg,"synthetic-precision"))
            require(status == 400)
        require(service.list() == [])


@case("regtest", "PAY-011", "Secret-bearing upstream errors cannot reach Pay API responses or application logs")
def upstream_error(c):
    with c.pay_app() as (cfg, store, service, port):
        class Broken:
            def new_address(self, _): raise RuntimeError(CANARY)
            def snapshot(self, *_): raise RuntimeError(CANARY)
        service.wallet = Broken()
        text = io.StringIO(); handler = logging.StreamHandler(text)
        logger = logging.getLogger("wam_pay"); logger.addHandler(handler)
        try:
            status, _, body = http_request(port, "/api/invoices", "POST", {"amount":"1"}, headers(cfg,"synthetic-error-001"))
            require(status == 503 and CANARY.encode() not in body)
            require(service.sync() is False)
            require(CANARY not in text.getvalue())
        finally: logger.removeHandler(handler)


@case("regtest", "PAY-012", "Stale reconciliation disables fulfillment using the application's clock")
def stale_state(c):
    with c.pay_app() as (cfg, store, service, port):
        inv = invoice(service); c.payment(inv["address"], 1.25); c.mine(2); require(service.sync())
        service.clock = lambda: service.last_sync + cfg.stale_seconds + 1
        require(not service.get(inv["id"])["eligible_for_fulfillment"])


@case("regtest", "PAY-013", "A single transaction can fund distinct invoice outputs without misattribution")
def multiple_outputs(c):
    with c.pay_app() as (cfg, store, service, port):
        first = invoice(service, "1", "synthetic-multi-001")
        second = invoice(service, "2", "synthetic-multi-002")
        c.funder.call("sendmany", ["", {first["address"]:1, second["address"]:2}])
        c.mine(2); require(service.sync())
        require(service.get(first["id"])["confirmed"] == "1.00000000")
        require(service.get(second["id"])["confirmed"] == "2.00000000")


@case("regtest", "PAY-014", "Pay refuses invoice creation if its independent genesis pin is wrong")
def wrong_chain_pin(c):
    with c.pay_app() as (cfg, store, service, port):
        wrong = replace(cfg, expected_genesis="0" * 64)
        service.wallet = c.pay["WalletGateway"](c.pay["RPCClient"](wrong), wrong)
        status, _, body = http_request(port, "/api/invoices", "POST", {"amount":"1"}, headers(cfg,"synthetic-genesis"))
        require(status == 503 and service.list() == [])

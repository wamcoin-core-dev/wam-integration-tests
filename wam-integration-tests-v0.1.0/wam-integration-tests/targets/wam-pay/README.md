# WAM Pay

**A local merchant desk for WAM invoices and node-backed payment monitoring.**

Community prototype · v0.1.0 · Python 3.11+ · SQLite · zero third-party runtime dependencies

Create an invoice, give the customer its receiving address and exact WAM amount,
then track receipts and confirmations through your own WAM node. The browser
dashboard is in Vietnamese; contributor documentation is in English.

## Try it in one command

From the extracted `wam-pay` directory:

```bash
python3 scripts/demo.py
```

Windows:

```powershell
py -3 scripts/demo.py
```

Open **http://127.0.0.1:8787** and paste the temporary API token printed in the
terminal. Create a `10` WAM invoice, simulate a payment with `0` confirmations,
then click **Đủ xác nhận**. Try **Loại giao dịch** to see the invoice downgrade.
Demo addresses cannot receive real funds. Demo data survives restarts; the API
token changes each time. Nothing needs to be installed with pip or npm.

**Hướng dẫn tiếng Việt:** [Bắt đầu trên Mac/Windows](docs/QUICKSTART_VI.md).

## Included

- One fresh wallet address per invoice; immutable invoice amount and confirmation policy.
- Exact integer accounting to 8 decimal places; decimal strings at the API boundary.
- Idempotent invoice creation, partial payments, multiple receipts and overpayment reporting.
- Reconciliation of historical receipts, including spent outputs; no balance-delta accounting.
- Mempool membership checks, confirmation tracking, expiry and conservative late-payment review.
- Reorg downgrades, persistent review flags and a durable event log.
- Network/genesis checks, wallet synchronization checks, stale-data gating and atomic database updates.
- Authenticated local API, merchant UI, safe SQLite backup and source packaging scripts.
- Offline unit/integration tests and a GitHub Actions matrix for Linux, macOS and Windows.

## Scope of this release

This is a **local, single-merchant MVP**, not a hosted payment service. It has
not been audited or verified against a live WAM node in the build environment.
Six confirmations is an editable application default, not an assurance about
WAM chain finality. Perform the [node acceptance procedure](docs/SETUP.md#acceptance-test)
before using actual payments.

The application contains no sending, signing, automatic refund, key export,
seed import, fiat conversion, webhook or public checkout endpoint. Its RPC
credentials may still grant broader privileges on the node: read
[SECURITY.md](SECURITY.md). A watch-only wallet needs a funded address derivation
range and an external signer; this app does not provision that wallet.

The HTTP server deliberately binds to `127.0.0.1`. Public deployment needs a
separately reviewed server/authentication design. This release does not claim a
WAM URI/QR standard or link customer addresses to external explorers.

## Run with a node

1. Prepare and back up a **dedicated** wallet in your local WAM node.
2. Run `python3 scripts/init_config.py` and edit `config.json` following
   [SETUP.md](docs/SETUP.md). Set `mode` to `rpc`, use a separate database, and
   verify the network/genesis against an independently trusted WAM source.
3. Set `WAM_PAY_API_TOKEN` and configure cookie authentication or
   `WAM_RPC_PASSWORD`.
4. Run `python3 -m src --check`, then `python3 -m src`.

The node wallet must remain loaded. The application never starts/stops the node
or unlocks the wallet. It does not need `txindex` for wallet RPC receipts.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q src scripts
python3 scripts/package_release.py
```

Tests use temporary databases and local fake RPC servers, without external
network access. GitHub Actions is configured but was not executed remotely as
part of this delivery. See [VALIDATION.md](docs/VALIDATION.md) for actual checks.

```text
src/rpc/       authenticated RPC client and method allowlist
src/invoices/  exact amounts, SQLite storage and invoice service
src/payments/  state derivation
src/wallet/    WAM receipt adapter and isolated demo backend
src/api/       local authenticated HTTP routes
src/ui/        vanilla HTML/CSS/JavaScript merchant dashboard
tests/         offline behavior and HTTP integration tests
docs/          setup, API, design and validation notes
scripts/       demo, initialization, backup and release packaging
```

More: [API](docs/API.md) · [Architecture](docs/ARCHITECTURE.md) ·
[RPC compatibility](docs/RPC_COMPATIBILITY.md) · [Contributing](CONTRIBUTING.md).

MIT licensed. This independent community project is not represented as an
official WAM Coin release or endorsement.

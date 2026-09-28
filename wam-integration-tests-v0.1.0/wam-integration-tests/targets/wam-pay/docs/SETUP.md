# Node setup and operations

## Requirements

- Python 3.11+ with SQLite support; run commands from the repository root.
- A local WAM node with the RPCs in [RPC_COMPATIBILITY.md](RPC_COMPATIBILITY.md).
- A loaded, dedicated wallet with unused receiving addresses. Provision and back
  up the wallet using WAM's own tools. No wallet creation/import/unlock is automated.
- A synchronized clock and chain, live peers (except regtest), and wallet
  `lastprocessedblock.hash` matching the node tip.

## Configuration

`python3 scripts/init_config.py` creates `config.json` without overwriting it.
The JSON configuration rejects unknown fields; credentials live in environment
variables. Relative paths resolve beside the configuration file, not the shell's
working directory. Tilde expansion is supported; `$HOME` substitution in JSON is not.

| Field | Default / purpose |
|---|---|
| `mode` | `demo`; change to `rpc` for node receipts |
| `host`, `port` | `127.0.0.1`, `8787`; only loopback binding is supported |
| `database` | `data/demo.sqlite3`; use a different file for live payments |
| `poll_seconds`, `stale_seconds` | 15, 60; stale window must be at least twice poll interval |
| `min_confirmations` | 6; minimum 1, copied into each new invoice |
| `invoice_ttl_seconds` | 1800; invoice request may specify 60–604800 |
| `rpc_url` | `http://127.0.0.1:9554`; no URL credentials or wallet path |
| `rpc_wallet` | `wam-pay`; exact loaded node wallet name |
| `rpc_cookie_file` | Empty; set actual local cookie path for cookie authentication |
| `rpc_user` | Empty; used with `WAM_RPC_PASSWORD` if no cookie path is configured |
| `rpc_timeout_seconds` | 10; per request, not per entire reconciliation |
| `expected_chain` | `main`; supported values: `main`, `test`, `regtest` |
| `expected_genesis` | Published WAM mainnet value; independently verify before using funds |
| `max_tip_age_seconds` | 3600; applied outside regtest |

The database pins mode, chain, genesis and wallet name. A mismatch refuses
startup. It does not uniquely identify a restored wallet sharing the same name;
ownership checks on every invoice address provide an additional check. Keep the
wallet and invoice database paired. Do not edit the `meta` binding to force reuse.

### Authentication

Mac/Linux:

```bash
export WAM_PAY_API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
printf '%s\n' "$WAM_PAY_API_TOKEN"
python3 -m src --check
python3 -m src
```

Windows PowerShell:

```powershell
$env:WAM_PAY_API_TOKEN = py -3 -c "import secrets; print(secrets.token_urlsafe(32))"
Write-Output $env:WAM_PAY_API_TOKEN
py -3 -m src --check
py -3 -m src
```

Prefer a correctly restricted RPC account for deployment. If using a username,
set `rpc_user` in config and `WAM_RPC_PASSWORD` in the process environment using
your normal secret-management method. Cookie auth rereads the cookie for every
call so node restarts/rotation are handled. A configured cookie takes precedence.
Neither secret is served to the browser. Do not put RPC credentials in command
line arguments or commit configuration/data files.

Node RPC must listen only on loopback. This release neither reads nor modifies
`wam.conf`; verify the node's actual RPC bind and authentication configuration.
Cookie authentication may have broad privileges. Where the WAM build supports
Bitcoin Core's `rpcwhitelist`, restrict the application account to the exact
method list in the compatibility document. Verify behavior on the installed build.

### Check the node explicitly

Using the `wam-cli` binary and the **same datadir/network as your running node**:

```bash
wam-cli -datadir=/absolute/node-data getblockchaininfo
wam-cli -datadir=/absolute/node-data getblockhash 0
wam-cli -datadir=/absolute/node-data -rpcwallet=wam-pay getwalletinfo
```

Use the corresponding network flag when needed. Compare genesis with a trusted
WAM release/source independent of this node; do not simply accept an arbitrary
connected node's genesis. The example configuration uses the published mainnet
values, not a claim that the node on your machine has already been checked.

`python3 -m src --check` runs read-only readiness checks and exits. It never
allocates an address, sends funds or modifies a wallet. A successful check
does not test an actual incoming transfer or mining consensus.

## Acceptance test

Start on a maintained WAM test network if available; otherwise use an isolated
regtest environment whose genesis and wallet setup you have independently
verified. This repository does not supply or build `wamd` or a mining harness.

1. Run the readiness check and create an invoice. Verify its address in the node
   wallet and check that repeated requests with the same idempotency key return
   the same invoice/address.
2. Send a small test-network payment from a **separate** wallet using WAM tools.
   Confirm the app shows pending confirmations and later `paid` at its threshold.
3. Test two installments, a late installment and an overpayment. Inspect exact
   amounts and the persisted event log.
4. Stop the app and restart it. Confirm prior receipts remain and freshness is
   false until the first successful reconciliation.
5. Stop node RPC or disconnect it. Confirm `ready=false` and no stale invoice
   is eligible for fulfillment; reconnect and reconcile.
6. On **isolated regtest only**, exercise a conflicting/replaced transaction and
   a reorg with your node tooling. Verify dropped amounts and sticky review flags.
7. Back up and restore the invoice database and its separately backed-up wallet.
   Verify every invoice address is still recognized.

Only after these pass should a maintainer assess a controlled small-value live
trial. Confirmation depth remains a merchant risk policy, not a finality guarantee.
No real coin transfer is performed by this repository's automated tests.

## Backup and restore

```bash
python3 scripts/backup.py data/wam-main.sqlite3 /existing/backup-dir/wam-pay.sqlite3
```

This uses SQLite's online backup API and checks integrity. Existing destination
files are never overwritten. Back up the node wallet separately using WAM tools;
the invoice database cannot recover keys or rederive a wallet.

For restore, stop **all** WAM Pay processes. Preserve the current database plus
its `-wal`/`-shm` files together in a separate recovery directory. Put the verified
backup at a **new** database path, point config to it, and start with the matching
wallet/network. Do not combine an old database with unrelated WAL sidecars. A
restored backup may lack invoices created after the backup; use wallet labels
`wam-pay:<invoice-id>` and your order records for manual recovery. Restore runs
must reconcile before any fulfillment decision. Periodically test recovery.

## Operational limits

One process owns one SQLite database. The application has no automatic delivery,
refund or review-clear action. Resolve reviewed orders outside the app and keep
your business records. Historical invoices remain monitored so later receipts
and deep reorgs remain visible. Each scan rereads all relevant transactions;
20,000 distinct transaction IDs is a hard scan ceiling, not a performance promise.
Large wallets need an indexed, incremental reconciler before production use.

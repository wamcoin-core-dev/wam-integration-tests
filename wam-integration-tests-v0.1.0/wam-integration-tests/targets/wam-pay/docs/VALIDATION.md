# Validation record — v0.1.0

Build date: 2026-09-28. Environment: Linux, Python 3.12.14, Node.js 24.19.0.

| Check | Result |
|---|---|
| `python3 -m unittest discover -s tests -v` | 55 tests passed |
| Python compilation, `src` and `scripts` | Passed |
| `node --check src/ui/app.js` | Passed |
| HTML nesting, unique IDs and JS element references | Passed after correcting a missing closing div |
| CLI `--check` in isolated demo config | Passed |
| Actual app process startup and authenticated HTTP requests | Passed |
| Create invoice, add demo receipt, confirm paid state | Passed |
| SIGTERM process shutdown | Passed |
| Git whitespace/error check | Passed |

The suite covers decimal precision, invalid input, duplicate/idempotent requests,
concurrent creation, multiple outputs, partial and overpayments, confirmation
thresholds, expiry, late receipts, mempool eviction, conflicts, reorg review,
snapshot rollback, outage/stale state, restart persistence, database binding,
RPC authentication/cookie rotation, wallet routing, redirect rejection, API
authentication/Host/Origin checks, backup integrity and process locking.

`tests/test_integration.py` combines the real invoice service and WAM adapter
with synthetic RPC responses. `tests/test_rpc.py` exercises actual HTTP transport
against a local fake JSON-RPC server. Neither is a live-node or consensus test.

## Not validated here

- No live WAM node, wallet, testnet transfer or mainnet transfer was used.
- No real WAM reorg/mining harness was run; these behaviors use synthetic fixtures.
- macOS/Windows execution has not been run locally. The CI matrix is supplied,
  but GitHub Actions has not been triggered or claimed as passing.
- No automated browser render or visual screenshot review was completed: the
  environment has Playwright's library but no Chromium executable. HTML/JS checks
  and HTTP UI asset delivery passed; interactive browser behavior needs review.
- No independent security audit, public deployment, load test or throughput claim.

Before a real payment trial, complete the node acceptance procedure in
[SETUP.md](SETUP.md#acceptance-test) and review the UI on the target browser.

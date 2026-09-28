# Changelog

## 0.1.0 — 2026-09-28

- Two disposable, checksum-pinned WAM v0.1.11 regtest nodes with fresh wallets,
  local P2P, cookie-authenticated RPC and owned-process cleanup.
- Real transfer, Taproot address, restart, branch convergence and minimal supply
  checks; existing upstream consensus coverage acknowledged separately.
- Real Pay HTTP → invoice/SQLite → wallet/node scenarios: confirmations, retries,
  partial/overpayment, reorg review, outage, restart, stale state and attribution.
- Watchtower live-wallet audit checks plus strict report/transport privacy gates.
- Adversarial harness transport tests, synthetic secret canaries, per-run HMAC
  utility and JSON/JUnit allowlist reporting.
- Reproducible, unmodified app snapshots and source/archive/executable provenance.
- Linux network-isolated CI definition and portable harness selftest matrix.
- Four target criteria retained as failures for review; see FINDINGS.md and the
  completed run in VALIDATION.md. No official release, publication or external
  messaging performed.

# Changelog

## 0.1.0 — 2026-09-28

Initial community MVP.

- Local Vietnamese merchant UI and authenticated JSON API.
- Invoice creation with exact amounts, individual receiving addresses, durable
  idempotency keys and immutable confirmation thresholds.
- SQLite receipt ledger and event history; partial, multiple, excess and late
  payment handling.
- RPC transport, network/wallet guards, mempool checks, whole-snapshot
  reconciliation, reorg downgrades and stale-data gating.
- Isolated persistent demo, backup/init/package scripts, offline tests and CI configuration.
- Setup, API, architecture, compatibility, security and contributor documentation.

Validation is local/synthetic. Live WAM node acceptance and an independent
security audit remain outstanding. No sending, automatic refunds, public checkout
or webhook delivery is included in this release.

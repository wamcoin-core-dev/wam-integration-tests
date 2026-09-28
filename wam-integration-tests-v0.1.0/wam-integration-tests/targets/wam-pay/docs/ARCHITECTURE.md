# Design and invariants

The browser talks to a loopback-only authenticated HTTP service. The invoice
service owns SQLite transactions; a single background worker asks the selected
wallet adapter for a complete receipt snapshot. The RPC adapter connects only to
the loopback node. The demo adapter implements the same receive interface with
synthetic data. Runtime database bindings prevent switching modes in-place.

## Receiving

Invoice creation validates amount and metadata, acquires the service lock and
an immediate database transaction, checks the idempotency key, verifies node
readiness and obtains a new bech32 receiving address. Address ownership is checked
before commit. A unique database constraint prevents address reuse. A wallet RPC
success followed by a process crash can leave a labeled, unused address; it cannot
create two committed invoices for one idempotency key.

Money is stored as integers in units of 0.00000001 WAM. RPC JSON decimals are parsed
with `Decimal`; API amounts are canonicalized from strings. Binary floating-point
arithmetic is not used for money. Per-invoice confirmation policy is immutable.

## Reconciliation

1. Verify expected chain and genesis, synchronized node, peer availability,
   reasonably recent tip, loaded wallet, no rescan, and matching wallet tip.
2. Check that every invoice address is still owned/watched by the selected wallet.
3. Discover receipt transaction IDs with `listreceivedbyaddress`. Union them with
   all previously recorded IDs so vanished or conflicted receipts are rechecked.
4. Read each wallet transaction once. Exclude coinbase and negative-confirmation
   transactions. Require current mempool membership for zero-confirmation receipts.
5. Select `receive` details whose address matches an invoice. Deduplicate by
   `(txid, vout)`, not by transaction alone. Confirm each result references the
   original wallet tip; repeat readiness checks at the end.
6. In one SQLite transaction, deactivate prior outputs, upsert currently active
   outputs, preserve first-seen times and rederive every invoice. Record changes
   and the checked tip. Abort the entire update on any inconsistency or failure.

This rereads **receipts**, not UTXOs or wallet balances, so later spending does
not erase a payment. Mempool is inherently moving: the output list is not a globally
atomic mempool snapshot, and its zero-confirmation totals are advisory only.
Only confirmed receipts can make a live invoice eligible under its policy.

## Expiry and review

First-seen means the first successful application reconciliation that persisted
the output. It is intentionally not the node's transaction/block timestamp.
Enough on-time receipts can confirm after expiry and still be paid. An outage or
old restored backup can cause an actual earlier payment to require late review;
this is preferable to silently accepting an unverifiable deadline.

An invoice already paid that loses sufficient confirmations gets a permanent
review flag. Confirmation recovery updates amounts/status but does not clear the
flag. This version has no automatic fulfillment/refund or review-clear operation.
Merchant decisions remain in the external order system. Event history records
state/amount/review changes and new outputs; it is an operational audit log, not
a cryptographically tamper-evident ledger or every-block confirmation history.

## Concurrency and persistence

An OS advisory lock blocks multiple application processes from using the same
database. A service reentrant lock serializes API mutations and scans. SQLite
WAL, foreign keys, uniqueness constraints, full synchronous commits and immediate
write transactions protect accounting. The lock assumes other processes do not
manually write to the database. No database credentials or wallet secrets are stored.

Restart begins with readiness false even if prior data is recent. A failed scan
keeps the last committed snapshot and immediately disables freshness. Successful
scans expire after `stale_seconds`. A newly created invoice is not fresh until
its first scan. Host clock moving backwards disables freshness until consistent.

## Limits and follow-up work

The full-history scan favors inspectability over throughput. A production
successor should introduce indexed incremental scanning with reorg checkpoints,
durable outbox events, a separate authenticated merchant backend/public checkout,
rate limits and resource limits, and a reviewed WAM payment-URI convention. It
also needs live WAM regtest/testnet acceptance, a threat-model review and operational
load testing. None of those are represented as completed in this release.

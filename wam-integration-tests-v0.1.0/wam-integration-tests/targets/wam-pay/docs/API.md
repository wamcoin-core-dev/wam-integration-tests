# Local API v0.1

Base URL: `http://127.0.0.1:8787`. All `/api/*` endpoints require
`Authorization: Bearer <WAM_PAY_API_TOKEN>`. No CORS or public invoice lookup is
provided. JSON writes require `Content-Type: application/json`; maximum body is
8192 bytes. Amounts are fixed-point **strings**, never JSON floating-point values.
All timestamps are Unix seconds in UTC. IDs are opaque lowercase hex strings.

| Method | Route | Result |
|---|---|---|
| GET | `/healthz` | Public process liveness only; does not imply node readiness |
| GET | `/api/status` | Mode, readiness, last successful sync, generic error, policy |
| POST | `/api/invoices` | Create invoice with mandatory `Idempotency-Key` |
| GET | `/api/invoices?limit=50&offset=0` | Newest invoices; limit 1–200, offset 0–1000000 |
| GET | `/api/invoices/{id}` | Invoice, all recorded receipts, latest 100 events |
| POST | `/api/invoices/{id}/demo-payments` | Demo-only synthetic receipt/change |

## Create

```bash
curl http://127.0.0.1:8787/api/invoices \
  -H "Authorization: Bearer $WAM_PAY_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: order-20260928-001' \
  --data '{"amount":"10.00000000","memo":"Order 001","expires_in_seconds":1800}'
```

Required: `amount` > 0 and <= 22000000, maximum 8 decimals. Optional: `memo` up to
240 characters without control characters; `expires_in_seconds` integer 60–604800.
Unknown fields are rejected. The caller cannot choose the receiving address.
Idempotency keys are 8–128 characters from letters, digits, `_` and `-`.

Returns **201** for a new invoice, **200** for an identical replay, **409** when
the key was previously used with different normalized amount/memo/expiry input.
Retries after a lost response must use the **same key and input**. A crash before
database commit can leave an unused wallet address; no invoice is returned for it.

Invoice fields include `id`, `mode`, `address`, `amount`, `memo`, `status`,
`received`, `confirmed`, `remaining`, `overpaid`, `required_confirmations`,
`created_at`, `expires_at`, `checked_at`, `checked_tip`, `fresh`, `needs_review`
and `eligible_for_fulfillment`.

- `received`: all currently active receipts, including mempool transactions.
- `confirmed`: receipts individually meeting this invoice's confirmation depth.
- `remaining`: requested amount minus active received total, floored at zero.
- `overpaid`: confirmed amount above requested amount, floored at zero.
- `fresh`: a recent successful invoice scan, with no subsequent scan failure.
- `eligible_for_fulfillment`: live RPC mode, fresh, `paid`, and no sticky review
  flag. Always false in demo. It is an observation, not an irreversible delivery
  authorization. Requery immediately before a business decision and keep your
  own idempotent order fulfillment records; this app never fulfills an order.

## Statuses

| Status | Meaning |
|---|---|
| `pending` | No active received amount before expiry |
| `partially_paid` | Some amount received, less than requested, before expiry |
| `confirming` | Total received covers invoice but sufficient confirmed amount does not |
| `paid` | Enough confirmed funds were first observed before the deadline |
| `expired` | Deadline reached with no active receipts |
| `partial_expired` | Deadline reached with an insufficient received amount |
| `late_paid` | Enough confirmed funds, but not enough were first observed before expiry |

Expiry never stops monitoring. `confirming` may persist past expiry and become
`paid` when on-time receipts confirm. A transaction first noticed during recovery
after expiry is conservatively late, regardless of its block timestamp. A prior
paid invoice that drops below the threshold gets a sticky `needs_review=true`.

Status can move backwards after reorg, replacement or eviction. On RPC failure,
last known amounts/status remain; `fresh` and fulfillment eligibility become
false. Expiry is still calculated against wall time. Consumers must inspect these
flags rather than relying on the status label alone.

## Demo actions

Create synthetic receipt:

```json
{"amount":"10.00000000","confirmations":0}
```

Response contains `txid` and updated `invoice`. Change that receipt:

```json
{"txid":"<returned-demo-txid>","confirmations":6}
```

Use `-1` to drop it. Dropped demo receipts cannot be revived through this helper;
add a new synthetic receipt instead. Demo writes are not idempotent; use once per
intended simulation. These endpoints are absent from a server started in RPC mode.

## Errors

400 invalid input; 401 bad/missing token; 403 host/origin rejected; 404 unknown
resource; 409 idempotency conflict; 503 node/address allocation unavailable;
500 unexpected internal error. Error JSON has an `error` string. Node error
messages, RPC passwords, cookies and API tokens are not returned.

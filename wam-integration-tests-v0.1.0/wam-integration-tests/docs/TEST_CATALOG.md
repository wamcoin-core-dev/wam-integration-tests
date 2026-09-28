# Test catalog

Static descriptions corresponding to public report IDs.

`selftest` uses local synthetic RPC servers and filesystem fixtures. `regtest` runs actual WAM nodes and bundled applications; PAY-011 and WT-004–005 also inject synthetic faults. WT-003 is a stronger criterion than the legacy stable-hash design.

## selftest

| ID | Criterion | Source |
|---|---|---|
| RPC-001 | Reject remote hosts, credentials, alternate IP encodings and URL injection | `tests/transport.py` |
| RPC-002 | Ignore ambient HTTP proxy configuration | `tests/transport.py` |
| RPC-003 | Reject HTTP redirects without a second request | `tests/transport.py` |
| RPC-004 | Remote error messages never enter exception text | `tests/transport.py` |
| RPC-005 | Reject mismatched response IDs | `tests/transport.py` |
| RPC-006 | Reject duplicate JSON keys | `tests/transport.py` |
| RPC-007 | Reject NaN and Infinity in RPC responses | `tests/transport.py` |
| RPC-008 | Bound response bytes | `tests/transport.py` |
| RPC-009 | Malformed and ambiguous RPC envelopes fail closed | `tests/transport.py` |
| RPC-010 | Rotate cookie authentication without caching old credentials | `tests/transport.py` |
| RPC-011 | Percent-encode wallet routing without leaking labels | `tests/transport.py` |
| RPC-012 | Private-key export and unlisted methods are denied before transport | `tests/transport.py` |
| RPC-013 | Refuse mutations when the node reports mainnet | `tests/transport.py` |
| RPC-014 | Refuse mutations on a regtest chain with the wrong genesis | `tests/transport.py` |
| RPC-015 | Re-attest chain identity before each mutating request | `tests/transport.py` |
| RPC-016 | Timeout does not retry a mutating RPC | `tests/transport.py` |
| RPC-017 | Reject malformed and oversized cookies | `tests/transport.py` |
| RPC-018 | Reject an HTTP error masquerading as a successful RPC | `tests/transport.py` |
| SAFE-001 | Per-run HMAC labels are stable within a run and unlinkable across runs | `tests/privacy.py` |
| SAFE-002 | Disposable workspace is removed after an exception | `tests/privacy.py` |
| SAFE-003 | Failed assertions and exceptions produce no raw data in JSON/JUnit | `tests/privacy.py` |
| SAFE-004 | Reject report-field injection | `tests/privacy.py` |
| SAFE-005 | Detect appended secret text in XML artifacts | `tests/privacy.py` |
| SAFE-006 | Refuse to publish directories containing extra raw files | `tests/privacy.py` |
| SAFE-007 | Missing tests cannot produce a green report | `tests/privacy.py` |
| SAFE-008 | Refuse to overwrite an existing report | `tests/privacy.py` |
| SAFE-009 | Verify exact bundled application bytes before loading targets | `tests/privacy.py` |
| SAFE-010 | A binary checksum mismatch prevents process launch | `tests/privacy.py` |
| SAFE-011 | Node configuration uses fresh datadir, local binding and disabled discovery | `tests/privacy.py` |

## regtest

| ID | Criterion | Source |
|---|---|---|
| CORE-001 | Both owned nodes are on the pinned WAM regtest chain | `scenarios/core.py` |
| CORE-002 | Cookie-authenticated RPC refuses an unauthenticated request | `scenarios/core.py` |
| CORE-003 | All observed peers are local and no public node address is advertised | `scenarios/core.py` |
| CORE-004 | Fresh descriptor wallet produces distinct valid Taproot addresses | `scenarios/core.py` |
| CORE-005 | Payment reaches the second node mempool and receives confirmations | `scenarios/core.py` |
| CORE-006 | Cookie rotates across node restart and the wallet preserves its receipt | `scenarios/core.py` |
| CORE-007 | Mined coinbase pays the consensus treasury amount using exact decimals | `scenarios/core.py` |
| CORE-008 | Private datadir and cookie have owner-only POSIX permissions | `scenarios/core.py` |
| CORE-009 | Supply reporting remains under the WAM cap | `scenarios/core.py` |
| CORE-010 | Two isolated branches converge to the longer valid branch | `scenarios/core.py` |
| CORE-011 | Immediately restored blocks have RPC header-height compatibility with Pay | `scenarios/core.py` |
| PAY-001 | Unauthenticated invoice API reveals no wallet, memo, token or customer data | `scenarios/pay.py` |
| PAY-002 | Create invoice over HTTP, pay on-chain, and gate fulfillment on confirmations | `scenarios/pay.py` |
| PAY-003 | Different invoices receive different owned addresses and no memo enters wallet labels | `scenarios/pay.py` |
| PAY-004 | Concurrent HTTP retries produce exactly one invoice and address | `scenarios/pay.py` |
| PAY-005 | Partial payments and overpayment reconcile without double counting | `scenarios/pay.py` |
| PAY-006 | Invalidating a paid block revokes fulfillment and latches manual review | `scenarios/pay.py` |
| PAY-007 | Node outage preserves prior accounting while disabling fulfillment | `scenarios/pay.py` |
| PAY-008 | Service restart recovers invoices and requires a fresh sync before fulfillment | `scenarios/pay.py` |
| PAY-009 | Reject cross-origin and forged Host requests even with a valid API token | `scenarios/pay.py` |
| PAY-010 | Client precision violations cannot allocate an invoice | `scenarios/pay.py` |
| PAY-011 | Secret-bearing upstream errors cannot reach Pay API responses or application logs | `scenarios/pay.py` |
| PAY-012 | Stale reconciliation disables fulfillment using the application's clock | `scenarios/pay.py` |
| PAY-013 | A single transaction can fund distinct invoice outputs without misattribution | `scenarios/pay.py` |
| PAY-014 | Pay refuses invoice creation if its independent genesis pin is wrong | `scenarios/pay.py` |
| WT-001 | Watchtower reads a real wallet and masks reused receiving addresses | `scenarios/watchtower.py` |
| WT-002 | Audit makes only the declared read-only RPC calls | `scenarios/watchtower.py` |
| WT-003 | Default pseudonyms cannot link the same receiving address across independent reports | `scenarios/watchtower.py` |
| WT-004 | Remote error text cannot be embedded in a shareable Watchtower report | `scenarios/watchtower.py` |
| WT-005 | Watchtower transport rejects redirects before contacting the target | `scenarios/watchtower.py` |
| WT-006 | Watchtower does not report Tor anonymity merely because RPC is local | `scenarios/watchtower.py` |


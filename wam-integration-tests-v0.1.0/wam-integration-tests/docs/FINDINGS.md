# Findings against the supplied versions

These are reproducible **acceptance-criteria failures**, not claims that all
funds are compromised or that WAM's consensus is broken. Scope: the pinned
v0.1.11 Linux daemon, Pay v0.1.0 and Watchtower v0.3 snapshots. No real keys,
funds, users or public network are involved.

## CORE-011 — RPC height mismatch immediately after reconsiderblock

On the tested WAM v0.1.11 regtest binary: mine blocks, invalidate the first,
then reconsider it. The active chain is restored, but `getblockchaininfo`
can report the restored `blocks` height while `headers` remains at the
invalidated ancestor's height. The observation persists across repeated reads
until a fresh block is processed. A minimal reproduced sequence showed
`blocks=112`, `headers=110` after reconsidering the two blocks.

Pay correctly fails closed because its readiness contract requires equal
block/header heights. This temporarily prevents invoice creation/reconciliation
after that specific administrative regtest operation. It is not evidence of
fund theft, an invalid spend or ordinary mainnet reorg failure.

The test records the mismatch as a failure **before** mining a fresh block to
restore the shared fixture. PAY-006 then separately tests actual payment
confirmation rollback, manual-review latching and recovery. Do not remove
Pay's readiness checks to make this scenario pass. Ask the Core maintainers
whether the inherited header-tip cache should be refreshed on reconsideration
or whether the client contract needs a reviewed refinement.

## WT-003 — Stable pseudonyms allow cross-report linkage

Watchtower v0.3 deliberately uses truncated, unsalted SHA256 of an address and
wallet name. Raw strings are hidden, but a repeated address produces the same
identifier in independent reports. Someone with a candidate address can also
compute its identifier. This behavior matches v0.3's documented stable-hash
design; it does not satisfy this suite's stronger cross-report unlinkability
criterion.

Proposed direction: default to aggregate statistics without identifiers, or
use a fresh random per-report HMAC key for within-report grouping. Do not
publish/persist that key or a reversible mapping. If longitudinal tracking is
an explicit feature, make the linkage tradeoff visible and opt-in. Fresh
pseudonyms do not remove correlation via counts/timing or public on-chain data.

## WT-004 — Raw upstream error text enters the audit report

`assess_privacy` includes `str(WatchtowerError)` in finding details when a wallet
RPC fails. The transport can put raw HTTP/RPC response details into that error.
A synthetic canary placed in such an error is present in the report returned
by the real audit function. This can expose endpoint messages, paths or other
metadata when a report is shared; it is not a claim that ordinary responses
always contain secrets.

Proposed direction: fixed public error codes and short predefined descriptions.
Keep sensitive local diagnostics separate and opt-in, with documented retention.
The **new test runner's own** JSON/JUnit artifacts never embed those raw reports
or exception messages, including on this test's failure.

## WT-005 — Redirects can send RPC requests to a different destination

The v0.3 transport uses the default `urllib.request.urlopen` opener. In a local
synthetic test, HTTP 301/302/303 redirects can produce a request to the supplied
destination, forwarding the Authorization header to the second loopback port;
307/308 did not follow the POST in this reproduction. The strict gate requires no
redirect follow at all. This is a transport-boundary concern when the endpoint
is malicious or misconfigured. Both endpoints in the reproduction are local;
no external service receives test credentials.

| Synthetic response | Requests observed at redirected port | Authorization forwarded |
|---|---:|---|
| 301 | 1 | Yes |
| 302 | 1 | Yes |
| 303 | 1 | Yes |
| 307 | 0 | No |
| 308 | 0 | No |

Proposed direction: an explicit no-redirect opener, no ambient HTTP proxies,
literal-loopback validation at client construction, strict response IDs and
bounded response sizes. Review these together before changing the target.

## Handling the failures

The suite does not silently patch target snapshots or mark these criteria as
expected failures. The full regtest profile exits nonzero while they remain.
That is the intended release gate. A maintainer can reproduce each criterion,
review a fix, update the target snapshot and manifest explicitly, and rerun.
Fixing these specific issues would not constitute a full security/privacy audit.

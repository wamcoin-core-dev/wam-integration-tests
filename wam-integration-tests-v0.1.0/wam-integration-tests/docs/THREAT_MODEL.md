# Privacy threat model and test boundaries

## Assets and observers

Protect real seeds/private keys, wallet names and addresses, RPC cookies,
invoice memos and customer identifiers, payment graphs, and local filesystem
paths from accidental disclosure in developer logs, CI artifacts and public
bug reports. Observers include artifact readers, a malicious/misconfigured RPC
endpoint, a redirect destination, ambient proxy infrastructure and unrelated
network peers. Tests only create synthetic data, including synthetic canaries.

## Controls and evidence

| Requirement | Mechanism | Evidence |
|---|---|---|
| No real funds | No external datadir/config/URL/seed options; create fresh nodes | SAFE-011, CORE-001 |
| Correct chain before changes | Independently pinned regtest genesis; attest every mutating RPC | RPC-013–015 |
| Confidential RPC auth | Cookie file; never credentials in process arguments; literal loopback | RPC-001–004, CORE-002 |
| No proxy/redirect exfiltration | Direct HTTPConnection; no redirect implementation | RPC-002–003 |
| Minimal report data | Closed JSON schema, canonical XML and fixed failure codes | SAFE-003–008 |
| Avoid address reuse | Fresh receiving address per invoice | CORE-004, PAY-003–004 |
| Correct receipt attribution | Real wallet RPC + actual HTTP API + SQLite reconciliation | PAY-002, PAY-005–008, PAY-013 |
| No raw target-error disclosure | Secret-bearing canaries injected at failure boundaries | PAY-011, WT-004 |
| No stable address pseudonyms across reports | Strict target criterion | WT-003; see documented failure |
| Restricted audit authority | Observe actual Watchtower method calls | WT-002 |
| Minimize retention | Stop owned processes; remove temporary chain/wallet data | SAFE-002 and context cleanup |

## What these tests do not prove

- No claim of anonymous transactions, hidden amounts, shielded pools, ring
  signatures, PayJoin, CoinJoin or resistance to chain analysis. WAM's existing
  transparent transaction model is not changed by a testing tool.
- A new address reduces one source of linkage; it does not stop change-output,
  timing, amount, input-ownership or network correlations. Taproot capability
  checks do not certify privacy. Pay v0.1.0 explicitly requests bech32 addresses.
- Tor and BIP324 are not exercised against external networks. We check that the
  audit does not infer Tor anonymity from local RPC. A full Tor test needs a
  separately reviewed network lab and threat model.
- Direct CLI execution is not a sandbox for a malicious binary or imported
  Python code. Hash pinning identifies bytes, not trustworthiness. The operator
  must review the binary origin, dynamic libraries, Python runtime and snapshots.
- No resistance to a hostile same-user process, administrator, memory inspection,
  swap, crash dumps, backups, physical recovery or filesystem snapshots.
- Permission bits are checked on POSIX. Windows ACL isolation is not attested.
- Deleting temporary files is not cryptographic erasure. SIGKILL, power loss or
  an unkillable process can leave temporary synthetic data behind. Use an encrypted
  volume and ephemeral CI host when stronger local-retention controls are needed.
- Report case results reveal which software versions satisfy criteria. They are
  public test metadata, not a differential-privacy mechanism.
- Response-byte caps do not constitute a complete HTTP slowloris defense. Requests
  have socket timeouts and CI has a whole-job timeout; no guarantee is made for a
  compromised daemon that dribbles data forever or forks unrelated processes.
- The repository's existing consensus tests remain the authority for negative
  treasury/PoW/genesis/epoch scenarios. The ecosystem smoke checks are not a new
  consensus audit or benchmark.

## Failure behavior

Unknown RPC methods fail before transport. Private-key export/unlock/import
methods are outside the harness allowlist. Automatic retries are not made,
especially after a timed-out mutation whose outcome could be unknown. Node
startup failures block all integration cases. Missing/skipped coverage is a
nonzero exit. Target privacy findings are not made to disappear by sanitizing
the target output before evaluating it.

The public report is synthesized from an allowlist rather than a regex-filtered
debug log. Regex scrubbing alone cannot enumerate every possible secret format.

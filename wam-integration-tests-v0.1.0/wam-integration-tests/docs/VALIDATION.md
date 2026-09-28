# Completed validation — 2026-09-28

This record describes execution completed in the build environment. It does not
claim that the supplied GitHub workflow has run or that all target criteria pass.

| Profile | Passed | Failed | Errors | Not run | Exit |
|---|---:|---:|---:|---:|---:|
| Harness selftest | 29 | 0 | 0 | 0 | 0 |
| Real WAM regtest + Pay/Watchtower integration | 27 | 4 | 0 | 0 | 1 |
| **Total** | **56** | **4** | **0** | **0** | **Not all criteria pass** |

The regtest profile's four failures are **CORE-011, WT-003, WT-004, WT-005**.
They are retained as blocking criteria, not marked expected or skipped. See
[FINDINGS.md](FINDINGS.md) for the reproduction and interpretation of each.

## What actually ran

- Two independent processes using the official Linux WAM v0.1.11 release binary,
  with verified archive/executable digests and fresh temporary data directories.
- Cookie-authenticated JSON-RPC, real RandomX regtest block generation, real
  transactions, local P2P relay, confirmations, restart and branch convergence.
- Real bundled Pay HTTP server, invoice service, SQLite database, RPC client and
  wallet adapter. All 14 Pay criteria passed after correcting the test fixture
  restoration sequence described below.
- Real bundled Watchtower audit against synthetic wallets on the live regtest
  node; synthetic RPC/HTTP faults for the error/redirect boundaries.
- Independent synthetic transport probes confirmed that the Watchtower redirect
  issue forwarded Authorization to a second **local** port for 301/302/303.
- Public report schema validation for both JSON/JUnit pairs.
- Python AST parsing for all source files, TOML parsing, workflow YAML parsing,
  Bash syntax validation and target snapshot checksums.

The machine was Linux x86_64, Ubuntu 24.04, Python 3.12.14. The native daemon
needed libevent runtime libraries, provided locally from Ubuntu 2.1.12 packages.
See PROVENANCE.md for pinned source and binary identities.

## Test development corrections

Early development runs were blocked by missing native libevent dependencies,
then by test-node configuration issues: `connect=0` needed the `[regtest]`
section, and the initial `maxconnections=8` left no inbound slots after Core's
outbound reserve. The completed run uses 16 and waits for a version handshake.
These were harness setup issues, not WAM product findings.

Another early run showed cascading Pay failures after a test's
`reconsiderblock`. Investigation isolated the real block/header RPC mismatch.
CORE-011 now captures that observation as a dedicated failure. Cleanup mines
a fresh block before subsequent cases; PAY-006 tests payment rollback and
review latching without allowing a broken shared fixture to contaminate later
results. No target source code was changed to produce passing cases.

## Evidence files

The release includes `evidence/selftest/{summary.json,junit.xml}` and
`evidence/regtest/{summary.json,junit.xml}` copied from the completed runs.
These contain only the minimal public schema; no chain data, wallets, addresses,
TXIDs, auth headers, RPC bodies or diagnostic logs are bundled as evidence.
The source archive additionally carries MANIFEST.sha256 for byte verification.

## Not validated here

- GitHub Actions execution, branch-protection wiring or artifact-upload behavior
  on GitHub. The workflow is supplied, not reported as passing.
- OS-enforced network isolation in this container: unprivileged namespace
  creation was denied by the host (`uid_map` permission). The completed local
  node run used explicit loopback binding and disabled discovery/automatic peers;
  all observed peers were local. No claim of full local egress containment is made.
  The CI namespace step fails if isolation cannot be established.
- Native macOS/Windows daemon runs or Windows ACL enforcement.
- Mainnet/public-testnet operation, external wallet/DEX adapters, Tor/PayJoin/
  CoinJoin, cryptographic proofs, a full consensus audit, load/stress benchmarks,
  binary reproducible builds or independent publisher signature verification.

The correct acceptance statement is: **the harness works and exposes four
unresolved target criteria on the pinned versions**, not “WAM is privacy-certified.”

# WAM Ecosystem Integration Tests

An independent, privacy-oriented **test contribution** for WAM Core, WAM Pay and
WAM Watchtower. Python standard library only. It launches two disposable WAM
regtest nodes, creates synthetic wallets, exercises real payments and reorgs,
and exports minimal JSON/JUnit evidence.

This is a reviewable v0.1.0 contribution, not an official WAM release or a
cryptographic anonymity audit. Read [validation](docs/VALIDATION.md) before
interpreting a green or red result.

## How this fits the existing WAM repository

WAM **already has integrations and integration/functional tests**. At reviewed
main commit `5b9cb8f6a79c04e0ffb6244d045a4a51a896ea59`:

| Existing upstream area | Purpose | This contribution |
|---|---|---|
| [`integration/`](https://github.com/wamcoin-core-dev/wam-coin/tree/5b9cb8f6a79c04e0ffb6244d045a4a51a896ea59/integration) | Venue/wallet adapters, configuration and submission material for Komodo, BasicSwap, Block DX, Bisq, Haveno, ElectrumX and registries | Does not replace these adapters or claim venue acceptance |
| [`test/functional/`](https://github.com/wamcoin-core-dev/wam-coin/tree/5b9cb8f6a79c04e0ffb6244d045a4a51a896ea59/test/functional) | Real-node tests for treasury validation, genesis, PoW and RandomX epoch behavior | Leaves consensus-negative testing to upstream; includes limited smoke assertions for its own fixture |
| `scripts/run_functional_tests.sh`, `scripts/regtest_smoke.py` | Existing test execution and chain smoke checks | Adds WAM **node → Pay → Watchtower** behavior and privacy regression gates |

Suggested upstream placement: a separate QA contribution under `contrib/qa/`
or a WAM-organization test repository, subject to maintainer review. No upstream
repository was changed or published by this build.

## Quick start

Python 3.11+; Python 3.12 is the tested build runtime. Run from this directory:

```bash
python -m wam_it selftest
```

This checks the harness using adversarial local HTTP servers. It does **not**
demonstrate that a WAM daemon or payment works. Run the actual integration profile:

```bash
python -m wam_it regtest \
  --wamd /absolute/path/to/wamd \
  --sha256 EXPECTED_EXECUTABLE_SHA256 \
  --report-dir reports/regtest
```

The checksum is for the executable, not its ZIP/tar archive. The tested Linux
v0.1.11 daemon digest is
`625609c08afef441e9dddd71330dcab1cec112d6fabe361769b9907f0efe7ab4`.
See [setup](docs/SETUP.md) and [Vietnamese instructions](docs/QUICKSTART_VI.md).
Use a new report directory for each run; existing output is never overwritten.

An optional, explicit download command is supplied for the pinned Linux release:

```bash
python scripts/fetch_release.py
python -m wam_it regtest --wamd .tools/wamd \
  --sha256 625609c08afef441e9dddd71330dcab1cec112d6fabe361769b9907f0efe7ab4
```

Downloading the release contacts GitHub. The test runner does not download
anything, contact an explorer, query a public node, or use a public testnet.

## Privacy requirements

- No real wallet/seed/key/address input. No command to attach to an existing node.
- New private temporary directories; fresh synthetic wallets and regtest-only funds.
- Literal loopback RPC, cookie auth, no HTTP proxy or redirect, bounded responses.
- WAM regtest chain + genesis checked before every harness mutating RPC.
- A pinned executable and checksummed application snapshots.
- No RPC bodies, addresses, TXIDs, labels, invoices, tokens, paths, raw exceptions
  or traceback text in exported test reports. Reports use static case IDs.
- Session HMAC pseudonyms for in-memory use; no stable cross-run user identifiers
  in the public report. The HMAC utility is not silently applied to targets to
  hide their own failing privacy behavior.
- Node/app temporary data is removed on normal completion, failures and handled
  interruption. Deletion is not secure erasure; see the threat model.
- Linux CI runs the test phase in a network namespace with loopback only. Direct
  CLI execution enforces local configuration but is not an OS network sandbox.

## Reading the result

`summary.json` and `junit.xml` contain case IDs, statuses, fixed error codes,
counts and the software binary digest. Descriptions are in the static
[test catalog](docs/TEST_CATALOG.md), not derived from runtime data.

```bash
python -m wam_it check-report reports/regtest
```

Exit `0`: all selected cases ran and passed. Exit `1`: a tested criterion failed.
Exit `2`: execution error, missing coverage, setup/cleanup failure or cancellation.
A missing binary never becomes a skipped green integration run.

The strict privacy criteria are intentionally stronger than Watchtower v0.3's
documented stable hashing. **Known target failures remain real failures**, not
`xfail`, warning-only checks or secretly patched targets. See
[findings](docs/FINDINGS.md). A working test suite can correctly produce a red
target verdict; that is evidence to review and fix, not a reason to weaken tests.

## Contents

| Path | Role |
|---|---|
| `wam_it/` | Node lifecycle, RPC, minimal reports and suite runner |
| `tests/` | Harness privacy and adversarial transport checks |
| `scenarios/` | Real-chain Core/Pay/Watchtower cases and injected failure cases |
| `targets/` | Unmodified Pay v0.1.0 and Watchtower v0.3 snapshots, licenses and checksums |
| `.github/workflows/ci.yml` | Least-privilege CI with pinned actions and restricted report uploads |
| `docs/` | Threat model, coverage, provenance, findings and validation |

No production daemon is bundled. Python dependencies: none. Native daemon
runtime libraries are still required. MIT; included targets retain their
original licenses.

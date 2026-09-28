# Setup and reproducibility

## Trusted inputs

Run from this repository's root with Python 3.11 or newer. No pip packages are
needed. Use a reviewed WAM daemon from the canonical project or a reviewed local
build. Pin its executable hash. Do not use a daemon's own answer as the expected
genesis: the independent value lives in `wam_it/rpc.py`.

The runner accepts only a daemon path and its hash. It never accepts a production
datadir, a remote RPC URL, RPC credentials or wallet keys. It creates wallets and
funds them by regtest mining. Allow roughly 2 GB free RAM for the two light-mode
RandomX nodes and validation overhead; no performance guarantee is implied.

## Linux

The official Linux v0.1.11 daemon dynamically links libevent and SQLite. On
Ubuntu 22.04, install `libevent-2.1-7`, `libevent-pthreads-2.1-7`, and the normal
SQLite runtime through your package manager. Ubuntu 24.04 uses the corresponding
`libevent-2.1-7t64` and `libevent-pthreads-2.1-7t64` package names. The build
validation used Ubuntu 24.04, Python 3.12.14 and libevent 2.1.12 from Ubuntu.

```bash
python3 scripts/fetch_release.py
python3 -m wam_it regtest --wamd .tools/wamd \
  --sha256 625609c08afef441e9dddd71330dcab1cec112d6fabe361769b9907f0efe7ab4 \
  --report-dir reports/run-001
```

When supported by your Linux host, run with an OS-level network boundary:

```bash
bash scripts/run_isolated_linux.sh "$PWD/.tools/wamd" \
  625609c08afef441e9dddd71330dcab1cec112d6fabe361769b9907f0efe7ab4 \
  reports/isolated-001
```

This uses an unprivileged user/network namespace. If the host denies namespace
creation, the wrapper fails; it does not silently downgrade to connected mode.
The CI workflow uses its ephemeral runner's `sudo unshare --net` equivalent.
The direct Python command still disables discovery, automatic peers and
external RPC, but does not certify OS-level egress isolation.

## Windows / PowerShell

The harness selftest is portable:

```powershell
py -3 -m wam_it selftest --report-dir reports/selftest-windows
```

For experimental native integration execution, obtain the matching reviewed
Windows WAM release, verify its publisher's archive checksums/signature according
to the WAM release instructions, then pin the extracted executable's checksum:

```powershell
$wamBinary = (Resolve-Path 'C:\wam-test-tools\wamd.exe').Path
$wamDigest = (Get-FileHash -Algorithm SHA256 $wamBinary).Hash.ToLowerInvariant()
py -3 -m wam_it regtest --wamd $wamBinary --sha256 $wamDigest --report-dir reports/regtest-windows
```

Computing a file's hash only pins its current bytes; it is not publisher
authentication. Native Windows execution is not part of the completed local
validation. The POSIX permission case is reported `not_run` on Windows, so the
full profile intentionally cannot claim all privacy criteria there. Prefer a
reviewed Linux CI run for the published acceptance result.

## macOS

Use `python3 -m wam_it selftest`. A reviewed macOS binary can be passed to
`regtest` with its own executable checksum; the Linux checksum is inapplicable.
Native macOS integration and network isolation were not validated in this build.

## Errors and diagnosis

| Public code | Check locally |
|---|---|
| `BINARY_DIGEST` | Expected digest is the executable's SHA256; review version/bytes |
| `NODE_START` | Executable permissions, native shared libraries, CPU/OS compatibility |
| `RPC_CREDENTIALS` | Fresh node cookie creation and local filesystem permissions |
| `CHAIN_MISMATCH` | Review binary/source; never replace the pinned genesis to force a pass |
| `WAIT_TIMEOUT` | Local P2P handshake/sync; resource pressure and daemon compatibility |
| `TARGET_CHANGED` | Snapshot differs from reviewed manifest; follow CONTRIBUTING.md |
| `ASSERTION_FAILED` | Look up the case ID in TEST_CATALOG.md and FINDINGS.md |
| `REPORT_EXISTS` | Choose a new report directory |

No `--show-secrets`, raw-log artifact export or live-wallet debug mode is supplied.
For deeper diagnosis, reproduce with synthetic data on a disposable developer
machine; do not paste a real node's config, RPC cookie or wallet files into an issue.

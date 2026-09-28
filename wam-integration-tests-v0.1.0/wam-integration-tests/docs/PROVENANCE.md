# Source and binary provenance

Reviewed on 2026-09-28. Source was read through Git directly; a browser renderer
was not relied on for code behavior.

| Input | Identity |
|---|---|
| WAM repository | https://github.com/wamcoin-core-dev/wam-coin |
| Daemon source tag | `v0.1.11` |
| Resolved tag commit | `8a3f4fe4f1d804c378f795d4cc281ec5125f75f3` |
| Main branch inspected for existing integration work | `5b9cb8f6a79c04e0ffb6244d045a4a51a896ea59` |
| Linux release archive | `wam-coin-v0.1.11-x86_64-linux-gnu.tar.gz` |
| Archive SHA256 | `bd010ed615ab8063d5c12aa61236311ece7e9d19896d9541dacba1888dd9987a` |
| Extracted `wamd` SHA256 | `625609c08afef441e9dddd71330dcab1cec112d6fabe361769b9907f0efe7ab4` |
| Pay snapshot | User-supplied `wam-pay-v0.1.0.zip`; file/ZIP checksums in `targets/manifest.json` |
| Watchtower snapshot | User-supplied `WAM-Watchtower-v0.3.zip`; source/license and checksums in `targets/manifest.json` |

The archive hash matched the digest exposed by the release API. This checks byte
identity relative to the release publication, not independent publisher
authentication. A GPG signature, reproducible native build and build attestation
were not verified here. Review the project's signing process before selecting
an operational binary. No official endorsement is implied.

## Source-grounded compatibility decisions

- [`src/wam/chainparams.cpp`](https://github.com/wamcoin-core-dev/wam-coin/blob/8a3f4fe4f1d804c378f795d4cc281ec5125f75f3/src/wam/chainparams.cpp):
  regtest genesis `b88f3d26…d6d3d30d`, address HRP `wamrt`, maturity 100,
  accelerated 150-block halving, no fixed/DNS seeds, Taproot always active.
- `scripts/patch_upstream.py`: WAM changes to the inherited Bitcoin Core RPC,
  address and RandomX generation paths. No assumption that stock Bitcoin
  regtest addresses or mainnet subsidy intervals apply to WAM regtest.
- `scripts/regtest_smoke.py`, `test/functional/`: pre-existing chain and
  consensus tests. This contribution explicitly acknowledges their coverage.
- Pay's RPC contract was validated through its real adapter and invoice service;
  synthetic failure injection is identified separately in the catalog.
- Watchtower is evaluated as provided, including its stable SHA256 masking
  design and its error-report behavior. Findings apply to that exact snapshot,
  not an unseen future upstream version.

GitHub Actions references are immutable commits resolved from these tags:
checkout v4.2.2, setup-python v5.6.0, upload-artifact v4.6.2. The workflow has not
been triggered from this build environment; a checked-in workflow is not proof
of CI success.

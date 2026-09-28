# Security and privacy reporting

This is independent test tooling, not an officially audited WAM component.
Only ephemeral regtest wallets are supported. Never provide real seed words,
private keys, wallet backups, RPC cookies or production database files.

For a suspected exposure, provide the software version, static test ID and
minimal synthetic reproduction. Use the responsible maintainer's private
security channel for exploitable issues; consult the canonical WAM repository's
current SECURITY.md for WAM Core issues. No private contact address is invented
by this project. Do not attach raw logs to a public issue.

Known criteria not met by bundled historical snapshots are described in
`docs/FINDINGS.md`. They are not silently fixed or exempted by the runner.
Refer to `docs/THREAT_MODEL.md` for the threat model and untested boundaries.

# Security policy

WAM Pay v0.1.0 is an unaudited local prototype. No version is currently represented
as suitable for unattended public merchant deployment. Maintainers should define
a private reporting contact or enable GitHub private vulnerability reporting
before making the repository public. Until then, share a minimal private report
with the repository owner; never include keys, cookies, tokens or wallet backups.

## Trust boundaries

- The node and operating-system account are trusted. A dishonest/compromised
  node can lie about payments. Genesis checking does not make it trustworthy.
- Application RPC methods are receive-oriented. This is not a sandbox for a
  compromised process: cookie/full RPC credentials can authorize other node
  actions outside this client's allowlist. Use a restricted account and prefer
  a properly provisioned watch-only wallet with an external signer.
- No seed, private-key or signing data is requested or stored by the app. Keys
  may still reside in a hot node wallet; the app is not a cold-storage system.
- SQLite contains customer memos, addresses and transaction histories. Protect
  local files and backups. POSIX files use restrictive modes; on Windows use
  account ACLs because `chmod` does not provide the same permission boundary.
- A read-only local service remains accessible to other processes/users that can
  access its socket. Protect the bearer token and lock the OS session.

## Built-in controls

Loopback-only HTTP/RPC, API bearer authentication with constant-time comparison,
strict Host and Origin checks, no permissive CORS, no redirects/proxy inheritance
for RPC, strict RPC method allowlist, bounded request/response sizes, decimal
validation, parameterized SQL, in-memory browser token, no third-party UI scripts,
DOM text rendering, CSP/no-store headers and no request-body/access logging.
Authentication covers all invoice and status API routes; static UI and liveness
are public locally. No customer invoice is anonymously exposed.

The built-in Python HTTP server is intended for local operation and has no
production-grade rate limiter or global thread/RPC scan budget. Do not expose
it with port forwarding, LAN binding or a public reverse proxy. Network exposure
needs a reviewed server design, separate identities, TLS and resource controls.

## Payment risks

- Zero-confirmation transactions never qualify as paid.
- Reorgs can reverse confirmed payments at any depth. Six confirmations is an
  application setting, not a WAM network security claim.
- Last-known status is not sufficient when `fresh=false`; RPC outages preserve
  data but disable eligibility. Even a fresh response can become outdated.
- First-seen expiry is conservative across downtime; handle late payments manually.
- Review flags remain after a previously paid invoice loses confirmations. No
  automatic delivery, refund or review-clear endpoint is implemented.
- Database state is not cryptographically tamper-proof. Keep separate merchant
  records and practice wallet plus database restoration.

## Contributing security fixes

Prefer a private reproducer with mocked RPC data. Describe affected commit,
expected and observed behavior, and a regression test. Do not upload live wallet
files or run destructive chain commands against a user's mainnet node.

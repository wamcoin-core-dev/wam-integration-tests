# Contributing

Use Python 3.11+ and keep the default test suite offline and dependency-free.

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q src scripts
```

Use a focused branch and describe the user-visible problem, the change and the
validation. For payment logic, test behavior around exact amounts, duplicate
outputs, partial payments, lost responses, expiry, outages, reorgs and restarts.
Do not merely assert that implementation helpers call one another.

Keep monetary values as integer base units internally and decimal strings at
public boundaries. Never accept caller-supplied receiving addresses. Preserve
the idempotency contract and whole-snapshot commit. A change to schema version
requires an explicit tested migration and backup/rollback instructions; never
silently rewrite live data. Do not weaken genesis or freshness checks to get a
test to pass.

Any new spending RPC, webhook, public endpoint, dependency or network service
requires a design/threat review and a corresponding documentation change. Never
commit `config.json`, environment files, wallets, cookies, tokens or databases.
Use only fake credentials and synthetic receipts in tests. Public contributions
must not imply approval by the WAM core team.

The dashboard uses external local JS/CSS files to keep CSP restrictive. Render
untrusted data with `textContent`, not `innerHTML`. Verify narrow/mobile layouts
when editing UI. Follow [SECURITY.md](SECURITY.md) for vulnerability reports.

To build a source archive: `python3 scripts/package_release.py`. The package is
allowlisted and excludes runtime files. Review archive contents before release.
Run an actual WAM test-network acceptance test before promoting RPC compatibility
from documented target to validated integration.

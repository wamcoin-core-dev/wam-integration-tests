# Contributing

Start with the upstream-fit table in README.md. Do not duplicate WAM's
consensus tests or venue adapters without explaining the missing coverage.

Every new case needs a stable public ID, a concrete invariant, a meaningful
failure assertion and an entry in the catalog. Use synthetic fixtures only.
Do not put addresses, wallet names, test parameter values or customer text in
dynamic test names. Do not use `expectedFailure` to hide a privacy finding.
Do not export traceback or node logs as CI artifacts.

Run `python -m wam_it selftest` and the real `regtest` profile for changes to
node/app behavior. The selftest profile alone is insufficient for an integration
claim. Keep reports from failed runs and explain their fixed case IDs rather
than removing the tests to make CI green.

To update an application target, review the replacement code and provenance,
replace its snapshot under `targets/`, then deliberately regenerate SHA256
entries in `targets/manifest.json`. Record both old and new versions in the
changelog. Never update a checksum automatically because a test reports a
mismatch. The checked-in snapshots are not modified at runtime.

Shared nodes keep the test run fast. Tests must restore network partitions and
block invalidations in `finally`, create their own Pay wallets, and stop any
server/thread they start. A failed scenario must not mutate an operator's node.
Review cleanup on partial setup, signal interruption and failing assertions.

Use the root runner, not discovery of the legacy target test directories, for
the published evidence. Target unit tests remain bundled for provenance, but
are not counted as cases in this suite. Submit a draft to the location chosen
by WAM maintainers; this contribution does not confer organization permissions.

# UNDER REVIEW — not reviewed, not endorsed

This repository was contributed by a community member and transferred into
this account. It is here so that the review can happen in the open, not
because it has passed one.

**Do not use it with real funds until this notice is replaced by one naming
what was reviewed, by whom, and on what date.**

It is not part of WAM Coin. Nothing in the main repository imports it,
nothing on the project's servers runs it, and it does not touch the chain,
the node, the pool or the treasury — checked on 2026-10-01, not assumed. The
risk it carries is not to the network. It is that a repository sitting under
this account reads as endorsed, and somebody acts on that.

## What has been read, and what has not

Read on 2026-10-01, by one person, by eye. Not an audit, and it has not been
run.

A test suite is read for one reason before any other: a test that passes while
asserting nothing is worse than a missing test, because it reports health that
was never measured. Checked first, and it is fine. There is no `assert`
anywhere in the scenarios, which looked alarming and is the opposite -- they
call `require()`, which raises, and `python -O` strips `assert` while it
cannot strip a function call. That is a deliberate choice and the right one.

**Thirty cases**, all on regtest, and these are the ones that matter to the
chain rather than to the application:

* `CORE-007` the mined coinbase pays the consensus treasury amount, in exact
  decimals
* `CORE-009` supply reporting stays under the 22,000,000 cap, and the premine
  is exactly 2,000,000
* `CORE-010` two isolated branches converge on the longer valid one
* `CORE-001` both nodes are on the pinned chain and the genesis hash matches
* `CORE-002` an unauthenticated RPC request is refused with 401
* `CORE-003` every observed peer is local and no public address is advertised
* `CORE-008` the datadir and the cookie are owner-only

And the application ones are not shallow either: `PAY-005` partial payment and
overpayment reconcile without double counting, `PAY-006` invalidating a paid
block revokes fulfilment, `PAY-009` a forged Host or cross-origin request is
refused even with a valid token, `PAY-011` an upstream error carrying a secret
cannot reach an API response or a log, `PAY-014` the payment server refuses to
create an invoice if its own genesis pin is wrong. `WT-002` holds the
watchtower to only the read-only RPC calls it declares.

**Not read:** the harness itself (`wam_it/`), the packaging scripts, and the
commit history that arrived with the transfer. **Not done:** nobody has run
it. A suite that is correct on the page and broken in its runner reports
nothing, which is the same failure one level up.

## Where the review is happening

In the discussions of the main repository:
<https://github.com/wamcoin-core-dev/wam-coin/discussions>

Anyone may take a part of it. Say which part before you start, so two people
do not read the same file while another goes unread — and say what you found
afterwards, including "I read it and found nothing". That is a result and it
is worth recording.

## Licence

MIT. The licence file shipped nested inside the version folder, where GitHub
cannot see it and a reader cannot find it, so a copy is placed at the root.
Nothing was moved or changed.

---

*The contributor's own description follows.*

_None was supplied at the repository root; see the folder inside._

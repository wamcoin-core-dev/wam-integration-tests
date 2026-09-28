# WAM Integration Tests v1.0 — Review Notes

This repository is currently pending WAM Core review.

## Areas requiring review

1. Consensus assumptions
   - Block reward schedule
   - Treasury handling
   - Halving boundaries
   - Genesis assumptions

2. RPC compatibility
   - RPC method names
   - Response field assumptions
   - Error handling

3. Mining tests
   - getblocktemplate behavior
   - stale job handling
   - block submission
   - RandomX key rotation

4. Wallet tests
   - address generation
   - transaction creation
   - confirmations
   - wallet isolation

5. Safety
   - Tests must not expose private keys
   - Tests must not send real mainnet funds
   - Destructive tests must run only on regtest/testnet

## Questions for WAM Core

- Are any current consensus assumptions incorrect?
- Are there existing integration tests that duplicate these cases?
- Which tests should eventually be moved into `wam-coin/integration/`?
- Are any RPC calls or expected responses WAM-specific?
- Are there edge cases missing from the current suite?

## Status

Experimental / Review Required
Not yet approved as an official WAM Core test suite.

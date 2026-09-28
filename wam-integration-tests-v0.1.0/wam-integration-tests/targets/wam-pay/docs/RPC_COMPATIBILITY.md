# WAM RPC compatibility record

Reviewed: 2026-09-28. This implementation targets the Bitcoin Core 28-family
wallet RPC interface described by WAM's public integration material. A live WAM
daemon was **not available** in the build environment. Fixtures and transport
tests demonstrate this client's behavior; they do not prove a specific WAM
release behaves identically.

## Sources

- [WAM integration/listing package](https://github.com/wam-coin-official/wam-coin/blob/main/docs/LISTING_PACKAGE.md)
- [WAM repository](https://github.com/wam-coin-official/wam-coin)
- [Bitcoin Core 28 listreceivedbyaddress](https://bitcoincore.org/en/doc/28.0.0/rpc/wallet/listreceivedbyaddress/)
- [Bitcoin Core 28 gettransaction](https://bitcoincore.org/en/doc/28.0.0/rpc/wallet/gettransaction/)
- [Bitcoin Core 28 getmempoolentry](https://bitcoincore.org/en/doc/28.0.0/rpc/blockchain/getmempoolentry/)

The indexed WAM package describes a Bitcoin Core v28.1 base, 8 decimals, mainnet
RPC port 9554 and testnet RPC port 19554. Mainnet genesis in that package:

```text
d8d3debea987b62a0934c3980d62bffbb6e16aa797d19891d4fcc9b9fb11d7e9
```

Its indexed launch-status prose is dated; no current network status, release
endorsement or latest-version claim is inferred from it. Fetching the separately
referenced `wamcoin-core-dev/wam-coin` v0.1.11 release did not succeed during this
build. Verify current canonical repository/release ownership with the WAM team,
and pin/review the release you operate. Do not replace a genesis mismatch with
the connected node's answer without independently verifying the correct chain.

## Explicit RPC allowlist

| Scope | Method | Arguments used / expectation |
|---|---|---|
| Node | `getblockchaininfo` | no args; chain, blocks, headers, bestblockhash, initialblockdownload |
| Node | `getblockhash` | `[0]`; expected genesis |
| Node | `getblockheader` | `[tip_hash]`; header time |
| Node | `getconnectioncount` | no args; nonzero outside regtest |
| Node | `getmempoolentry` | `[txid]`; error -5 means absent |
| Wallet | `getwalletinfo` | name, scanning=false, lastprocessedblock.hash |
| Wallet | `getnewaddress` | `[label, "bech32"]`; creates receiving address |
| Wallet | `getaddressinfo` | `[address]`; ismine or iswatchonly |
| Wallet | `listreceivedbyaddress` | `[0, false, true]`; addresses and receipt txids |
| Wallet | `gettransaction` | `[txid, true]`; confirmations, details, lastprocessedblock.hash |

Requests use JSON-RPC 2.0 with unique IDs and positional arrays. Wallet routes are
URL-encoded `/wallet/<configured-name>`; node calls use `/`. HTTP proxy environment
variables and redirects are disabled. Responses are limited to 16 MiB. RPC error
codes are preserved internally; raw node errors are not sent to browser clients.

Compatibility gates intentionally fail closed when required fields are missing,
a wallet is rescanning, a transaction has the wrong tip, or the tip changes while
scanning. Use the installed binary's `help <method>` and the acceptance procedure
to confirm behavior before calling this a tested integration.

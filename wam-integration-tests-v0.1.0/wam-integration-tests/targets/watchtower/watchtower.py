#!/usr/bin/env python3
"""WAM Watchtower v0.3 — independent WAM network, monetary, and privacy/node auditor.

Read-only tool. Talks directly to a local WAM node over Bitcoin-style JSON-RPC.

v0.1: block-finder concentration auditor.
v0.2: adds an independent monetary-integrity audit that reconstructs the WAM
      emission schedule with exact integer arithmetic, verifies the genesis
      founder reserve structure, scans coinbase claims, and checks the 5%
      treasury rule block by block.
v0.3: adds Privacy / Node Doctor: RPC exposure checks, Tor/proxy/peer visibility,
      public-address advertising, BIP324 transport visibility, and an optional
      read-only wallet address-reuse audit.

No private keys or wallet seed are required. Wallet RPC is used read-only only
when the optional address-reuse audit is enabled.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import ipaddress
import json
import os
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pathlib import Path
from typing import Any, Iterable, Sequence

APP_NAME = "WAM Watchtower"
APP_VERSION = "0.3.0"
EXPECTED_MAINNET_GENESIS = "d8d3debea987b62a0934c3980d62bffbb6e16aa797d19891d4fcc9b9fb11d7e9"
DEFAULT_RPC_URL = "http://127.0.0.1:9554/"
DEFAULT_WINDOWS = (144, 720, 5040)
DEFAULT_BATCH_SIZE = 50

# Verified in WAM's launch-day runbook. Users can override/add labels in config.json.
OFFICIAL_POOL_ADDRESS = "wam1qrulaxxlqf65madsmhqrevf467r6qmgdrxhf9yw"

# WAM monetary constants. These are deliberately duplicated here instead of
# trusting getsupplyinfo so Watchtower can independently reconstruct the schedule.
COIN = 100_000_000
MAX_SUPPLY_SAT = 22_000_000 * COIN
GENESIS_PREMINE_SAT = 2_000_000 * COIN
FOUNDER_TRANCHE_SAT = 400_000 * COIN
FOUNDER_TRANCHES = 5
INITIAL_SUBSIDY_SAT = 50 * COIN
HALVING_INTERVAL = 200_000
TREASURY_LAST_HEIGHT = 400_000
TREASURY_NUMERATOR = 5
TREASURY_DENOMINATOR = 100
EXPECTED_GENESIS_TIME = 1_789_430_400  # 2026-09-15 00:00:00 UTC
EXPECTED_FOUNDER_UNLOCK_TIMES = (
    1_820_966_400,  # 2027-09-15
    1_852_588_800,  # 2028-09-15
    1_884_124_800,  # 2029-09-15
    1_915_660_800,  # 2030-09-15
    1_947_196_800,  # 2031-09-15
)


class WatchtowerError(RuntimeError):
    pass


@dataclass
class RPCConfig:
    url: str = DEFAULT_RPC_URL
    rpc_user: str | None = None
    rpc_password: str | None = None
    cookie_file: str | None = None
    timeout: int = 30
    batch_size: int = DEFAULT_BATCH_SIZE


@dataclass
class PrivacyConfig:
    node_config_file: str | None = None
    wallet_address_reuse_audit: bool = True
    wallet: str | None = None
    show_addresses: bool = False
    reuse_threshold: int = 2


@dataclass(frozen=True)
class PrivacyFinding:
    severity: str
    check: str
    summary: str
    detail: str = ""
    remediation: str = ""


class RPCClient:
    def __init__(self, cfg: RPCConfig):
        self.cfg = cfg
        self._auth_header = self._build_auth_header()
        self._next_id = 1

    def _build_auth_header(self) -> str:
        user = self.cfg.rpc_user
        password = self.cfg.rpc_password
        if (not user or password is None) and self.cfg.cookie_file:
            cookie_path = Path(os.path.expandvars(os.path.expanduser(self.cfg.cookie_file)))
            try:
                raw = cookie_path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise WatchtowerError(f"Cannot read RPC cookie: {cookie_path}: {exc}") from exc
            if ":" not in raw:
                raise WatchtowerError(f"Invalid RPC cookie format: {cookie_path}")
            user, password = raw.split(":", 1)
        if not user or password is None:
            raise WatchtowerError(
                "RPC authentication is missing. Set rpc_user/rpc_password or cookie_file in config.json."
            )
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        return f"Basic {token}"

    def _request(self, payload: Any) -> Any:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.cfg.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": self._auth_header,
                "User-Agent": f"wam-watchtower/{APP_VERSION}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise WatchtowerError(f"RPC HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise WatchtowerError(f"Cannot reach WAM RPC at {self.cfg.url}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise WatchtowerError(f"RPC timeout talking to {self.cfg.url}") from exc

    def call(self, method: str, *params: Any) -> Any:
        ident = self._next_id
        self._next_id += 1
        response = self._request({"jsonrpc": "2.0", "id": ident, "method": method, "params": list(params)})
        if response.get("error"):
            raise WatchtowerError(f"RPC {method} failed: {response['error']}")
        return response.get("result")

    def batch(self, calls: Sequence[tuple[str, Sequence[Any]]]) -> list[Any]:
        if not calls:
            return []
        payload = []
        ids: list[int] = []
        for method, params in calls:
            ident = self._next_id
            self._next_id += 1
            ids.append(ident)
            payload.append({"jsonrpc": "2.0", "id": ident, "method": method, "params": list(params)})
        raw = self._request(payload)
        if not isinstance(raw, list):
            raise WatchtowerError("RPC batch response was not a list")
        by_id = {item.get("id"): item for item in raw}
        out = []
        for ident, (method, _) in zip(ids, calls):
            item = by_id.get(ident)
            if item is None:
                raise WatchtowerError(f"RPC batch lost response for {method} (id {ident})")
            if item.get("error"):
                raise WatchtowerError(f"RPC {method} failed: {item['error']}")
            out.append(item.get("result"))
        return out

    def for_wallet(self, wallet_name: str) -> "RPCClient":
        """Return an RPC client scoped to /wallet/<name> without changing auth."""
        parsed = urllib.parse.urlparse(self.cfg.url)
        base_path = parsed.path.rstrip("/")
        wallet_path = f"{base_path}/wallet/{urllib.parse.quote(wallet_name, safe='')}"
        url = urllib.parse.urlunparse((
            parsed.scheme, parsed.netloc, wallet_path, parsed.params, parsed.query, parsed.fragment
        ))
        cfg = RPCConfig(
            url=url,
            rpc_user=self.cfg.rpc_user,
            rpc_password=self.cfg.rpc_password,
            cookie_file=self.cfg.cookie_file,
            timeout=self.cfg.timeout,
            batch_size=self.cfg.batch_size,
        )
        return RPCClient(cfg)


@dataclass(frozen=True)
class BlockFinder:
    height: int
    block_hash: str
    finder: str
    label: str
    payout_value: float
    block_time: int | None


@dataclass(frozen=True)
class MoneyBlock:
    height: int
    block_hash: str
    expected_subsidy_sat: int
    node_subsidy_sat: int
    total_fees_sat: int
    coinbase_output_sat: int
    actual_new_issuance_sat: int
    expected_treasury_sat: int
    treasury_paid_sat: int
    treasury_compliant: bool
    subsidy_matches_schedule: bool
    overmint_sat: int
    undermint_sat: int
    treasury_address: str


@dataclass(frozen=True)
class GenesisAudit:
    block_hash: str
    block_time: int | None
    coinbase_output_sat: int
    output_count: int
    tranche_values_ok: bool
    script_lengths_ok: bool
    locktimes_found: tuple[int, ...]
    locktimes_ok: bool
    common_owner_script_tail: bool
    ok: bool


def chunks(seq: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise WatchtowerError(f"Config file does not exist: {p}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WatchtowerError(f"Cannot load config {p}: {exc}") from exc


def resolve_config(path: str) -> tuple[RPCConfig, dict[str, str], float]:
    data = load_json(path)
    rpc = data.get("rpc", {})
    cfg = RPCConfig(
        url=rpc.get("url", DEFAULT_RPC_URL),
        rpc_user=rpc.get("user"),
        rpc_password=rpc.get("password"),
        cookie_file=rpc.get("cookie_file"),
        timeout=int(rpc.get("timeout", 30)),
        batch_size=max(1, int(rpc.get("batch_size", DEFAULT_BATCH_SIZE))),
    )
    labels = {OFFICIAL_POOL_ADDRESS: "Official pool"}
    for address, label in data.get("labels", {}).items():
        if isinstance(address, str) and isinstance(label, str) and address and label:
            labels[address] = label
    threshold = float(data.get("concentration_alert_pct", 35.0))
    return cfg, labels, threshold


def resolve_privacy_config(path: str) -> PrivacyConfig:
    data = load_json(path)
    raw = data.get("privacy", {})
    if not isinstance(raw, dict):
        raw = {}
    return PrivacyConfig(
        node_config_file=raw.get("node_config_file"),
        wallet_address_reuse_audit=bool(raw.get("wallet_address_reuse_audit", True)),
        wallet=raw.get("wallet") if isinstance(raw.get("wallet"), str) and raw.get("wallet") else None,
        show_addresses=bool(raw.get("show_addresses", False)),
        reuse_threshold=max(2, int(raw.get("reuse_threshold", 2))),
    )


def wam_to_sat(value: Any) -> int:
    """Convert a JSON WAM amount to integer watoshi without binary-float math."""
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise WatchtowerError(f"Invalid WAM amount: {value!r}") from exc
    sat = (dec * COIN).quantize(Decimal("1"), rounding=ROUND_DOWN)
    return int(sat)


def sat_to_wam_text(sat: int) -> str:
    sign = "-" if sat < 0 else ""
    sat = abs(int(sat))
    whole, frac = divmod(sat, COIN)
    if frac == 0:
        return f"{sign}{whole:,}"
    return f"{sign}{whole:,}.{frac:08d}".rstrip("0")


def expected_subsidy_sat(height: int) -> int:
    """Exact WAM block subsidy for a non-genesis height."""
    if height <= 0:
        return 0
    halvings = (height - 1) // HALVING_INTERVAL
    if halvings >= 64:
        return 0
    return INITIAL_SUBSIDY_SAT >> halvings


def expected_treasury_sat(height: int) -> int:
    if height < 1 or height > TREASURY_LAST_HEIGHT:
        return 0
    subsidy = expected_subsidy_sat(height)
    return subsidy * TREASURY_NUMERATOR // TREASURY_DENOMINATOR


def scheduled_supply_sat(height: int) -> int:
    """Genesis premine + exact scheduled block subsidies through height."""
    if height <= 0:
        return GENESIS_PREMINE_SAT
    total = GENESIS_PREMINE_SAT
    remaining = int(height)
    epoch = 0
    while remaining > 0:
        subsidy = INITIAL_SUBSIDY_SAT >> epoch if epoch < 64 else 0
        if subsidy <= 0:
            break
        count = min(HALVING_INTERVAL, remaining)
        total += subsidy * count
        remaining -= count
        epoch += 1
    return total


def scheduled_treasury_min_sat(height: int) -> int:
    if height <= 0:
        return 0
    last = min(int(height), TREASURY_LAST_HEIGHT)
    total = 0
    current = 1
    while current <= last:
        epoch_end = min(last, ((current - 1) // HALVING_INTERVAL + 1) * HALVING_INTERVAL)
        count = epoch_end - current + 1
        total += expected_treasury_sat(current) * count
        current = epoch_end + 1
    return total


def spk_address(script_pub_key: dict[str, Any]) -> str | None:
    # Bitcoin Core v28 standard output format.
    addr = script_pub_key.get("address")
    if isinstance(addr, str) and addr:
        return addr
    # Compatibility with older/alternate verbose decoders.
    addrs = script_pub_key.get("addresses")
    if isinstance(addrs, list) and len(addrs) == 1 and isinstance(addrs[0], str):
        return addrs[0]
    return None


def coinbase_output_total_sat(coinbase: dict[str, Any]) -> int:
    return sum(wam_to_sat(vout.get("value", 0)) for vout in coinbase.get("vout", []))


def treasury_paid_in_coinbase_sat(coinbase: dict[str, Any], treasury_address: str) -> int:
    paid = 0
    for vout in coinbase.get("vout", []):
        if spk_address(vout.get("scriptPubKey") or {}) == treasury_address:
            paid += wam_to_sat(vout.get("value", 0))
    return paid


def decode_scriptnum(raw: bytes) -> int:
    if not raw:
        return 0
    data = bytearray(raw)
    negative = bool(data[-1] & 0x80)
    data[-1] &= 0x7F
    value = int.from_bytes(data, "little", signed=False)
    return -value if negative else value


def extract_first_pushed_scriptnum(script_hex: str) -> tuple[int | None, int]:
    """Return (scriptnum, bytes consumed by the first push) for a small direct push."""
    try:
        raw = bytes.fromhex(script_hex)
    except ValueError:
        return None, 0
    if not raw:
        return None, 0
    op = raw[0]
    if op < 1 or op > 75 or len(raw) < 1 + op:
        return None, 0
    return decode_scriptnum(raw[1 : 1 + op]), 1 + op


def audit_genesis_block(block: dict[str, Any]) -> GenesisAudit:
    txs = block.get("tx") or []
    if not txs or not isinstance(txs[0], dict):
        raise WatchtowerError("Genesis block has no decoded coinbase transaction")
    coinbase = txs[0]
    positive_vouts = [v for v in coinbase.get("vout", []) if wam_to_sat(v.get("value", 0)) > 0]
    values = [wam_to_sat(v.get("value", 0)) for v in positive_vouts]
    tranche_values_ok = len(values) == FOUNDER_TRANCHES and all(v == FOUNDER_TRANCHE_SAT for v in values)
    total_sat = sum(values)

    script_hexes = [(v.get("scriptPubKey") or {}).get("hex", "") for v in positive_vouts]
    script_lengths_ok = len(script_hexes) == FOUNDER_TRANCHES and all(
        isinstance(h, str) and len(h) == 64 for h in script_hexes
    )

    locktimes: list[int] = []
    tails: list[str] = []
    for script_hex in script_hexes:
        locktime, consumed = extract_first_pushed_scriptnum(script_hex)
        if locktime is not None:
            locktimes.append(locktime)
        # Preserve the rest after the first pushed locktime. For the published
        # bare CLTV form this should be identical across all five tranches.
        tails.append(script_hex[consumed * 2 :] if consumed else "")

    locktimes_tuple = tuple(sorted(locktimes))
    locktimes_ok = locktimes_tuple == tuple(sorted(EXPECTED_FOUNDER_UNLOCK_TIMES))
    common_tail = len(tails) == FOUNDER_TRANCHES and bool(tails[0]) and len(set(tails)) == 1
    ok = (
        total_sat == GENESIS_PREMINE_SAT
        and tranche_values_ok
        and script_lengths_ok
        and locktimes_ok
        and common_tail
    )
    return GenesisAudit(
        block_hash=str(block.get("hash", "")),
        block_time=block.get("time"),
        coinbase_output_sat=total_sat,
        output_count=len(positive_vouts),
        tranche_values_ok=tranche_values_ok,
        script_lengths_ok=script_lengths_ok,
        locktimes_found=locktimes_tuple,
        locktimes_ok=locktimes_ok,
        common_owner_script_tail=common_tail,
        ok=ok,
    )


def extract_finder(block: dict[str, Any], treasury_address: str, labels: dict[str, str]) -> tuple[str, str, float]:
    txs = block.get("tx") or []
    if not txs or not isinstance(txs[0], dict):
        raise WatchtowerError(f"Block {block.get('hash', '?')} has no decoded coinbase transaction")
    coinbase = txs[0]
    candidates: list[tuple[float, str]] = []
    fallback_scripts: list[tuple[float, str]] = []
    for vout in coinbase.get("vout", []):
        try:
            value = float(vout.get("value", 0.0))
        except (TypeError, ValueError):
            value = 0.0
        spk = vout.get("scriptPubKey") or {}
        if spk.get("type") == "nulldata" or value <= 0:
            continue
        addr = spk_address(spk)
        if addr and addr == treasury_address:
            continue
        if addr:
            candidates.append((value, addr))
        else:
            script_hex = spk.get("hex") or "unknown-script"
            fallback_scripts.append((value, f"script:{script_hex[:24]}"))
    if candidates:
        value, finder = max(candidates, key=lambda item: item[0])
    elif fallback_scripts:
        value, finder = max(fallback_scripts, key=lambda item: item[0])
    else:
        finder, value = "unknown", 0.0
    label = labels.get(finder, finder)
    return finder, label, value


def scan_blocks(client: RPCClient, start_height: int, end_height: int, treasury_address: str,
                labels: dict[str, str], progress: bool = True) -> list[BlockFinder]:
    heights = list(range(start_height, end_height + 1))
    results: list[BlockFinder] = []
    total = len(heights)
    done = 0
    for height_chunk in chunks(heights, client.cfg.batch_size):
        hashes = client.batch([("getblockhash", [h]) for h in height_chunk])
        blocks = client.batch([("getblock", [h, 2]) for h in hashes])
        for height, block_hash, block in zip(height_chunk, hashes, blocks):
            finder, label, value = extract_finder(block, treasury_address, labels)
            results.append(BlockFinder(
                height=height,
                block_hash=block_hash,
                finder=finder,
                label=label,
                payout_value=value,
                block_time=block.get("time"),
            ))
        done += len(height_chunk)
        if progress:
            print(f"\rScanning block finders: {done}/{total}", end="", flush=True)
    if progress:
        print()
    return results


def hhi(counts: Counter[str], total: int) -> float:
    if total <= 0:
        return 0.0
    return sum((count / total * 100.0) ** 2 for count in counts.values())


def summarize(rows: Sequence[BlockFinder], window: int, threshold: float) -> dict[str, Any]:
    subset = list(rows[-window:]) if window < len(rows) else list(rows)
    counts = Counter(row.finder for row in subset)
    labels: dict[str, str] = {}
    for row in subset:
        labels[row.finder] = row.label
    total = len(subset)
    ranked = []
    for finder, count in counts.most_common():
        share = 100.0 * count / total if total else 0.0
        ranked.append({
            "finder": finder,
            "label": labels.get(finder, finder),
            "blocks": count,
            "share_pct": round(share, 3),
        })
    largest = ranked[0]["share_pct"] if ranked else 0.0
    first_time = subset[0].block_time if subset else None
    last_time = subset[-1].block_time if subset else None
    avg_block_sec = None
    if first_time is not None and last_time is not None and total > 1 and last_time >= first_time:
        avg_block_sec = (last_time - first_time) / (total - 1)
    return {
        "window_blocks": total,
        "start_height": subset[0].height if subset else None,
        "end_height": subset[-1].height if subset else None,
        "distinct_finders": len(counts),
        "largest_finder_share_pct": largest,
        "above_alert_threshold": largest >= threshold,
        "alert_threshold_pct": threshold,
        "hhi": round(hhi(counts, total), 2),
        "average_block_seconds": round(avg_block_sec, 2) if avg_block_sec is not None else None,
        "finders": ranked,
    }


def print_summary(summary: dict[str, Any]) -> None:
    print(f"\nWindow: {summary['window_blocks']} blocks  "
          f"(height {summary['start_height']} → {summary['end_height']})")
    print(f"Distinct finders: {summary['distinct_finders']}  |  "
          f"Largest share: {summary['largest_finder_share_pct']:.2f}%  |  "
          f"HHI: {summary['hhi']:.2f}")
    if summary.get("average_block_seconds") is not None:
        print(f"Average observed block interval: {summary['average_block_seconds']:.2f}s")
    if summary["above_alert_threshold"]:
        print(f"NOTICE: largest finder is at/above configured {summary['alert_threshold_pct']:.1f}% threshold")
    print("\nBlocks   Share      Finder")
    print("------   --------   ------")
    for item in summary["finders"]:
        label = item["label"]
        if label == item["finder"] and len(label) > 42:
            label = label[:18] + "…" + label[-18:]
        print(f"{item['blocks']:>6}   {item['share_pct']:>7.2f}%   {label}")


def write_json(path: str, meta: dict[str, Any], summaries: list[dict[str, Any]], rows: Sequence[BlockFinder]) -> None:
    payload = {
        "tool": {"name": APP_NAME, "version": APP_VERSION},
        "generated_at_unix": int(time.time()),
        "network": meta,
        "summaries": summaries,
        "blocks": [asdict(row) for row in rows],
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_csv(path: str, rows: Sequence[BlockFinder]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["height", "block_hash", "finder", "label", "payout_value", "block_time"])
        for row in rows:
            writer.writerow([row.height, row.block_hash, row.finder, row.label, row.payout_value, row.block_time])


def doctor(client: RPCClient, verbose: bool = True) -> dict[str, Any]:
    chain = client.call("getblockchaininfo")
    genesis = client.call("getblockhash", 0)
    devfee = client.call("getdevfeeinfo")
    supply = client.call("getsupplyinfo")
    ok_chain = chain.get("chain") == "main"
    ok_genesis = genesis == EXPECTED_MAINNET_GENESIS
    synced = not chain.get("initialblockdownload", True) and chain.get("blocks") == chain.get("headers")
    if verbose:
        print(f"{APP_NAME} v{APP_VERSION}\n")
        print(f"Chain:              {chain.get('chain')} {'✓' if ok_chain else '✗ expected main'}")
        print(f"Height:             {chain.get('blocks')} / headers {chain.get('headers')}")
        print(f"Initial sync:       {chain.get('initialblockdownload')}")
        print(f"Synced:             {'YES' if synced else 'NO'}")
        print(f"Genesis:            {genesis} {'✓' if ok_genesis else '✗'}")
        print(f"Treasury address:   {devfee.get('address')}")
        print(f"Treasury active:    {devfee.get('active_now')} (through height {devfee.get('last_height')})")
        print(f"Circulating supply: {supply.get('circulating')} / {supply.get('max_supply')} WAM")
    if not ok_chain or not ok_genesis:
        raise WatchtowerError("Refusing to scan: RPC is not the expected WAM mainnet chain")
    if not synced:
        raise WatchtowerError("Refusing to scan: node is not fully synced")
    return {"chain": chain, "genesis": genesis, "devfee": devfee, "supply": supply}



def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    host = host.strip().strip("[]")
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_loopback_network(value: str) -> bool:
    raw = value.strip()
    if not raw:
        return False
    host = raw
    # rpcbind may be host:port or [ipv6]:port. rpcallowip may be CIDR.
    if raw.startswith("[") and "]" in raw:
        host = raw[1:raw.index("]")]
    elif "/" not in raw and raw.count(":") == 1:
        left, right = raw.rsplit(":", 1)
        if right.isdigit():
            host = left
    try:
        if "/" in host:
            return ipaddress.ip_network(host, strict=False).is_loopback
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def is_broad_rpc_allow(value: str) -> bool:
    raw = value.strip()
    try:
        net = ipaddress.ip_network(raw, strict=False)
        return net.prefixlen == 0 or not net.is_loopback
    except ValueError:
        return not is_loopback_network(raw)


def parse_node_config(path: str | Path) -> dict[str, list[str]]:
    """Parse enough of Bitcoin-style conf to audit network/privacy settings.

    Top-level values plus [main] values are considered effective for mainnet.
    Secret values are never returned by the privacy report; this parser is kept
    generic for tests and local evaluation only.
    """
    p = Path(os.path.expandvars(os.path.expanduser(str(path))))
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise WatchtowerError(f"Cannot read node config {p}: {exc}") from exc
    sections: dict[str, dict[str, list[str]]] = {"": {}}
    current = ""
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip().lower()
            sections.setdefault(current, {})
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lower().lstrip("-")
        value = value.strip()
        sections.setdefault(current, {}).setdefault(key, []).append(value)
    effective: dict[str, list[str]] = {}
    for sec in ("", "main"):
        for key, values in sections.get(sec, {}).items():
            effective[key] = list(values)
    return effective


def auto_detect_node_config(preferred: str | None = None) -> Path | None:
    candidates: list[Path] = []
    if preferred:
        candidates.append(Path(os.path.expandvars(os.path.expanduser(preferred))))
    env_conf = os.environ.get("WAM_CONF")
    if env_conf:
        candidates.append(Path(os.path.expandvars(os.path.expanduser(env_conf))))
    home = Path.home()
    candidates.extend([home / ".wam" / "wam.conf", home / ".wam-mainnet" / "wam.conf"])
    for env_name in ("APPDATA", "LOCALAPPDATA"):
        base = os.environ.get(env_name)
        if base:
            b = Path(base)
            candidates.extend([b / "WAM" / "wam.conf", b / "Wam" / "wam.conf", b / "WAMCoin" / "wam.conf"])
    if os.name == "nt":
        candidates.extend([Path(r"C:\wam\wam.conf"), Path(r"C:\wam\data\wam.conf"), Path(r"C:\wam\mainnet\wam.conf")])
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return candidate
    return None


def config_last(conf: dict[str, list[str]], key: str, default: str | None = None) -> str | None:
    values = conf.get(key.lower()) or []
    return values[-1] if values else default


def config_bool(conf: dict[str, list[str]], key: str, default: bool) -> bool:
    raw = config_last(conf, key)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _public_address(address: str) -> bool:
    raw = address.strip().strip("[]")
    if raw.endswith(".onion") or raw.endswith(".i2p"):
        return False
    # Strip :port from IPv4; IPv6 from Core is normally address only in localaddresses.
    if raw.count(":") == 1:
        left, right = raw.rsplit(":", 1)
        if right.isdigit():
            raw = left
    try:
        return ipaddress.ip_address(raw).is_global
    except ValueError:
        return False


def _address_id(address: str, show: bool) -> str:
    if show:
        return address
    return "addr#" + hashlib.sha256(address.encode("utf-8")).hexdigest()[:12]


def audit_wallet_reuse_rows(rows: Sequence[dict[str, Any]], threshold: int = 2,
                            show_addresses: bool = False) -> dict[str, Any]:
    used = 0
    reused: list[dict[str, Any]] = []
    for item in rows:
        address = item.get("address")
        txids = item.get("txids") or []
        if not isinstance(address, str) or not address:
            continue
        tx_count = len(set(x for x in txids if isinstance(x, str)))
        if tx_count <= 0:
            continue
        used += 1
        if tx_count >= threshold:
            reused.append({"address": _address_id(address, show_addresses), "received_tx_count": tx_count})
    reused.sort(key=lambda x: x["received_tx_count"], reverse=True)
    return {
        "used_receiving_addresses": used,
        "reused_receiving_addresses": len(reused),
        "reuse_threshold_transactions": threshold,
        "max_receive_transactions_on_one_address": reused[0]["received_tx_count"] if reused else 0,
        "examples": reused[:20],
    }


def assess_privacy(client: RPCClient, rpc_cfg: RPCConfig, privacy_cfg: PrivacyConfig) -> dict[str, Any]:
    findings: list[PrivacyFinding] = []

    parsed_rpc = urllib.parse.urlparse(rpc_cfg.url)
    rpc_host = parsed_rpc.hostname
    rpc_local = is_loopback_host(rpc_host)
    findings.append(PrivacyFinding(
        "PASS" if rpc_local else "HIGH",
        "rpc_endpoint",
        "Watchtower is using loopback RPC" if rpc_local else "Watchtower is using a non-loopback RPC endpoint",
        f"RPC host: {rpc_host or 'unknown'}",
        "Keep WAM RPC bound to 127.0.0.1/::1 and use it locally." if not rpc_local else "",
    ))

    config_path = auto_detect_node_config(privacy_cfg.node_config_file)
    conf: dict[str, list[str]] = {}
    config_meta: dict[str, Any] = {"found": bool(config_path), "source": "not found"}
    if config_path:
        conf = parse_node_config(config_path)
        config_meta = {"found": True, "source": "configured" if privacy_cfg.node_config_file else "auto-detected",
                       "filename": config_path.name}
        binds = conf.get("rpcbind", [])
        bind_safe = not binds or all(is_loopback_network(v) for v in binds)
        findings.append(PrivacyFinding(
            "PASS" if bind_safe else "HIGH",
            "rpc_bind",
            "RPC bind is loopback-only" if bind_safe else "RPC bind includes a non-loopback interface",
            "Default loopback bind" if not binds else ", ".join(binds),
            "Set rpcbind=127.0.0.1 (and optionally ::1) in the [main] section." if not bind_safe else "",
        ))
        allows = conf.get("rpcallowip", [])
        allow_safe = not allows or all(not is_broad_rpc_allow(v) for v in allows)
        findings.append(PrivacyFinding(
            "PASS" if allow_safe else "WARN",
            "rpc_allowlist",
            "RPC allowlist is loopback-only/default" if allow_safe else "RPC allowlist permits non-loopback clients",
            "Default loopback policy" if not allows else ", ".join(allows),
            "Restrict rpcallowip to loopback unless remote RPC is intentionally protected." if not allow_safe else "",
        ))
        try:
            mode = stat.S_IMODE(config_path.stat().st_mode)
            if os.name != "nt":
                too_open = bool(mode & (stat.S_IRWXG | stat.S_IRWXO))
                findings.append(PrivacyFinding(
                    "WARN" if too_open else "PASS",
                    "config_permissions",
                    "Node config is group/world accessible" if too_open else "Node config permissions are restrictive",
                    f"POSIX mode: {oct(mode)}",
                    "Use chmod 600 on wam.conf because it can contain RPC credentials." if too_open else "",
                ))
        except OSError:
            pass
    else:
        findings.append(PrivacyFinding(
            "INFO", "node_config", "wam.conf was not found automatically",
            "RPC-level checks still work, but bind/allowlist/proxy settings cannot be audited from disk.",
            "Set privacy.node_config_file in config.json if wam.conf is in a custom datadir.",
        ))

    network = client.call("getnetworkinfo")
    peers = client.call("getpeerinfo")
    networks = {str(n.get("name")): n for n in network.get("networks", []) if isinstance(n, dict)}
    onion = networks.get("onion", {})
    onion_proxy = str(onion.get("proxy") or "")
    onion_reachable = bool(onion.get("reachable"))
    tor_configured = bool(onion_proxy) or bool(config_last(conf, "proxy")) or bool(config_last(conf, "onion"))
    if tor_configured and onion_reachable:
        findings.append(PrivacyFinding("PASS", "tor_proxy", "Tor/onion networking is configured and reachable",
                                       f"Onion proxy: {onion_proxy or 'configured in wam.conf'}"))
    elif tor_configured:
        findings.append(PrivacyFinding("WARN", "tor_proxy", "Tor/proxy is configured but onion is not currently reachable",
                                       f"Onion proxy: {onion_proxy or 'configured in wam.conf'}",
                                       "Check the Tor service/proxy and WAM network settings."))
    else:
        findings.append(PrivacyFinding("WARN", "tor_proxy", "No Tor/onion proxy is visible",
                                       "Outbound transaction relay may use clearnet peers.",
                                       "If network-level privacy matters, configure Tor/proxy and verify onion reachability."))

    peer_network_counts = Counter(str(p.get("network") or "unknown") for p in peers if isinstance(p, dict))
    onion_peers = peer_network_counts.get("onion", 0)
    findings.append(PrivacyFinding(
        "PASS" if onion_peers > 0 else "INFO",
        "onion_peers",
        f"Connected onion peers: {onion_peers}" if onion_peers else "No current onion peers",
        ", ".join(f"{k}={v}" for k, v in sorted(peer_network_counts.items())) or "No peers",
        "Having no onion peer at one instant is not itself a failure; use Tor if you want transaction relay to avoid direct clearnet exposure." if not onion_peers else "",
    ))

    v2_count = sum(1 for p in peers if isinstance(p, dict) and p.get("transport_protocol_type") == "v2")
    v1_count = sum(1 for p in peers if isinstance(p, dict) and p.get("transport_protocol_type") == "v1")
    findings.append(PrivacyFinding(
        "PASS" if v2_count > 0 else "INFO",
        "p2p_transport",
        f"BIP324/v2 peers: {v2_count}" if v2_count else "No BIP324/v2 peers observed",
        f"v2={v2_count}, v1={v1_count}, total={len(peers)}",
        "v2 transport encrypts P2P links but is not a substitute for Tor." if v2_count == 0 else "",
    ))

    localaddresses = network.get("localaddresses") or []
    public_advertised = [a.get("address") for a in localaddresses if isinstance(a, dict) and isinstance(a.get("address"), str) and _public_address(a["address"])]
    findings.append(PrivacyFinding(
        "INFO" if public_advertised else "PASS",
        "public_p2p_identity",
        f"Node advertises {len(public_advertised)} public IP address(es)" if public_advertised else "No public IP advertised in getnetworkinfo",
        "Public listening is normal for a routing node, but it links this node to an IP address." if public_advertised else "",
        "If operator privacy is more important than accepting clearnet inbound peers, review listen/discover/Tor settings." if public_advertised else "",
    ))

    con_in = network.get("connections_in")
    con_out = network.get("connections_out")
    network_meta = {
        "connections": network.get("connections"),
        "connections_in": con_in,
        "connections_out": con_out,
        "peer_network_counts": dict(peer_network_counts),
        "onion_reachable": onion_reachable,
        "onion_proxy_configured": bool(onion_proxy),
        "bip324_v2_peers": v2_count,
        "bip324_v1_peers": v1_count,
        "public_advertised_address_count": len(public_advertised),
        "onlynet": conf.get("onlynet", []),
        "listen": config_bool(conf, "listen", True) if conf else None,
        "discover": config_bool(conf, "discover", True) if conf else None,
    }

    wallet_meta: dict[str, Any] = {"enabled": privacy_cfg.wallet_address_reuse_audit, "wallets": []}
    if privacy_cfg.wallet_address_reuse_audit:
        try:
            wallets = client.call("listwallets")
        except WatchtowerError as exc:
            findings.append(PrivacyFinding("SKIP", "address_reuse", "Wallet address-reuse audit unavailable",
                                           str(exc)))
            wallets = []
        if privacy_cfg.wallet:
            wallets = [privacy_cfg.wallet] if privacy_cfg.wallet in wallets else []
            if not wallets:
                findings.append(PrivacyFinding("SKIP", "wallet_selection", "Configured wallet is not loaded",
                                               "Load the wallet or clear privacy.wallet to audit all loaded wallets."))
        for wallet_name in wallets:
            wc = client.for_wallet(wallet_name)
            try:
                info = wc.call("getwalletinfo")
                received = wc.call("listreceivedbyaddress", 0, False, True)
                reuse = audit_wallet_reuse_rows(received if isinstance(received, list) else [],
                                                privacy_cfg.reuse_threshold, privacy_cfg.show_addresses)
                wallet_result = {
                    "wallet_id": "wallet#" + hashlib.sha256(wallet_name.encode()).hexdigest()[:10],
                    "descriptors": info.get("descriptors"),
                    "private_keys_enabled": info.get("private_keys_enabled"),
                    "avoid_reuse_flag": info.get("avoid_reuse"),
                    **reuse,
                }
                wallet_meta["wallets"].append(wallet_result)
                if reuse["reused_receiving_addresses"] > 0:
                    findings.append(PrivacyFinding(
                        "WARN", "address_reuse",
                        f"Receiving-address reuse detected in {wallet_result['wallet_id']}",
                        f"{reuse['reused_receiving_addresses']} reused of {reuse['used_receiving_addresses']} used receiving addresses; max {reuse['max_receive_transactions_on_one_address']} receive transactions on one address.",
                        "Generate a fresh receiving address for each payment. Mining/pool payout addresses may intentionally be reused, but remain linkable on-chain.",
                    ))
                else:
                    findings.append(PrivacyFinding(
                        "PASS", "address_reuse",
                        f"No receiving-address reuse detected in {wallet_result['wallet_id']}",
                        f"Checked {reuse['used_receiving_addresses']} used receiving addresses.",
                    ))
            except WatchtowerError as exc:
                findings.append(PrivacyFinding("SKIP", "address_reuse", "Could not audit one loaded wallet", str(exc)))
        if not wallets and not privacy_cfg.wallet:
            findings.append(PrivacyFinding("SKIP", "address_reuse", "No loaded wallet to audit",
                                           "Node/network privacy checks still completed."))
    else:
        findings.append(PrivacyFinding("SKIP", "address_reuse", "Wallet address-reuse audit disabled"))

    severity_order = {"HIGH": 0, "WARN": 1, "PASS": 2, "INFO": 3, "SKIP": 4}
    findings.sort(key=lambda f: (severity_order.get(f.severity, 9), f.check))
    summary_counts = Counter(f.severity for f in findings)
    return {
        "rpc": {"url_host": rpc_host, "loopback": rpc_local},
        "config": config_meta,
        "network": network_meta,
        "wallet": wallet_meta,
        "findings": [asdict(f) for f in findings],
        "summary": {
            "high": summary_counts.get("HIGH", 0),
            "warn": summary_counts.get("WARN", 0),
            "pass": summary_counts.get("PASS", 0),
            "info": summary_counts.get("INFO", 0),
            "skip": summary_counts.get("SKIP", 0),
        },
        "note": "This is an exposure/configuration audit, not an anonymity guarantee. Tor, CoinJoin and address hygiene address different threat models.",
    }


def print_privacy_report(report: dict[str, Any]) -> None:
    print(f"{APP_NAME} v{APP_VERSION} — Privacy / Node Doctor")
    print("=" * 58)
    counts = report["summary"]
    print(f"Findings: HIGH {counts['high']} | WARN {counts['warn']} | PASS {counts['pass']} | INFO {counts['info']} | SKIP {counts['skip']}")
    print()
    for item in report["findings"]:
        sev = item["severity"]
        print(f"[{sev:<4}] {item['check']}: {item['summary']}")
        if item.get("detail"):
            print(f"       {item['detail']}")
        if item.get("remediation"):
            print(f"       -> {item['remediation']}")
    print("\nNetwork snapshot")
    print("----------------")
    n = report["network"]
    print(f"Connections:          {n.get('connections')} (in {n.get('connections_in')}, out {n.get('connections_out')})")
    print(f"Peer networks:        {n.get('peer_network_counts')}")
    print(f"Onion reachable:      {n.get('onion_reachable')}")
    print(f"BIP324 v2 peers:      {n.get('bip324_v2_peers')}")
    print(f"Public IP advertised: {n.get('public_advertised_address_count')}")
    print("\nPRIVACY DOCTOR:       " + ("ACTION NEEDED" if counts["high"] else "REVIEW WARNINGS" if counts["warn"] else "NO HIGH-RISK FINDINGS"))
    print("Note: this tool does not claim that a node or wallet is anonymous.")


def write_privacy_json(path: str, meta: dict[str, Any], report: dict[str, Any]) -> None:
    payload = {
        "tool": {"name": APP_NAME, "version": APP_VERSION},
        "generated_at_unix": int(time.time()),
        "network": {"chain": meta["chain"].get("chain"), "height": meta["chain"].get("blocks"), "genesis": meta["genesis"]},
        "privacy": report,
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def cmd_privacy(args: argparse.Namespace) -> int:
    rpc_cfg, _, _ = resolve_config(args.config)
    privacy_cfg = resolve_privacy_config(args.config)
    if args.node_config_file:
        privacy_cfg.node_config_file = args.node_config_file
    if args.no_wallet:
        privacy_cfg.wallet_address_reuse_audit = False
    if args.wallet:
        privacy_cfg.wallet = args.wallet
    if args.show_addresses:
        privacy_cfg.show_addresses = True
    client = RPCClient(rpc_cfg)
    meta = doctor(client, verbose=False)
    report = assess_privacy(client, rpc_cfg, privacy_cfg)
    print_privacy_report(report)
    if args.json_out:
        write_privacy_json(args.json_out, meta, report)
        print(f"\nPrivacy JSON: {args.json_out}")
    if args.fail_on_high and report["summary"]["high"]:
        return 4
    return 0


def get_genesis_audit(client: RPCClient) -> GenesisAudit:
    genesis_hash = client.call("getblockhash", 0)
    block = client.call("getblock", genesis_hash, 2)
    return audit_genesis_block(block)


def analyze_money_block(height: int, block_hash: str, coinbase: dict[str, Any], stats: dict[str, Any],
                        treasury_address: str) -> MoneyBlock:
    expected_subsidy = expected_subsidy_sat(height)
    node_subsidy_raw = stats.get("subsidy")
    totalfee_raw = stats.get("totalfee")
    if not isinstance(node_subsidy_raw, int) or not isinstance(totalfee_raw, int):
        raise WatchtowerError(
            "getblockstats did not return integer 'subsidy'/'totalfee' fields. "
            "A Bitcoin Core v28-compatible WAM node is required for the full monetary audit."
        )
    node_subsidy = int(node_subsidy_raw)
    total_fees = int(totalfee_raw)
    coinbase_total = coinbase_output_total_sat(coinbase)
    actual_new = coinbase_total - total_fees
    expected_treasury = expected_treasury_sat(height)
    treasury_paid = treasury_paid_in_coinbase_sat(coinbase, treasury_address)
    treasury_compliant = expected_treasury == 0 or treasury_paid >= expected_treasury
    overmint = max(0, actual_new - expected_subsidy)
    undermint = max(0, expected_subsidy - actual_new)
    return MoneyBlock(
        height=height,
        block_hash=block_hash,
        expected_subsidy_sat=expected_subsidy,
        node_subsidy_sat=node_subsidy,
        total_fees_sat=total_fees,
        coinbase_output_sat=coinbase_total,
        actual_new_issuance_sat=actual_new,
        expected_treasury_sat=expected_treasury,
        treasury_paid_sat=treasury_paid,
        treasury_compliant=treasury_compliant,
        subsidy_matches_schedule=(node_subsidy == expected_subsidy),
        overmint_sat=overmint,
        undermint_sat=undermint,
        treasury_address=treasury_address,
    )


def scan_money_blocks(client: RPCClient, start_height: int, end_height: int, treasury_address: str,
                      progress: bool = True, cache_path: str | None = None) -> list[MoneyBlock]:
    if end_height < start_height:
        return []
    heights = list(range(start_height, end_height + 1))
    out: list[MoneyBlock] = []
    done = 0
    total = len(heights)
    cache_fh = open(cache_path, "a", encoding="utf-8") if cache_path else None
    try:
        for height_chunk in chunks(heights, client.cfg.batch_size):
            hashes = client.batch([("getblockhash", [h]) for h in height_chunk])
            # Verbosity 1 is enough to get the coinbase txid without transferring every decoded tx.
            blocks = client.batch([("getblock", [h, 1]) for h in hashes])
            coinbase_txids: list[str] = []
            for height, block in zip(height_chunk, blocks):
                txids = block.get("tx") or []
                if not txids or not isinstance(txids[0], str):
                    raise WatchtowerError(f"Block {height} did not expose a coinbase txid at verbosity 1")
                coinbase_txids.append(txids[0])
            coinbases = client.batch([
                ("getrawtransaction", [txid, True, block_hash])
                for txid, block_hash in zip(coinbase_txids, hashes)
            ])
            stats_rows = client.batch([
                ("getblockstats", [block_hash, ["subsidy", "totalfee"]]) for block_hash in hashes
            ])
            for height, block_hash, coinbase, stats in zip(height_chunk, hashes, coinbases, stats_rows):
                row = analyze_money_block(height, block_hash, coinbase, stats, treasury_address)
                out.append(row)
                if cache_fh:
                    cache_fh.write(json.dumps(asdict(row), separators=(",", ":")) + "\n")
            if cache_fh:
                cache_fh.flush()
            done += len(height_chunk)
            if progress:
                print(f"\rAuditing monetary blocks: {done}/{total}", end="", flush=True)
    finally:
        if cache_fh:
            cache_fh.close()
    if progress:
        print()
    return out


def load_money_cache(path: str, treasury_address: str, tip: int, client: RPCClient) -> list[MoneyBlock]:
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return []
    rows: list[MoneyBlock] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                row = MoneyBlock(**obj)
            except (json.JSONDecodeError, TypeError):
                # Ignore a torn final line from an interrupted append.
                continue
            if row.height < 1 or row.height > tip:
                continue
            if row.treasury_address != treasury_address:
                return []
            rows.append(row)
    except OSError:
        return []
    if not rows:
        return []
    rows.sort(key=lambda r: r.height)
    # Cache must be contiguous from block 1; otherwise an "actual supply" total would be false.
    for expected_height, row in enumerate(rows, start=1):
        if row.height != expected_height:
            return []
    # Validate the most recent cached hash against the live chain. If it differs,
    # discard the cache rather than trying to be clever around a reorg.
    last = rows[-1]
    live_hash = client.call("getblockhash", last.height)
    if live_hash != last.block_hash:
        return []
    return rows


def reset_cache(path: str) -> None:
    p = Path(path)
    if p.exists():
        stale = p.with_suffix(p.suffix + f".stale-{int(time.time())}")
        try:
            p.replace(stale)
            print(f"Cache did not match the live chain; moved old cache to {stale}")
        except OSError:
            try:
                p.unlink()
            except OSError:
                pass


def rpc_supply_value_sat(supply: dict[str, Any], key: str) -> int | None:
    value = supply.get(key)
    if value is None:
        return None
    try:
        return wam_to_sat(value)
    except WatchtowerError:
        return None


def monetary_summary(tip: int, genesis: GenesisAudit, rows: Sequence[MoneyBlock],
                     rpc_supply: dict[str, Any]) -> dict[str, Any]:
    scheduled = scheduled_supply_sat(tip)
    actual = genesis.coinbase_output_sat + sum(r.actual_new_issuance_sat for r in rows)
    required_treasury = scheduled_treasury_min_sat(tip)
    actual_treasury_required_window = sum(
        r.treasury_paid_sat for r in rows if 1 <= r.height <= TREASURY_LAST_HEIGHT
    )
    violations = [r for r in rows if not r.treasury_compliant]
    schedule_mismatch = [r for r in rows if not r.subsidy_matches_schedule]
    overmint = [r for r in rows if r.overmint_sat > 0]
    undermint_total = sum(r.undermint_sat for r in rows)
    overmint_total = sum(r.overmint_sat for r in rows)

    rpc_circulating = rpc_supply_value_sat(rpc_supply, "circulating")
    rpc_max = rpc_supply_value_sat(rpc_supply, "max_supply")
    rpc_founder = rpc_supply.get("founder_vesting") if isinstance(rpc_supply.get("founder_vesting"), dict) else {}
    rpc_locked = rpc_supply_value_sat(rpc_founder, "locked") if rpc_founder else None
    rpc_unlocked = rpc_supply_value_sat(rpc_founder, "unlocked") if rpc_founder else None

    return {
        "height": tip,
        "scheduled_supply_sat": scheduled,
        "actual_minted_supply_sat": actual,
        "supply_difference_sat": actual - scheduled,
        "hard_cap_sat": MAX_SUPPLY_SAT,
        "hard_cap_respected": actual <= MAX_SUPPLY_SAT,
        "genesis_ok": genesis.ok,
        "blocks_audited": len(rows),
        "treasury_required_min_sat": required_treasury,
        "treasury_paid_in_required_window_sat": actual_treasury_required_window,
        "treasury_noncompliant_blocks": len(violations),
        "subsidy_schedule_mismatch_blocks": len(schedule_mismatch),
        "overmint_blocks": len(overmint),
        "overmint_sat": overmint_total,
        "undermint_sat": undermint_total,
        "rpc_circulating_sat": rpc_circulating,
        "rpc_circulating_matches_schedule": rpc_circulating == scheduled if rpc_circulating is not None else None,
        "rpc_max_supply_sat": rpc_max,
        "rpc_max_supply_matches_constant": rpc_max == MAX_SUPPLY_SAT if rpc_max is not None else None,
        "rpc_founder_locked_sat": rpc_locked,
        "rpc_founder_unlocked_sat": rpc_unlocked,
        "ok": (
            genesis.ok
            and len(rows) == tip
            and actual <= MAX_SUPPLY_SAT
            and overmint_total == 0
            and not violations
            and not schedule_mismatch
        ),
        "violating_heights": [r.height for r in violations[:100]],
        "overmint_heights": [r.height for r in overmint[:100]],
        "schedule_mismatch_heights": [r.height for r in schedule_mismatch[:100]],
    }


def print_genesis_audit(genesis: GenesisAudit) -> None:
    print("\nGenesis founder reserve")
    print("-----------------------")
    print(f"Premine outputs:       {genesis.output_count} (expected 5)")
    print(f"Premine total:         {sat_to_wam_text(genesis.coinbase_output_sat)} WAM")
    print(f"5 × 400,000 WAM:       {'PASS' if genesis.tranche_values_ok else 'FAIL'}")
    print(f"32-byte lock scripts:  {'PASS' if genesis.script_lengths_ok else 'FAIL'}")
    print(f"Five CLTV dates:       {'PASS' if genesis.locktimes_ok else 'FAIL'}")
    if genesis.locktimes_found:
        print(f"Lock timestamps:       {', '.join(str(x) for x in genesis.locktimes_found)}")
    print(f"Common owner tail:     {'PASS' if genesis.common_owner_script_tail else 'FAIL'}")
    print(f"Genesis reserve audit: {'PASS' if genesis.ok else 'FAIL'}")


def print_monetary_summary(summary: dict[str, Any]) -> None:
    print("\nMonetary integrity")
    print("------------------")
    print(f"Height audited:        {summary['height']:,}")
    print(f"Blocks audited:        {summary['blocks_audited']:,}")
    print(f"Scheduled supply:      {sat_to_wam_text(summary['scheduled_supply_sat'])} WAM")
    print(f"Actual minted supply:  {sat_to_wam_text(summary['actual_minted_supply_sat'])} WAM")
    diff = summary["supply_difference_sat"]
    print(f"Difference:            {sat_to_wam_text(diff)} WAM")
    print(f"22M hard cap:          {'PASS' if summary['hard_cap_respected'] else 'FAIL'}")
    print(f"Overmint blocks:       {summary['overmint_blocks']}")
    print(f"Underclaimed subsidy:  {sat_to_wam_text(summary['undermint_sat'])} WAM")
    print(f"Subsidy mismatches:    {summary['subsidy_schedule_mismatch_blocks']}")
    print(f"Treasury required min: {sat_to_wam_text(summary['treasury_required_min_sat'])} WAM")
    print(f"Treasury actually paid:{sat_to_wam_text(summary['treasury_paid_in_required_window_sat']):>15} WAM")
    print(f"Treasury violations:   {summary['treasury_noncompliant_blocks']}")
    if summary.get("rpc_circulating_sat") is not None:
        print(f"Node getsupplyinfo:    {sat_to_wam_text(summary['rpc_circulating_sat'])} WAM "
              f"({'MATCH' if summary['rpc_circulating_matches_schedule'] else 'DIFF'})")
    print(f"\nMONETARY AUDIT:        {'PASS' if summary['ok'] else 'FAIL'}")


def write_money_json(path: str, meta: dict[str, Any], genesis: GenesisAudit,
                     summary: dict[str, Any], rows: Sequence[MoneyBlock]) -> None:
    bad_rows = [
        asdict(r) for r in rows
        if r.overmint_sat > 0 or not r.treasury_compliant or not r.subsidy_matches_schedule
    ]
    payload = {
        "tool": {"name": APP_NAME, "version": APP_VERSION},
        "generated_at_unix": int(time.time()),
        "network": meta,
        "genesis": asdict(genesis),
        "summary": summary,
        "violations": bad_rows,
        "method": {
            "schedule": "independent integer reconstruction from published WAM constants",
            "actual_issuance": "coinbase output total minus getblockstats.totalfee",
            "treasury": "direct coinbase output match against treasury address returned by getdevfeeinfo",
            "note": "fees are transfers, not new issuance; underclaimed subsidy permanently reduces actual minted supply",
        },
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_money_csv(path: str, rows: Sequence[MoneyBlock]) -> None:
    fields = [f.name for f in MoneyBlock.__dataclass_fields__.values()]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def cmd_scan(args: argparse.Namespace) -> int:
    rpc_cfg, labels, threshold = resolve_config(args.config)
    client = RPCClient(rpc_cfg)
    meta = doctor(client)
    tip = int(meta["chain"]["blocks"])
    windows = sorted(set(int(w) for w in args.windows if int(w) > 0))
    if not windows:
        raise WatchtowerError("At least one positive scan window is required")
    max_window = min(max(windows), tip) if tip > 0 else 0
    if max_window <= 0:
        raise WatchtowerError("Chain has no non-genesis blocks to scan")
    start = tip - max_window + 1
    treasury_address = meta["devfee"].get("address")
    if not treasury_address:
        raise WatchtowerError("getdevfeeinfo did not return the treasury address")
    print(f"\nScanning height {start} → {tip} ({max_window} blocks)…")
    rows = scan_blocks(client, start, tip, treasury_address, labels, progress=not args.quiet)
    summaries = [summarize(rows, min(w, max_window), threshold) for w in windows]
    for summary in summaries:
        print_summary(summary)
    if args.json_out:
        write_json(args.json_out, {
            "chain": meta["chain"].get("chain"),
            "height": tip,
            "genesis": meta["genesis"],
            "treasury_address": treasury_address,
        }, summaries, rows)
        print(f"\nJSON report: {args.json_out}")
    if args.csv_out:
        write_csv(args.csv_out, rows)
        print(f"CSV blocks:  {args.csv_out}")
    return 0


def cmd_money(args: argparse.Namespace) -> int:
    rpc_cfg, _, _ = resolve_config(args.config)
    client = RPCClient(rpc_cfg)
    meta = doctor(client)
    tip = int(meta["chain"]["blocks"])
    treasury_address = meta["devfee"].get("address")
    if not treasury_address:
        raise WatchtowerError("getdevfeeinfo did not return the treasury address")

    genesis = get_genesis_audit(client)
    print_genesis_audit(genesis)

    rows: list[MoneyBlock] = []
    cache_path = None if args.no_cache else args.cache
    if cache_path:
        rows = load_money_cache(cache_path, treasury_address, tip, client)
        if rows:
            print(f"\nLoaded {len(rows):,} verified monetary rows from cache.")
        elif Path(cache_path).exists() and Path(cache_path).stat().st_size:
            reset_cache(cache_path)

    start = len(rows) + 1
    if start <= tip:
        print(f"\nAuditing monetary rules from height {start:,} → {tip:,}…")
        new_rows = scan_money_blocks(
            client, start, tip, treasury_address,
            progress=not args.quiet,
            cache_path=cache_path,
        )
        rows.extend(new_rows)
    else:
        print("\nMonetary cache already reaches the current tip.")

    if len(rows) != tip:
        raise WatchtowerError(
            f"Monetary audit is incomplete: have {len(rows)} block rows for tip {tip}. "
            "Delete the cache and re-run."
        )

    summary = monetary_summary(tip, genesis, rows, meta["supply"])
    print_monetary_summary(summary)

    report_meta = {
        "chain": meta["chain"].get("chain"),
        "height": tip,
        "genesis": meta["genesis"],
        "treasury_address": treasury_address,
    }
    if args.json_out:
        write_money_json(args.json_out, report_meta, genesis, summary, rows)
        print(f"\nMonetary JSON: {args.json_out}")
    if args.csv_out:
        write_money_csv(args.csv_out, rows)
        print(f"Monetary CSV:  {args.csv_out}")
    return 0 if summary["ok"] else 3


def cmd_doctor(args: argparse.Namespace) -> int:
    rpc_cfg, _, _ = resolve_config(args.config)
    doctor(RPCClient(rpc_cfg))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="watchtower.py",
        description="Independent WAM decentralization, monetary-integrity and privacy/node auditor (read-only).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_doc = sub.add_parser("doctor", help="verify RPC, mainnet genesis, sync, treasury and supply")
    p_doc.add_argument("--config", default="config.json", help="config file (default: config.json)")
    p_doc.set_defaults(func=cmd_doctor)

    p_scan = sub.add_parser("scan", help="scan recent blocks and measure finder concentration")
    p_scan.add_argument("--config", default="config.json", help="config file (default: config.json)")
    p_scan.add_argument("--windows", nargs="+", type=int, default=list(DEFAULT_WINDOWS),
                        help="block windows, e.g. 144 720 5040")
    p_scan.add_argument("--json-out", default="watchtower-report.json", help="write full JSON report")
    p_scan.add_argument("--csv-out", default="watchtower-blocks.csv", help="write per-block CSV")
    p_scan.add_argument("--quiet", action="store_true", help="hide scan progress")
    p_scan.set_defaults(func=cmd_scan)

    p_money = sub.add_parser("money", help="audit emission, genesis reserve and treasury rules through chain tip")
    p_money.add_argument("--config", default="config.json", help="config file (default: config.json)")
    p_money.add_argument("--json-out", default="watchtower-money.json", help="write monetary audit JSON")
    p_money.add_argument("--csv-out", default="watchtower-money-blocks.csv", help="write per-block monetary CSV")
    p_money.add_argument("--cache", default="watchtower-money-cache.jsonl",
                         help="incremental verified cache (default: watchtower-money-cache.jsonl)")
    p_money.add_argument("--no-cache", action="store_true", help="ignore and do not write monetary cache")
    p_money.add_argument("--quiet", action="store_true", help="hide monetary scan progress")
    p_money.set_defaults(func=cmd_money)

    p_priv = sub.add_parser("privacy", help="audit RPC exposure, Tor/proxy, peer privacy and optional address reuse")
    p_priv.add_argument("--config", default="config.json", help="config file (default: config.json)")
    p_priv.add_argument("--json-out", default="watchtower-privacy.json", help="write privacy/node audit JSON")
    p_priv.add_argument("--node-config-file", default=None, help="explicit path to wam.conf for bind/proxy checks")
    p_priv.add_argument("--wallet", default=None, help="audit one loaded wallet by name")
    p_priv.add_argument("--no-wallet", action="store_true", help="skip wallet address-reuse audit")
    p_priv.add_argument("--show-addresses", action="store_true", help="include full reused receiving addresses in report (off by default)")
    p_priv.add_argument("--fail-on-high", action="store_true", help="exit 4 when a HIGH finding exists")
    p_priv.set_defaults(func=cmd_privacy)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except WatchtowerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

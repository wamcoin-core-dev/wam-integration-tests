"""Strict startup validation. Secrets are never returned by the API."""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from src.errors import ValidationError


@dataclass(frozen=True)
class Config:
    mode: str = "demo"
    host: str = "127.0.0.1"
    port: int = 8787
    database: str = "data/demo.sqlite3"
    poll_seconds: int = 15
    stale_seconds: int = 60
    min_confirmations: int = 6
    invoice_ttl_seconds: int = 1800
    rpc_url: str = "http://127.0.0.1:9554"
    rpc_wallet: str = "wam-pay"
    rpc_cookie_file: str = ""
    rpc_user: str = ""
    rpc_timeout_seconds: int = 10
    expected_chain: str = "main"
    expected_genesis: str = "d8d3debea987b62a0934c3980d62bffbb6e16aa797d19891d4fcc9b9fb11d7e9"
    max_tip_age_seconds: int = 3600
    api_token: str = ""
    rpc_password: str = ""


def load_config(path):
    path = Path(path).resolve()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValidationError("Cannot read config JSON") from exc
    allowed = set(Config.__dataclass_fields__) - {"api_token", "rpc_password"}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValidationError("Unknown config fields; secrets belong in environment variables")
    cfg = Config(**raw, api_token=os.getenv("WAM_PAY_API_TOKEN", ""),
                 rpc_password=os.getenv("WAM_RPC_PASSWORD", ""))
    if cfg.mode not in ("demo", "rpc") or cfg.host != "127.0.0.1":
        raise ValidationError("mode must be demo/rpc; this release binds only 127.0.0.1")
    bounds = {"port": (1, 65535), "poll_seconds": (2, 3600), "stale_seconds": (5, 7200),
              "min_confirmations": (1, 1000), "invoice_ttl_seconds": (60, 604800),
              "rpc_timeout_seconds": (1, 60), "max_tip_age_seconds": (120, 86400)}
    for key, (lo, hi) in bounds.items():
        val = getattr(cfg, key)
        if type(val) is not int or not lo <= val <= hi:
            raise ValidationError(f"Invalid {key}")
    if cfg.stale_seconds < cfg.poll_seconds * 2:
        raise ValidationError("stale_seconds must be at least twice poll_seconds")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", cfg.api_token):
        raise ValidationError("Set WAM_PAY_API_TOKEN to a random 32–128 character URL-safe token")
    for name in ("database", "rpc_url", "rpc_wallet", "rpc_cookie_file", "rpc_user",
                 "expected_chain", "expected_genesis"):
        if not isinstance(getattr(cfg, name), str):
            raise ValidationError(f"Invalid {name}")
    if not cfg.database or not cfg.rpc_wallet or len(cfg.rpc_wallet) > 128:
        raise ValidationError("database and rpc_wallet are required")
    try:
        url = urlsplit(cfg.rpc_url)
        valid = (url.scheme == "http" and url.hostname == "127.0.0.1" and
                 url.port is not None and url.path in ("", "/") and not url.query and
                 not url.fragment and not url.username and not url.password)
    except ValueError:
        valid = False
    if not valid:
        raise ValidationError("rpc_url must be http://127.0.0.1:PORT without credentials or path")
    if cfg.expected_chain not in ("main", "test", "regtest") or not re.fullmatch(
            r"[0-9a-f]{64}", cfg.expected_genesis):
        raise ValidationError("Set the expected chain and its 64-character genesis hash")
    if cfg.mode == "rpc" and not (cfg.rpc_cookie_file or (cfg.rpc_user and cfg.rpc_password)):
        raise ValidationError("Configure a cookie file or rpc_user plus WAM_RPC_PASSWORD")
    values = dict(cfg.__dict__)
    for key in ("database", "rpc_cookie_file"):
        if values[key]:
            target = Path(values[key]).expanduser()
            values[key] = str(target if target.is_absolute() else path.parent / target)
    return Config(**values)

"""Integrity-check bundled, unmodified application snapshots before importing."""

import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys

from .errors import HarnessError

ROOT = Path(__file__).resolve().parents[1]


def verify_targets():
    manifest = json.loads((ROOT / "targets" / "manifest.json").read_text())
    for relative, digest in manifest["files"].items():
        p = ROOT / "targets" / relative
        if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise HarnessError("TARGET_CHANGED")
    # An extra Python module can alter import resolution just as a changed file can.
    actual = {str(p.relative_to(ROOT / "targets")).replace("\\", "/")
              for p in (ROOT / "targets").rglob("*.py")}
    if actual != {k for k in manifest["files"] if k.endswith(".py")}:
        raise HarnessError("TARGET_CHANGED")
    return manifest


def load_targets():
    verify_targets()
    if "src" in sys.modules:
        raise HarnessError("TARGET_CHANGED")
    sys.path.insert(0, str(ROOT / "targets" / "wam-pay"))
    pay = {key: getattr(importlib.import_module(module), key) for key, module in {
        "Config": "src.config", "RPCClient": "src.rpc.client",
        "WalletGateway": "src.wallet.gateway", "Store": "src.invoices.store",
        "InvoiceService": "src.invoices.service", "make_server": "src.api.server",
    }.items()}
    spec = importlib.util.spec_from_file_location("_wam_watchtower_target",
                                                ROOT / "targets" / "watchtower" / "watchtower.py")
    wt = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = wt
    spec.loader.exec_module(wt)
    return pay, wt

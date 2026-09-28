#!/usr/bin/env python3
"""Deterministic source ZIP; no daemon, wallet, local reports or bytecode."""
import hashlib
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wam_it.report import scan_public
from wam_it.targets import verify_targets

DIRS = {"wam_it", "tests", "scenarios", "scripts", ".github", "docs", "targets", "evidence"}
FILES = {"README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md", ".gitignore", "pyproject.toml"}


def main():
    verify_targets()
    for name in ("selftest", "regtest"): scan_public(ROOT / "evidence" / name)
    output = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT.parent / "wam-integration-tests-v0.1.0.zip"
    entries = []
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if not path.is_file() or path.is_symlink(): continue
        if rel.parts[0] not in DIRS and rel.as_posix() not in FILES: continue
        if any(p in {"__pycache__", ".git", ".venv"} for p in rel.parts): continue
        if path.suffix in {".pyc", ".pyo", ".log", ".zip", ".db", ".sqlite3", ".pem", ".key"}: continue
        if path.name in {".cookie", ".env", "wallet.dat", "config.json"}: continue
        entries.append(("wam-integration-tests/" + rel.as_posix(), path.read_bytes()))
    manifest = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in entries)
    entries.append(("wam-integration-tests/MANIFEST.sha256", manifest.encode()))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=(2026,9,28,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 << 16)
            archive.writestr(info, data)
    print(f"Packaged {len(entries)} files")


if __name__ == "__main__": main()

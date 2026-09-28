import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from wam_it.cases import case, require
from wam_it.errors import HarnessError
from wam_it.node import Node, verify_binary
from wam_it.privacy import PrivateWorkspace, RunPseudonyms
from wam_it.report import SafeResult, build_report, scan_public, write_report
from wam_it.targets import verify_targets
from wam_it.testing import CANARY
from tests.transport import expect


@case("selftest", "SAFE-001", "Per-run HMAC labels are stable within a run and unlinkable across runs")
def pseudonyms(_):
    a, b = RunPseudonyms(), RunPseudonyms()
    require(a.label(CANARY) == a.label(CANARY))
    require(a.label(CANARY) != b.label(CANARY))
    require(a.label(CANARY) != a.label(CANARY + "different"))


@case("selftest", "SAFE-002", "Disposable workspace is removed after an exception")
def cleanup(_):
    try:
        with PrivateWorkspace() as ws:
            path = ws.path
            (path / "synthetic-wallet").write_text(CANARY)
            if os.name == "posix": require(path.stat().st_mode & 0o077 == 0)
            raise RuntimeError(CANARY)
    except RuntimeError:
        pass
    require(not path.exists())


@case("selftest", "SAFE-003", "Failed assertions and exceptions produce no raw data in JSON/JUnit")
def report_canaries(_):
    def bad(): raise RuntimeError(CANARY)
    def assertion(): raise AssertionError(CANARY)
    result = SafeResult()
    for ident, fn in (("CANARY-001", bad), ("CANARY-002", assertion)):
        test = unittest.FunctionTestCase(fn); test.case_id = ident; test.run(result)
    report = build_report(result.rows, "selftest")
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "report"
        write_report(dest, report)
        require(scan_public(dest) == report)
        for p in dest.iterdir():
            text = p.read_text()
            require(CANARY not in text and "Traceback" not in text and tmp not in text)


@case("selftest", "SAFE-004", "Reject report-field injection")
def report_schema(_):
    rows = [{"id":"SAFE-999", "status":"pass", "code":"", "wallet":CANARY}]
    expect("REPORT_INVALID", lambda: build_report(rows, "selftest"))


@case("selftest", "SAFE-005", "Detect appended secret text in XML artifacts")
def xml_gate(_):
    report = build_report([{"id":"SAFE-999", "status":"pass", "code":""}], "selftest")
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "report"; write_report(dest, report)
        with (dest / "junit.xml").open("a") as f: f.write(CANARY)
        expect("REPORT_INVALID", lambda: scan_public(dest))


@case("selftest", "SAFE-006", "Refuse to publish directories containing extra raw files")
def extra_artifacts(_):
    report = build_report([{"id":"SAFE-999", "status":"pass", "code":""}], "selftest")
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "report"; write_report(dest, report)
        (dest / "debug.log").write_text(CANARY)
        expect("REPORT_INVALID", lambda: scan_public(dest))


@case("selftest", "SAFE-007", "Missing tests cannot produce a green report")
def skipped_not_pass(_):
    require(build_report([], "selftest")["verdict"] == "fail")
    require(build_report([{"id":"SAFE-999","status":"not_run","code":"NOT_RUN"}], "selftest")["verdict"] == "fail")


@case("selftest", "SAFE-008", "Refuse to overwrite an existing report")
def no_overwrite(_):
    report = build_report([], "selftest")
    with tempfile.TemporaryDirectory() as tmp:
        expect("REPORT_EXISTS", lambda: write_report(tmp, report))


@case("selftest", "SAFE-009", "Verify exact bundled application bytes before loading targets")
def target_integrity(_):
    require(len(verify_targets()["files"]) > 10)


@case("selftest", "SAFE-010", "A binary checksum mismatch prevents process launch")
def binary_pin(_):
    with tempfile.TemporaryDirectory() as tmp:
        binary = Path(tmp) / "fake-daemon"
        binary.write_text(CANARY)
        with patch("subprocess.Popen") as spawn:
            node = Node(binary, "0" * 64, tmp, 0)
            expect("BINARY_DIGEST", node.start)
            require(not spawn.called)


@case("selftest", "SAFE-011", "Node configuration uses fresh datadir, local binding and disabled discovery")
def isolated_config(_):
    with PrivateWorkspace() as ws:
        n = Node("unused", "0" * 64, ws.path, 0)
        config = n.conf.read_text()
        for item in ("regtest=1", "connect=0", "dnsseed=0", "fixedseeds=0", "discover=0",
                     "rpcbind=127.0.0.1", "bind=127.0.0.1", "listenonion=0"):
            require(item in config.splitlines())
        require("rpcpassword" not in config and "rpcuser" not in config)
        if os.name == "posix": require(n.conf.stat().st_mode & 0o077 == 0)

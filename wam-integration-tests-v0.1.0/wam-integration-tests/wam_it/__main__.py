"""CLI with no live-node attachment option and no sensitive diagnostic output."""

import argparse
import contextlib
from pathlib import Path
import signal
import sys

from .cases import CATALOG, suite
from .context import Context
from .errors import HarnessError
from .node import verify_binary
from .privacy import Discard
from .report import SafeResult, build_report, scan_public, write_report


def main():
    parser = argparse.ArgumentParser(description="WAM privacy-oriented integration tests (disposable regtest only)")
    sub = parser.add_subparsers(dest="command", required=True)
    selftest = sub.add_parser("selftest", help="Test the harness against local adversarial servers")
    selftest.add_argument("--report-dir", default="reports/selftest")
    regtest = sub.add_parser("regtest", help="Launch two NEW regtest nodes and test WAM + Pay + Watchtower")
    regtest.add_argument("--wamd", required=True, help="Trusted local daemon binary; never a wallet or datadir")
    regtest.add_argument("--sha256", required=True, help="Expected SHA256 of the daemon executable")
    regtest.add_argument("--report-dir", default="reports/regtest")
    audit = sub.add_parser("check-report", help="Validate that a report directory contains only public schema data")
    audit.add_argument("directory")
    args = parser.parse_args()
    try:
        if args.command == "check-report":
            scan_public(args.directory)
            print("Report schema: PASS")
            return 0
        # Load the full catalog even when setup fails so missing coverage is explicit.
        import tests.transport, tests.privacy
        import scenarios.core, scenarios.pay, scenarios.watchtower
        if Path(args.report_dir).exists():
            raise HarnessError("REPORT_EXISTS")
        result = SafeResult()
        run_error, digest = None, None
        def interrupted(_signum, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, interrupted)
        try:
            with contextlib.redirect_stdout(Discard()), contextlib.redirect_stderr(Discard()):
                if args.command == "selftest":
                    suite("selftest").run(result)
                else:
                    path = verify_binary(args.wamd, args.sha256)
                    digest = args.sha256
                    with Context(path, digest) as context:
                        suite("regtest", context).run(result)
        except KeyboardInterrupt:
            run_error = "CANCELLED"
        except HarnessError as exc:
            run_error = exc.code
        except Exception:
            run_error = "SETUP_FAILED"
        completed = {r["id"] for r in result.rows}
        result.rows += [{"id":ident, "status":"not_run", "code":"NOT_RUN"}
                        for ident, _, _ in CATALOG[args.command] if ident not in completed]
        report = build_report(result.rows, args.command, digest, run_error)
        write_report(args.report_dir, report)
        scan_public(args.report_dir)
        counts = report["counts"]
        print(f"{args.command}: {counts['pass']} passed, {counts['fail']} failed, "
              f"{counts['error']} errors, {counts['not_run']} not run")
        for row in report["cases"]:
            if row["status"] != "pass": print(f"{row['id']}: {row['status']} ({row['code']})")
        if run_error: print("Run error: " + run_error)
        return 2 if run_error or counts["error"] or counts["not_run"] else (0 if report["verdict"] == "pass" else 1)
    except HarnessError as exc:
        print("Harness error: " + exc.code, file=sys.stderr)
        return 2
    except Exception:
        print("Harness error: INTERNAL_ERROR", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())

"""Launch a persistent fake-money demo with a fresh in-memory API token."""
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    config.update(mode="demo", database=str(ROOT / "data" / "demo.sqlite3"), rpc_cookie_file="", rpc_user="")
    env = dict(os.environ, WAM_PAY_API_TOKEN=secrets.token_urlsafe(32))
    env.pop("WAM_RPC_PASSWORD", None)
    print("Open http://127.0.0.1:8787 and paste this temporary API token:", flush=True)
    print(env["WAM_PAY_API_TOKEN"], flush=True)
    print("Demo receipts persist in data/demo.sqlite3. Ctrl+C stops the app.", flush=True)
    with tempfile.TemporaryDirectory(prefix="wam-pay-demo-") as tmp:
        path = Path(tmp) / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        child = subprocess.Popen([sys.executable, "-m", "src", "--config", str(path)], cwd=ROOT, env=env)
        try:
            return child.wait()
        except KeyboardInterrupt:
            try:
                return child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.terminate()
                return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import logging
import os
import signal
import sys
import threading

from src.api.server import make_server
from src.config import load_config
from src.errors import ConflictError, NodeUnavailable, ValidationError
from src.invoices.service import InvoiceService
from src.invoices.store import Store
from src.rpc.client import RPCClient
from src.runtime import InstanceLock
from src.wallet.demo import DemoWallet
from src.wallet.gateway import WalletGateway


def main():
    parser = argparse.ArgumentParser(description="WAM Pay local merchant dashboard")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--check", action="store_true", help="Read-only node/wallet readiness check; no address allocation")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    os.umask(0o077)
    instance = None
    try:
        cfg = load_config(args.config)
        wallet = DemoWallet() if cfg.mode == "demo" else WalletGateway(RPCClient(cfg), cfg)
        if args.check:
            if cfg.mode == "rpc":
                wallet.ready()
            print("Readiness check passed (mode=" + cfg.mode + "). Payment flow still requires an end-to-end test.")
            return 0
        instance = InstanceLock(cfg.database)
        store = Store(cfg.database, {"mode": cfg.mode, "chain": cfg.expected_chain,
                                    "genesis": cfg.expected_genesis, "wallet": cfg.rpc_wallet})
        service = InvoiceService(store, wallet, cfg)
        server = make_server(service, cfg)
        stop = threading.Event()

        def poll():
            while not stop.is_set():
                service.sync()
                stop.wait(cfg.poll_seconds)

        worker = threading.Thread(target=poll, name="payment-monitor", daemon=True)
        worker.start()
        print(f"WAM Pay ({cfg.mode}) — http://{cfg.host}:{cfg.port}", flush=True)
        if cfg.mode == "demo":
            print("DEMO: synthetic addresses and payments; do not send real WAM.", flush=True)

        def terminate(signum, frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, terminate)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            server.server_close()
            worker.join(timeout=cfg.rpc_timeout_seconds + 1)
        return 0
    except (ValidationError, ConflictError, NodeUnavailable) as exc:
        print(f"Cannot start: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Cannot start ({type(exc).__name__}); check config, node and file access.", file=sys.stderr)
        return 1
    finally:
        if instance:
            instance.close()


if __name__ == "__main__":
    raise SystemExit(main())

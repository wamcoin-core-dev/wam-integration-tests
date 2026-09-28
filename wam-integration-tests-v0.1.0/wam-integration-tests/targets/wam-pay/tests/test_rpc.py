import base64
import json
import tempfile
import threading
import unittest
from dataclasses import replace
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.config import Config
from src.errors import NodeUnavailable
from src.rpc.client import RPCClient, RPCError


class RPCTests(unittest.TestCase):
    def setUp(self):
        self.requests = []; self.response_mode = "normal"
        test = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                test.requests.append((self.path, self.headers.get("Authorization"), data))
                if test.response_mode == "redirect":
                    self.send_response(302); self.send_header("Location","http://127.0.0.1:1/secret"); self.end_headers(); return
                if test.response_mode == "auth":
                    self.send_response(401); self.end_headers(); return
                if test.response_mode == "error":
                    response = json.dumps({"id":data["id"], "error":{"code":-5, "message":"do not leak raw details"}})
                    code = 500
                else:
                    request_id = "wrong-id" if test.response_mode == "id" else data["id"]
                    response = '{"id":'+json.dumps(request_id)+',"result":{"amount":0.00000001}}'
                    code = 200
                payload = response.encode()
                self.send_response(code); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval":0.01}); self.thread.start()
        self.addCleanup(self.stop)
        self.cfg = replace(Config(), rpc_url=f"http://127.0.0.1:{self.server.server_address[1]}",
                           rpc_user="merchant", rpc_password="secret", rpc_wallet="name/with space")
        self.client = RPCClient(self.cfg)

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def test_wallet_route_basic_auth_and_decimal_decoding(self):
        result = self.client.call("gettransaction", ["txid", True])
        self.assertEqual(result["amount"], Decimal("0.00000001"))
        path, auth, payload = self.requests[-1]
        self.assertEqual(path, "/wallet/name%2Fwith%20space")
        self.assertEqual(auth, "Basic " + base64.b64encode(b"merchant:secret").decode())
        self.assertEqual(payload["params"], ["txid", True])
        self.client.call("getblockchaininfo")
        self.assertEqual(self.requests[-1][0], "/")

    def test_allowlist_blocks_spending_and_private_keys(self):
        for method in ["sendtoaddress", "dumpprivkey", "walletpassphrase", "sendrawtransaction", "stop"]:
            with self.subTest(method=method), self.assertRaises(ValueError): self.client.call(method)
        self.assertEqual(self.requests, [])

    def test_http_rpc_error_code_preserved_without_body(self):
        self.response_mode = "error"
        with self.assertRaises(RPCError) as caught: self.client.call("getmempoolentry", ["txid"])
        self.assertEqual(caught.exception.code, -5)
        self.assertNotIn("raw details", str(caught.exception))

    def test_wrong_id_auth_failure_and_redirect_rejected(self):
        for mode in ["id", "auth", "redirect"]:
            self.response_mode = mode
            with self.subTest(mode=mode), self.assertRaises(NodeUnavailable): self.client.call("getblockchaininfo")

    def test_cookie_is_reread_after_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".cookie"
            client = RPCClient(replace(self.cfg, rpc_cookie_file=str(path)))
            for secret in ["__cookie__:first", "__cookie__:second"]:
                path.write_text(secret, encoding="utf-8")
                client.call("getblockchaininfo")
                self.assertEqual(self.requests[-1][1], "Basic " + base64.b64encode(secret.encode()).decode())

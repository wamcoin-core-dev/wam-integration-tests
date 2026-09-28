import http.client
import json
import threading
from dataclasses import replace

from src.api.server import make_server
from tests.helpers import ServiceCase


class APITests(ServiceCase):
    def setUp(self):
        super().setUp()
        self.server = make_server(self.service, self.cfg, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval":0.01})
        self.thread.start()
        self.addCleanup(self.close_server)
        self.port = self.server.server_address[1]

    def close_server(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, method, path, body=None, auth=True, extra=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        headers = {"Authorization":"Bearer " + self.cfg.api_token} if auth else {}
        if body is not None:
            if not isinstance(body, str): body = json.dumps(body)
            headers["Content-Type"] = "application/json"
        headers.update(extra or {})
        try:
            conn.request(method, path, body, headers)
            response = conn.getresponse()
            raw = response.read()
            content = json.loads(raw) if "application/json" in response.getheader("Content-Type", "") else raw
            return response.status, content, dict(response.getheaders())
        finally:
            conn.close()

    def test_private_routes_require_token(self):
        for method, path in [("GET","/api/status"),("GET","/api/invoices"),("POST","/api/invoices")]:
            with self.subTest(path=path): self.assertEqual(self.request(method, path, auth=False)[0], 401)

    def test_absolute_request_target_cannot_bypass_auth(self):
        response = self.request("GET", f"http://127.0.0.1:{self.port}/api/invoices", auth=False)
        self.assertEqual(response[0], 400)

    def test_host_and_origin_checks(self):
        self.assertEqual(self.request("GET", "/api/invoices", extra={"Host":"attacker.example"})[0], 403)
        self.assertEqual(self.request("POST", "/api/invoices", {}, extra={"Origin":"https://attacker.example"})[0], 403)

    def test_create_replay_conflict_and_detail(self):
        header = {"Idempotency-Key":"test-order-1234"}
        first = self.request("POST", "/api/invoices", {"amount":"1.00000001"}, extra=header)
        self.assertEqual(first[0], 201)
        self.assertEqual(self.request("POST", "/api/invoices", {"amount":"1.00000001"}, extra=header)[0], 200)
        self.assertEqual(self.request("POST", "/api/invoices", {"amount":"2"}, extra=header)[0], 409)
        result = self.request("GET", "/api/invoices/" + first[1]["id"])
        self.assertEqual(result[1]["amount"], "1.00000001")
        self.assertIn("payments", result[1])

    def test_invalid_json_floats_size_and_pagination(self):
        header = {"Idempotency-Key":"test-order-1234"}
        for body in ['{"amount":"1","amount":"2"}', '{"amount": NaN}', '{', {"amount":1.0}, 'x'*8193]:
            with self.subTest(body=str(body)[:50]):
                self.assertEqual(self.request("POST", "/api/invoices", body, extra=header)[0], 400)
        for query in ["limit=201", "offset=-1", "limit=x", "limit=1&limit=2", "a=1&b=2&c=3&d=4&e=5"]:
            self.assertEqual(self.request("GET", "/api/invoices?"+query)[0], 400)

    def test_full_demo_payment_flow(self):
        inv = self.invoice()
        path = "/api/invoices/" + inv["id"] + "/demo-payments"
        result = self.request("POST", path, {"amount":"10", "confirmations":0})
        self.assertEqual(result[1]["invoice"]["status"], "confirming")
        result = self.request("POST", path, {"txid":result[1]["txid"], "confirmations":6})
        self.assertEqual(result[1]["invoice"]["status"], "paid")

    def test_demo_disabled_in_rpc_service(self):
        self.service.cfg = replace(self.cfg, mode="rpc")
        inv = self.invoice()
        self.assertEqual(self.request("POST", "/api/invoices/"+inv["id"]+"/demo-payments", {"amount":"1"})[0], 400)

    def test_static_headers_and_no_secret_exposure(self):
        status, body, headers = self.request("GET", "/", auth=False)
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertNotIn(self.cfg.api_token.encode(), body)
        status, data, headers = self.request("GET", "/api/status")
        self.assertNotIn("api_token", data)
        self.assertNotIn("rpc_password", data)
        self.assertEqual(self.request("GET", "/config.json")[0], 404)
        self.assertEqual(self.request("GET", "/../config.json")[0], 404)

    def test_memo_is_json_data_not_server_html(self):
        inv = self.invoice(memo='<img src=x onerror="alert(1)">')
        result = self.request("GET", "/api/invoices/"+inv["id"])
        self.assertEqual(result[1]["memo"], inv["memo"])
        self.assertTrue(result[2]["Content-Type"].startswith("application/json"))

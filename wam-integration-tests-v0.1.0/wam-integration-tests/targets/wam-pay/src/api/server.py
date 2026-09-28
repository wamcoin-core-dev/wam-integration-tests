import hmac
import json
import logging
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from src.errors import ConflictError, NodeUnavailable, ValidationError

UI = Path(__file__).resolve().parents[1] / "ui"
MAX_BODY = 8192


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 16


def make_server(service, cfg, port=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "WAM-Pay"

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, format, *args):
            pass  # URLs and customer data are intentionally not logged.

        def respond(self, status, data, content_type="application/json; charset=utf-8"):
            if content_type.startswith("application/json"):
                data = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True

        def guard(self):
            if not self.path.startswith("/") or self.path.startswith("//"):
                self.respond(400, {"error": "origin_form_required"})
                return False
            actual_port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}"}
            if len(self.headers.get_all("Host", [])) != 1 or self.headers.get("Host") not in hosts:
                self.respond(403, {"error": "invalid_host"})
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + host for host in hosts}:
                self.respond(403, {"error": "invalid_origin"})
                return False
            if self.headers.get("Transfer-Encoding"):
                self.respond(400, {"error": "transfer_encoding_not_supported"})
                return False
            if self.path.startswith("/api/"):
                auth = self.headers.get("Authorization", "")
                if not hmac.compare_digest(auth.encode(), ("Bearer " + cfg.api_token).encode()):
                    self.respond(401, {"error": "unauthorized"})
                    return False
            return True

        def body(self):
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,6}", lengths[0]):
                raise ValidationError("One valid Content-Length is required")
            length = int(lengths[0])
            if not 0 < length <= MAX_BODY:
                raise ValidationError("Request body must be 1–8192 bytes")
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise ValidationError("Content-Type must be application/json")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValidationError("Incomplete request body")
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("Duplicate JSON field")
                    result[key] = value
                return result
            def invalid_constant(value):
                raise ValueError("Non-finite number")
            try:
                return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
            except (ValueError, UnicodeError, RecursionError):
                raise ValidationError("Invalid JSON") from None

        def run_route(self, method):
            try:
                if not self.guard():
                    return
                url = urlsplit(self.path)
                path = url.path
                if method == "GET" and path == "/healthz":
                    return self.respond(200, {"alive": True})
                static = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                          "/styles.css": ("styles.css", "text/css")}
                if method == "GET" and path in static:
                    name, mime = static[path]
                    return self.respond(200, (UI / name).read_bytes(), mime + "; charset=utf-8")
                if method == "GET" and path == "/api/status":
                    return self.respond(200, service.health())
                if path == "/api/invoices":
                    if method == "GET":
                        try:
                            query = parse_qs(url.query, keep_blank_values=True, max_num_fields=4)
                        except ValueError:
                            raise ValidationError("Invalid pagination parameters") from None
                        if set(query) - {"limit", "offset"} or any(len(v) != 1 for v in query.values()):
                            raise ValidationError("Invalid pagination parameters")
                        try:
                            limit, offset = int(query.get("limit", ["50"])[0]), int(query.get("offset", ["0"])[0])
                        except ValueError:
                            raise ValidationError("Invalid pagination") from None
                        if not 1 <= limit <= 200 or not 0 <= offset <= 1_000_000:
                            raise ValidationError("limit must be 1–200; offset must be 0–1000000")
                        return self.respond(200, {"invoices": service.list(limit, offset)})
                    if method == "POST":
                        result, created = service.create(self.body(), self.headers.get("Idempotency-Key"))
                        return self.respond(201 if created else 200, result)
                match = re.fullmatch(r"/api/invoices/([0-9a-f]{32})(/demo-payments)?", path)
                if match:
                    invoice_id, demo = match.groups()
                    if demo and method == "POST" and cfg.mode == "demo":
                        return self.respond(200, service.demo_payment(invoice_id, self.body()))
                    if not demo and method == "GET":
                        inv = service.get(invoice_id)
                        return self.respond(200, inv) if inv else self.respond(404, {"error": "not_found"})
                self.respond(404, {"error": "not_found"})
            except ValidationError as exc:
                self.respond(400, {"error": str(exc)})
            except ConflictError as exc:
                self.respond(409, {"error": str(exc)})
            except NodeUnavailable:
                self.respond(503, {"error": "node_unavailable"})
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                self.close_connection = True
            except Exception as exc:
                logging.getLogger("wam_pay").error("HTTP operation failed (%s)", type(exc).__name__)
                self.respond(500, {"error": "internal_error"})

        def do_GET(self):
            self.run_route("GET")

        def do_POST(self):
            self.run_route("POST")

        def do_OPTIONS(self):
            self.respond(405, {"error": "method_not_allowed"})

    return LocalServer((cfg.host, cfg.port if port is None else port), Handler)

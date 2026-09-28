import base64
import json
import uuid
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from src.errors import NodeUnavailable

NODE_METHODS = frozenset({"getblockchaininfo", "getblockhash", "getblockheader",
                          "getconnectioncount", "getmempoolentry"})
WALLET_METHODS = frozenset({"getnewaddress", "getaddressinfo", "getwalletinfo",
                            "listreceivedbyaddress", "gettransaction"})
MAX_RESPONSE = 16 * 1024 * 1024


class RPCError(NodeUnavailable):
    def __init__(self, code):
        self.code = code
        super().__init__(f"RPC returned error code {code}")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def reject_constant(value):
    raise ValueError("Non-finite JSON number")


class RPCClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def call(self, method, params=None):
        if method not in NODE_METHODS | WALLET_METHODS:
            raise ValueError("RPC method is not allowed")
        cfg = self.cfg
        try:
            if cfg.rpc_cookie_file:
                credentials = Path(cfg.rpc_cookie_file).read_text(encoding="utf-8").strip()
                if ":" not in credentials or "\n" in credentials:
                    raise ValueError("Invalid cookie")
            else:
                credentials = f"{cfg.rpc_user}:{cfg.rpc_password}"
            auth = base64.b64encode(credentials.encode()).decode()
            request_id = uuid.uuid4().hex
            url = cfg.rpc_url.rstrip("/")
            if method in WALLET_METHODS:
                url += "/wallet/" + quote(cfg.rpc_wallet, safe="")
            payload = json.dumps({"jsonrpc": "2.0", "id": request_id,
                                  "method": method, "params": params or []}).encode()
            request = Request(url, data=payload, headers={"Content-Type": "application/json",
                              "Authorization": "Basic " + auth}, method="POST")
            try:
                response = self.opener.open(request, timeout=cfg.rpc_timeout_seconds)
            except HTTPError as exc:
                if exc.code not in (400, 404, 500):
                    raise NodeUnavailable("RPC HTTP request failed") from None
                response = exc
            with response:
                data = response.read(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE:
                raise ValueError("RPC response too large")
            decoded = json.loads(data, parse_float=Decimal, parse_constant=reject_constant)
            if not isinstance(decoded, dict) or decoded.get("id") != request_id:
                raise ValueError("Invalid RPC envelope")
            if decoded.get("error") is not None:
                code = decoded["error"].get("code")
                if type(code) is not int:
                    raise ValueError("Invalid RPC error")
                raise RPCError(code)
            if "result" not in decoded:
                raise ValueError("Missing RPC result")
            return decoded["result"]
        except NodeUnavailable:
            raise
        except (OSError, URLError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise NodeUnavailable("RPC unavailable or invalid response") from None

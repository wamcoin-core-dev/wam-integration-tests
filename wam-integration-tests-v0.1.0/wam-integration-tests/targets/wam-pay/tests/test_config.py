import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.config import load_config
from src.errors import ValidationError


class ConfigTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "config.json"
        self.env = patch.dict(os.environ, {"WAM_PAY_API_TOKEN":"t"*48}, clear=True)
        self.env.start(); self.addCleanup(self.env.stop)

    def load(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")
        return load_config(self.path)

    def test_paths_are_relative_to_config(self):
        cfg = self.load({"database":"data/test.sqlite3"})
        self.assertEqual(Path(cfg.database), self.path.parent / "data/test.sqlite3")

    def test_reject_network_exposure_embedded_secrets_and_unknown_keys(self):
        cases = [{"host":"0.0.0.0"},{"rpc_url":"http://example.com:9554"},
                 {"rpc_url":"http://user:password@127.0.0.1:9554"},
                 {"rpc_url":"http://127.0.0.1:9554/wallet/x"},{"min_confirmations":0},
                 {"min_confirmations":True},{"api_token":"secret"},{"other":1},
                 {"mode":"rpc"},{"stale_seconds":10},{"expected_genesis":"x"}]
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ValidationError): self.load(data)

    def test_secret_required(self):
        os.environ["WAM_PAY_API_TOKEN"] = "short"
        with self.assertRaises(ValidationError): self.load({})

    def test_cookie_auth_and_explicit_credentials(self):
        self.assertEqual(self.load({"mode":"rpc", "rpc_cookie_file":".cookie"}).mode, "rpc")
        os.environ["WAM_RPC_PASSWORD"] = "a-secret-not-logged"
        self.assertEqual(self.load({"mode":"rpc", "rpc_user":"merchant"}).rpc_user, "merchant")

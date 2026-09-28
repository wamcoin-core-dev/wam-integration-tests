import tempfile
import unittest
from pathlib import Path

from src.errors import ConflictError
from src.runtime import InstanceLock


class RuntimeTests(unittest.TestCase):
    def test_single_instance_and_clean_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "invoice.sqlite3")
            first = InstanceLock(path)
            try:
                with self.assertRaises(ConflictError): InstanceLock(path)
            finally:
                first.close()
            second = InstanceLock(path)
            second.close()

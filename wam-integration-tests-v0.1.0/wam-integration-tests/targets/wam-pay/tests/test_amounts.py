import unittest
from decimal import Decimal

from src.errors import ValidationError
from src.invoices.amounts import format_amount, parse_amount, rpc_units


class AmountTests(unittest.TestCase):
    def test_exact_smallest_unit_and_maximum(self):
        self.assertEqual(parse_amount("0.00000001"), 1)
        self.assertEqual(parse_amount("22000000"), 2_200_000_000_000_000)
        self.assertEqual(format_amount(parse_amount("12.34")), "12.34000000")

    def test_reject_ambiguous_or_unsafe_api_amounts(self):
        for value in [1.1, 1, True, None, "0", "-1", "1e3", "NaN", "Infinity", "1.000000001",
                      " 1", "1 ", "+1", "01", ".1", "1.", "22000000.00000001", "1,000", "١"]:
            with self.subTest(value=value), self.assertRaises(ValidationError): parse_amount(value)

    def test_rpc_decimal_preserved(self):
        self.assertEqual(rpc_units(Decimal("0.00000001")), 1)
        self.assertEqual(rpc_units(Decimal("0.1")) + rpc_units(Decimal("0.2")), 30_000_000)

    def test_rpc_refuses_float_and_bad_precision(self):
        for value in [0.1, "0.1", True, Decimal("NaN"), Decimal("Infinity"), Decimal("0.000000001"), -1]:
            with self.subTest(value=value), self.assertRaises(ValidationError): rpc_units(value)

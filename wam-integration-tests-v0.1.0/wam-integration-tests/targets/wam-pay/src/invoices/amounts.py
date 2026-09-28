import re
from decimal import Decimal

from src.errors import ValidationError

SCALE = 100_000_000
MAX_UNITS = 22_000_000 * SCALE


def parse_amount(value):
    """Public amounts MUST be fixed-point strings, never JSON floats."""
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]{0,7})(?:\.[0-9]{1,8})?", value):
        raise ValidationError("amount must be a positive decimal string with at most 8 decimals")
    units = int(Decimal(value) * SCALE)
    if not 0 < units <= MAX_UNITS:
        raise ValidationError("amount must be greater than zero and at most 22000000 WAM")
    return units


def rpc_units(value):
    """RPC JSON is parsed with Decimal before reaching this function."""
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise ValidationError("RPC amount must be an exact number")
    scaled = Decimal(value) * SCALE
    if not scaled.is_finite() or scaled != scaled.to_integral_value() or not 0 < scaled <= MAX_UNITS:
        raise ValidationError("Invalid RPC amount precision or range")
    return int(scaled)


def format_amount(units):
    return f"{units // SCALE}.{units % SCALE:08d}"

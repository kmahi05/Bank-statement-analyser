"""Money helpers. All amounts are decimal.Decimal; floats are never used."""
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def round_money(value: Decimal) -> Decimal:
    """Round to paise using the usual 'half up' rule (0.005 -> 0.01)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def money_str(value: Decimal) -> str:
    """Format for the JSON report: always two decimals, as a string."""
    return str(round_money(value))

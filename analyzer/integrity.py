"""Check 4: running-balance integrity."""
from .money import money_str


def find_balance_breaks(transactions):
    """Report every row whose printed balance != previous printed balance + credit - debit.

    We compare against the previous PRINTED balance, not our own running total,
    so one bad row is reported once instead of making every later row look wrong.
    """
    breaks = []
    for prev, cur in zip(transactions, transactions[1:]):
        expected = prev.balance + cur.credit - cur.debit
        if expected != cur.balance:
            breaks.append({
                "line": cur.line,
                "expected": money_str(expected),
                "printed": money_str(cur.balance),
                "difference": money_str(cur.balance - expected),
            })
    return breaks

"""Check 1: average monthly balance (AMB)."""
from datetime import timedelta
from decimal import Decimal

from .money import money_str


def daily_closing_balances(transactions):
    """date -> printed balance on the LAST row of that date, in file order."""
    closing = {}
    for txn in transactions:
        closing[txn.date] = txn.balance       # a later row on the same day overwrites
    return closing


def monthly_average_balance(transactions):
    """Return {"YYYY-MM": {"average": "123.45", "days": 30}}.

    Walks every calendar day from the first to the last date in the statement.
    On a day with no rows, the previous day's closing balance is carried forward.
    Days outside the statement period are not invented (see README).
    """
    if not transactions:
        return {}

    closing = daily_closing_balances(transactions)
    day, last_day = min(closing), max(closing)
    sums, counts = {}, {}
    balance = None

    while day <= last_day:
        balance = closing.get(day, balance)   # no rows today -> keep yesterday's balance
        month = day.strftime("%Y-%m")
        sums[month] = sums.get(month, Decimal("0")) + balance
        counts[month] = counts.get(month, 0) + 1
        day += timedelta(days=1)

    return {
        month: {"average": money_str(sums[month] / counts[month]), "days": counts[month]}
        for month in sums
    }

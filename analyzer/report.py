"""Glue: run the parser and the four checks, and assemble the JSON report."""
from .balance import monthly_average_balance
from .bounces import find_bounces
from .integrity import find_balance_breaks
from .parser import parse_statement
from .round_trips import DEFAULT_MAX_GAP_DAYS, DEFAULT_MIN_AMOUNT, find_round_trips


def analyse(text, min_amount=DEFAULT_MIN_AMOUNT, max_gap_days=DEFAULT_MAX_GAP_DAYS):
    parsed = parse_statement(text)
    txns = parsed.transactions

    monthly = monthly_average_balance(txns)
    bounces, bounce_warnings = find_bounces(txns)

    return {
        "statement_period": {
            "from": txns[0].date.isoformat() if txns else None,
            "to": txns[-1].date.isoformat() if txns else None,
        },
        "monthly_average_balance": {m: v["average"] for m, v in monthly.items()},
        "monthly_days_counted": {m: v["days"] for m, v in monthly.items()},
        "bounces": bounces,
        "round_trips": find_round_trips(txns, min_amount, max_gap_days),
        "balance_breaks": find_balance_breaks(txns),
        "warnings": parsed.warnings + bounce_warnings,
    }

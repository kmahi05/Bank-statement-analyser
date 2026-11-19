"""Check 3: round-trip transactions.

Rule: a CREDIT from counterparty X, followed by a DEBIT to the same X, of exactly
the same amount, at or above min_amount, at most max_gap_days calendar days later.
Each row is used in at most one pair.
"""
import re
from decimal import Decimal

from .money import money_str

DEFAULT_MIN_AMOUNT = Decimal("100000")    # Rs 1,00,000
DEFAULT_MAX_GAP_DAYS = 2                 # dates only, no times: 48 hours ~ 2 calendar days

# Where the counterparty name sits in each description style we have seen.
COUNTERPARTY_PATTERNS = [
    re.compile(r"^(?:NEFT|RTGS|IMPS|UPI)[-/ ](?:CR|DR)[-/ ]+(?P<name>.+)$"),   # NEFT-CR-ABC LTD
    re.compile(r"^(?:CHQ|CHEQUE) DEP\w*\s+\d+\s*-\s*(?P<name>.+)$"),            # CHQ DEP 123 - ABC
    re.compile(r"^POS PURCHASE\s+(?P<name>.+)$"),                               # POS PURCHASE ABC
]


def normalise_name(name: str) -> str:
    """'M/S "AMBA" Distributors' -> 'M S AMBA DISTRIBUTORS'. Keeps '&'."""
    cleaned = re.sub(r"[^A-Z0-9&]", " ", name.upper())
    return " ".join(cleaned.split())


def counterparty(description: str):
    """Return the normalised counterparty name, or None if we can't tell who it is."""
    text = " ".join(description.upper().split())
    for pattern in COUNTERPARTY_PATTERNS:
        m = pattern.match(text)
        if m:
            return normalise_name(m.group("name"))
    return None


def find_round_trips(transactions, min_amount=DEFAULT_MIN_AMOUNT,
                     max_gap_days=DEFAULT_MAX_GAP_DAYS):
    credits = [t for t in transactions if t.credit >= min_amount]
    debits = [t for t in transactions if t.debit >= min_amount]
    used_debits = set()
    trips = []

    for c in credits:
        name = counterparty(c.description)
        if name is None:
            continue
        for d in debits:                          # file order -> earliest match wins
            if d.line in used_debits or d.line <= c.line:
                continue                          # already paired, or not after the credit
            gap = (d.date - c.date).days
            if gap < 0 or gap > max_gap_days:
                continue
            if d.debit == c.credit and counterparty(d.description) == name:
                used_debits.add(d.line)
                trips.append({
                    "credit": c.line,
                    "debit": d.line,
                    "counterparty": name,
                    "amount": money_str(c.credit),
                    "gap_days": gap,
                })
                break                             # this credit is paired; move to the next
    return trips

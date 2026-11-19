"""Check 2: bounced cheques.

A bounce leaves three rows:  CHQ DEP <no> ...  ->  CHQ RTN <no> ...  ->  RTN CHGS <no>
We link them by cheque number and report one entry per cheque (instrument).
"""
import re

from .money import money_str

DEPOSIT = re.compile(r"^(?:CHQ|CHEQUE) DEP\w*\s+(\d+)")
RETURN = re.compile(r"^(?:CHQ|CHEQUE) (?:RTN|RETURN)\w*\s+(\d+)")
CHARGE = re.compile(r"^RTN CHGS?\s+(\d+)")


def find_bounces(transactions):
    """Return (bounces, warnings)."""
    last_deposit = {}     # cheque no -> most recent CHQ DEP row for it
    bounces = {}          # cheque no -> report entry (dict keeps insertion order)
    warnings = []

    for txn in transactions:
        desc = txn.description.upper()

        if m := DEPOSIT.match(desc):
            last_deposit[m.group(1)] = txn

        elif m := RETURN.match(desc):
            cheque = m.group(1)
            if cheque in bounces:
                warnings.append({"line": txn.line,
                                 "issue": f"cheque {cheque} returned again; counted once"})
                continue
            deposit = last_deposit.get(cheque)
            if deposit is None:
                warnings.append({"line": txn.line,
                                 "issue": f"cheque {cheque} returned but its deposit is not in the file"})
            elif deposit.credit != txn.debit:
                warnings.append({"line": txn.line,
                                 "issue": f"cheque {cheque}: returned amount {txn.debit} "
                                          f"differs from deposit {deposit.credit}"})
            bounces[cheque] = {
                "cheque_no": cheque,
                "deposit": deposit.line if deposit else None,
                "return": txn.line,
                "charge": None,
                "amount": money_str(txn.debit),
            }

        elif m := CHARGE.match(desc):
            cheque = m.group(1)
            entry = bounces.get(cheque)
            if entry is None:
                warnings.append({"line": txn.line,
                                 "issue": f"return charge for cheque {cheque} with no return row before it"})
            elif entry["charge"] is not None:
                warnings.append({"line": txn.line,
                                 "issue": f"extra return charge for cheque {cheque}"})
            else:
                entry["charge"] = txn.line

    for entry in bounces.values():
        if entry["charge"] is None:
            warnings.append({"line": entry["return"],
                             "issue": f"cheque {entry['cheque_no']} returned but no RTN CHGS row found"})

    return list(bounces.values()), warnings

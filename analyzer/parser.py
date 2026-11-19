"""Turn raw CSV text into clean Transaction records plus a list of warnings.

Nothing in here decides anything about bounces or round trips. Its only job
is to read the file faithfully and say clearly what it could not read.
"""
import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

EXPECTED_COLUMNS = ["date", "description", "debit", "credit", "balance"]

# The brief says YYYY-MM-DD, but statement_A.csv actually uses DD-MM-YYYY.
# We accept both. We never try MM-DD-YYYY: Indian banks print day first.
DATE_FORMATS = {
    "%Y-%m-%d": "YYYY-MM-DD",
    "%d-%m-%Y": "DD-MM-YYYY",
    "%d/%m/%Y": "DD/MM/YYYY",
}

ZERO = Decimal("0")


class StatementError(ValueError):
    """The file cannot be analysed at all (empty, or the header is wrong)."""


@dataclass(frozen=True)
class Transaction:
    line: int            # physical line number in the file (header = line 1)
    date: date
    description: str
    debit: Decimal       # 0 when the row is a credit
    credit: Decimal      # 0 when the row is a debit
    balance: Decimal     # running balance exactly as printed by the bank
    is_opening: bool = False


@dataclass
class ParseResult:
    transactions: list
    warnings: list


def parse_amount(raw: str):
    """'1,00,000.50' -> Decimal('100000.50'); blank -> None; junk -> ValueError."""
    text = raw.strip().replace(",", "")
    if text == "":
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"not a valid amount: {raw!r}") from None
    if not value.is_finite():                 # Decimal accepts 'NaN' and 'Infinity'
        raise ValueError(f"not a valid amount: {raw!r}")
    return value


def parse_date(raw: str):
    """Return (date, format_name). Raise ValueError if no known format fits."""
    text = raw.strip()
    for fmt, name in DATE_FORMATS.items():
        try:
            return datetime.strptime(text, fmt).date(), name
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {raw!r}")


def _parse_row(row, line):
    """Convert one CSV row into (Transaction, date_format). Raise ValueError if unusable."""
    if len(row) != len(EXPECTED_COLUMNS):
        raise ValueError(f"expected {len(EXPECTED_COLUMNS)} columns, found {len(row)}")

    raw_date, raw_desc, raw_debit, raw_credit, raw_balance = row
    txn_date, date_format = parse_date(raw_date)
    description = " ".join(raw_desc.split())      # trim and collapse inner whitespace
    debit = parse_amount(raw_debit)
    credit = parse_amount(raw_credit)
    balance = parse_amount(raw_balance)

    if balance is None:
        raise ValueError("balance is missing")

    if description.upper() == "OPENING BALANCE":
        if debit or credit:
            raise ValueError("opening balance row should not have a debit or credit")
        txn = Transaction(line, txn_date, description, ZERO, ZERO, balance, is_opening=True)
        return txn, date_format

    if debit is None and credit is None:
        raise ValueError("neither debit nor credit is filled")
    if debit is not None and credit is not None:
        raise ValueError("both debit and credit are filled")
    amount = debit if debit is not None else credit
    if amount < 0:
        raise ValueError(f"negative amount: {amount}")

    txn = Transaction(line, txn_date, description, debit or ZERO, credit or ZERO, balance)
    return txn, date_format


def parse_statement(text: str) -> ParseResult:
    """Parse the whole file. Bad rows are skipped and reported, never silently dropped."""
    text = text.lstrip("﻿")                  # Excel often adds a byte-order mark
    reader = csv.reader(io.StringIO(text, newline=""))

    transactions, warnings = [], []
    formats_seen = set()
    header_seen = False
    prev_end_line = 0                             # last physical line of the previous record

    for row in reader:
        # A quoted description may span lines, so a record can start several
        # lines after the previous one ended. reader.line_num is the END line.
        line = prev_end_line + 1
        prev_end_line = reader.line_num

        if not any(cell.strip() for cell in row):   # blank line (or a row of empty cells)
            continue

        if not header_seen:
            header = [cell.strip().lower() for cell in row]
            if header != EXPECTED_COLUMNS:
                raise StatementError(f"line {line}: unexpected header {row!r}")
            header_seen = True
            continue

        try:
            txn, date_format = _parse_row(row, line)
        except ValueError as exc:
            warnings.append({"line": line, "issue": f"row skipped: {exc}"})
            continue

        if transactions and txn.date < transactions[-1].date:
            warnings.append({"line": line, "issue": "date is earlier than the previous row"})
        if txn.is_opening and transactions:
            warnings.append({"line": line, "issue": "OPENING BALANCE row is not the first row"})

        formats_seen.add(date_format)
        transactions.append(txn)

    if not header_seen:
        raise StatementError("file is empty")
    if transactions and not transactions[0].is_opening:
        warnings.append({"line": transactions[0].line,
                         "issue": "no OPENING BALANCE row; first row cannot be integrity-checked"})
    if formats_seen - {"YYYY-MM-DD"}:
        warnings.append({"line": None,
                         "issue": "dates use " + ", ".join(sorted(formats_seen))
                                  + " (spec says YYYY-MM-DD); read as day-month-year"})

    return ParseResult(transactions, warnings)


def read_statement(path) -> ParseResult:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return parse_statement(f.read())

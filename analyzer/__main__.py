"""Command line:  python -m analyzer data/statement_A.csv [--out report.json]"""
import argparse
import json
import sys

from .parser import StatementError, parse_amount
from .report import analyse
from .round_trips import DEFAULT_MAX_GAP_DAYS, DEFAULT_MIN_AMOUNT


def rupees(text):
    """argparse type: '1,00,000' -> Decimal('100000'). Never goes through float."""
    value = parse_amount(text)        # raises ValueError on junk, which argparse reports nicely
    if value is None:
        raise ValueError("empty amount")
    return value


def main(argv=None):
    ap = argparse.ArgumentParser(description="First-pass checks on a bank statement CSV.")
    ap.add_argument("csv_path")
    ap.add_argument("--out", help="write the JSON here instead of printing it")
    ap.add_argument("--min-amount", type=rupees, default=DEFAULT_MIN_AMOUNT,
                    help="round-trip threshold in rupees (default 100000)")
    ap.add_argument("--max-gap-days", type=int, default=DEFAULT_MAX_GAP_DAYS,
                    help="round-trip window in calendar days (default 2 = 48h)")
    args = ap.parse_args(argv)

    try:
        with open(args.csv_path, encoding="utf-8-sig", newline="") as f:
            report = analyse(f.read(), args.min_amount, args.max_gap_days)
    except (OSError, UnicodeDecodeError, StatementError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output = json.dumps(report, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output + "\n")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())

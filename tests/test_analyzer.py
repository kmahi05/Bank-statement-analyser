"""Tests: each one pins down a behaviour or a decision written in the README."""
from decimal import Decimal
from pathlib import Path

import pytest

from analyzer.balance import monthly_average_balance
from analyzer.bounces import find_bounces
from analyzer.integrity import find_balance_breaks
from analyzer.parser import StatementError, parse_statement
from analyzer.report import analyse
from analyzer.round_trips import counterparty, find_round_trips

HEADER = "date,description,debit,credit,balance\n"


def csv_text(*rows):
    return HEADER + "".join(r + "\n" for r in rows)


def txns(*rows):
    return parse_statement(csv_text(*rows)).transactions


# ---------- parser ----------

def test_quoted_commas_and_escaped_quotes_are_kept_in_description():
    t = txns('2026-04-01,OPENING BALANCE,,,100',
             '2026-04-02,"NEFT-CR-MEHTA, JOSHI & CO",,50,150',
             '2026-04-02,"NEFT-CR-M/S ""AMBA"" DISTRIBUTORS",,10,160')
    assert t[1].description == "NEFT-CR-MEHTA, JOSHI & CO"
    assert t[2].description == 'NEFT-CR-M/S "AMBA" DISTRIBUTORS'
    assert t[1].credit == Decimal("50")


def test_line_numbers_are_file_lines_even_with_blank_and_multiline_rows():
    text = csv_text('01-04-2026,OPENING BALANCE,,,100',
                    '',                                         # blank line 3
                    '02-04-2026,"TWO\nLINE DESC",,5,105',        # lines 4-5
                    '03-04-2026,X,5,,100')                       # line 6
    t = parse_statement(text).transactions
    assert [x.line for x in t] == [2, 4, 6]


def test_indian_grouped_amounts_and_both_date_formats():
    t = txns('2026-04-01,OPENING BALANCE,,,"1,00,000.00"',
             '02-04-2026,X,," 2,50,000.5 ","3,50,000.50"')
    assert t[0].balance == Decimal("100000.00")
    assert t[1].credit == Decimal("250000.5")
    assert t[1].date.isoformat() == "2026-04-02"


def test_bad_rows_are_skipped_with_a_warning_not_silently():
    result = parse_statement(csv_text('2026-04-01,OPENING BALANCE,,,100',
                                      '2026-04-02,BOTH,5,5,100',
                                      '2026-04-03,NONE,,,100',
                                      'not-a-date,X,5,,95'))
    assert len(result.transactions) == 1
    assert [w["line"] for w in result.warnings] == [3, 4, 5]


def test_wrong_header_is_a_hard_error():
    with pytest.raises(StatementError):
        parse_statement("when,what,out,in,bal\n")


# ---------- check 1: average monthly balance ----------

def test_amb_carries_balance_forward_and_uses_last_row_of_the_day():
    t = txns('2026-04-01,OPENING BALANCE,,,100',
             '2026-04-01,A,,50,150',      # closing balance on 1 Apr is 150 (last row)
             '2026-04-03,B,,150,300')     # 2 Apr has no rows -> carries 150
    # days: 150, 150, 300 -> 600 / 3 = 200
    assert monthly_average_balance(t)["2026-04"] == {"average": "200.00", "days": 3}


def test_amb_splits_by_calendar_month_and_rounds_half_up():
    t = txns('2026-04-30,OPENING BALANCE,,,0.01',
             '2026-05-01,A,,0.01,0.02',
             '2026-05-02,B,0.02,,0.00',
             '2026-05-03,C,,0.03,0.03')
    amb = monthly_average_balance(t)
    assert amb["2026-04"]["average"] == "0.01"
    assert amb["2026-05"]["average"] == "0.02"   # (0.02+0+0.03)/3 = 0.01666.. -> 0.02


# ---------- check 2: bounces ----------

def test_three_rows_are_one_bounce():
    t = txns('2026-04-01,OPENING BALANCE,,,0',
             '2026-04-02,CHQ DEP 111 - ACME,,500,500',
             '2026-04-05,CHQ RTN 111 INSUFF FUNDS,500,,0',
             '2026-04-05,RTN CHGS 111,590,,-590')
    bounces, warnings = find_bounces(t)
    assert bounces == [{"cheque_no": "111", "deposit": 3, "return": 4,
                        "charge": 5, "amount": "500.00"}]
    assert warnings == []


def test_bounce_without_charge_row_is_still_reported_and_warned():
    t = txns('2026-04-01,OPENING BALANCE,,,0',
             '2026-04-02,CHQ DEP 111 - ACME,,500,500',
             '2026-04-05,CHQ RTN 111,500,,0')
    bounces, warnings = find_bounces(t)
    assert bounces[0]["charge"] is None
    assert "no RTN CHGS" in warnings[0]["issue"]


def test_cleared_cheque_is_not_a_bounce():
    t = txns('2026-04-01,OPENING BALANCE,,,0', '2026-04-02,CHQ DEP 222 - ACME,,500,500')
    assert find_bounces(t) == ([], [])


# ---------- check 3: round trips ----------

def rt_rows(credit_date, debit_date, amount="100000", out_name="ACME"):
    return txns('2026-04-01,OPENING BALANCE,,,0',
                f'{credit_date},NEFT-CR-ACME,,{amount},{amount}',
                f'{debit_date},NEFT-DR-{out_name},{amount},,0')


def test_round_trip_at_exactly_threshold_and_48h_is_flagged():
    trips = find_round_trips(rt_rows("2026-04-02", "2026-04-04"))
    assert trips == [{"credit": 3, "debit": 4, "counterparty": "ACME",
                      "amount": "100000.00", "gap_days": 2}]


@pytest.mark.parametrize("credit_date,debit_date,amount,out_name", [
    ("2026-04-02", "2026-04-05", "100000", "ACME"),     # 3 days: too late
    ("2026-04-02", "2026-04-03", "99999.99", "ACME"),   # below threshold
    ("2026-04-02", "2026-04-03", "100000", "OTHER"),    # different counterparty
])
def test_round_trip_negatives(credit_date, debit_date, amount, out_name):
    assert find_round_trips(rt_rows(credit_date, debit_date, amount, out_name)) == []


def test_debit_before_credit_is_not_a_round_trip():
    t = txns('2026-04-01,OPENING BALANCE,,,500000',
             '2026-04-02,NEFT-DR-ACME,100000,,400000',
             '2026-04-03,NEFT-CR-ACME,,100000,500000')
    assert find_round_trips(t) == []


def test_each_debit_is_used_once():
    t = txns('2026-04-01,OPENING BALANCE,,,0',
             '2026-04-02,NEFT-CR-ACME,,100000,100000',
             '2026-04-02,NEFT-CR-ACME,,100000,200000',
             '2026-04-03,NEFT-DR-ACME,100000,,100000')
    assert len(find_round_trips(t)) == 1


def test_counterparty_normalisation_matches_across_channels():
    assert counterparty("NEFT-CR-MEHTA, JOSHI & CO") == counterparty("UPI-DR-Mehta Joshi & Co")
    assert counterparty('NEFT-CR-M/S "AMBA" DISTRIBUTORS') == "M S AMBA DISTRIBUTORS"
    assert counterparty("GST PMT CHALLAN") is None


# ---------- check 4: integrity ----------

def test_one_wrong_balance_is_reported_once_not_cascaded():
    t = txns('2026-04-01,OPENING BALANCE,,,1000',
             '2026-04-02,A,100,,900',
             '2026-04-03,B,100,,825',     # should be 800: bank printed 25 too much
             '2026-04-04,C,100,,725')     # consistent with the printed 825
    assert find_balance_breaks(t) == [{"line": 4, "expected": "800.00",
                                       "printed": "825.00", "difference": "25.00"}]


# ---------- end to end on the real file ----------

def test_statement_a_end_to_end():
    text = (Path(__file__).parent.parent / "data" / "statement_A.csv").read_text(encoding="utf-8-sig")
    report = analyse(text)
    assert [b["cheque_no"] for b in report["bounces"]] == ["100349", "100357", "100364"]
    assert [(r["credit"], r["debit"]) for r in report["round_trips"]] == [(190, 194), (235, 236)]
    assert [b["line"] for b in report["balance_breaks"]] == [205]
    assert report["monthly_average_balance"]["2026-04"] == "1320098.53"

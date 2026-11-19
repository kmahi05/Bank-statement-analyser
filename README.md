# Bank Statement Analyzer

A small Python program that does an analyst's first pass over an MSME bank statement CSV. It reports:

1. average monthly balance
2. bounced cheques
3. round-trip transactions
4. running-balance breaks

It also lists everything it could not read cleanly.

The core uses only the Python standard library. All money is handled with `decimal.Decimal`; no floats are used anywhere.

## How to run

Requires Python 3.10+.

```bash
# analyse a statement (prints JSON)
python -m analyzer data/statement_A.csv

# write to a file, or change the round-trip rule
python -m analyzer data/statement_A.csv --out output/report.json
python -m analyzer data/statement_A.csv --min-amount 50000 --max-gap-days 3

# tests
pip install -r requirements-dev.txt
pytest

# optional HTTP endpoint
pip install -r requirements-api.txt
uvicorn api:app --reload
curl -F "file=@data/statement_A.csv" http://127.0.0.1:8000/analyze
```

The exit code is `2`, with a message on stderr, if the file can't be analysed at all (missing file, wrong header, not UTF-8).

## Project layout

| File | Responsibility |
|---|---|
| `analyzer/parser.py` | CSV text → `Transaction` records + warnings. All input cleaning happens here. |
| `analyzer/money.py` | Rounding and formatting of `Decimal` amounts. |
| `analyzer/balance.py` | Check 1: average monthly balance. |
| `analyzer/bounces.py` | Check 2: bounced cheques. |
| `analyzer/round_trips.py` | Check 3: round trips (counterparty extraction + matching). |
| `analyzer/integrity.py` | Check 4: running-balance breaks. |
| `analyzer/report.py` | Runs everything and builds the JSON. |
| `analyzer/__main__.py` | Command line. |
| `api.py` | Optional FastAPI endpoint (`POST /analyze`). |

Each check is a pure function that takes the list of transactions. A new check can be added without touching the others.

## Output

This follows the shape in the brief. It adds the following, and changes nothing that was asked for:

- `statement_period`: the first and last dates in the file.
- `monthly_days_counted`: how many days went into each month's average. This makes a partial month visible: September 2026 has 29 days in `statement_A.csv`.
- `bounces[].cheque_no` and `bounces[].amount`.
- `balance_breaks[].difference`: printed minus expected.
- `warnings`: every row that was skipped or looked odd, with its line number, plus file-level notes. Nothing is dropped silently.

All amounts are strings with exactly two decimals, so no precision is lost in JSON.

## Results for `statement_A.csv`

- **Bounces (3):** cheques 100349 (lines 19 → 27 → 28), 100357 (55 → 59 → 60), 100364 (183 → 187 → 188).
- **Round trips (2):**
  - TARA VENTURES ₹3,60,000: credit on line 190, debit on line 194, 2 days apart.
  - KRISHNA TRADELINKS ₹3,60,000: lines 235 → 236, same day.

  HARSH ASSOCIATES ₹1,20,000 (lines 9 and 29) is *not* flagged, because the gap is 11 days.
- **Balance break (1):** line 205. The printed balance is ₹25,000 higher than the previous balance minus the ₹45,000 rent debit.
- **Input issue:** dates are `DD-MM-YYYY`, not `YYYY-MM-DD` as the brief says. This is reported as a warning.

## Decisions and assumptions

Where the brief was ambiguous, this is what I chose and why.

### Reading the file
- **Dates.** `YYYY-MM-DD`, `DD-MM-YYYY` and `DD/MM/YYYY` are accepted. `MM-DD-YYYY` is never tried: these are Indian bank statements, which put the day first. If a date isn't in the spec's format, one warning is added.
- **Amounts.** Surrounding spaces and thousands separators (including Indian grouping, `1,00,000.00`) are removed before parsing straight into `Decimal`. `NaN`/`Infinity` and negative amounts are rejected.
- **Bad rows are skipped and reported, not guessed at.** This covers a row with both debit and credit filled, a row with neither, a missing balance, an unparseable date or amount, or the wrong number of columns. Because a skipped row's movement is missing, the next row will usually show up as a balance break as well, which is the honest result.
- **Blank lines are ignored.** A UTF-8 byte-order mark is removed. Header names are matched case-insensitively. A wrong header is a hard error, because column positions can't be trusted after that.
- **Line numbers are physical file lines**, as the brief requires. The code tracks where each CSV record *starts*, so a blank line or a quoted description containing a newline doesn't shift the numbers.
- **Row order is the file's order** (the bank's order). Out-of-order dates get a warning but are not re-sorted, because the running balance only makes sense in printed order.
- **Description whitespace** is trimmed, and repeated spaces are collapsed.

### 1. Average monthly balance
- Every calendar day from the **first date to the last date in the file** is counted. On a day with no rows, the previous day's closing balance is carried forward.
- The closing balance for a day is the **printed** balance on that day's last row, as the brief specifies, even if that row is a balance break.
- **Partial months are not padded.** The statement ends on 29 Sep, so September is averaged over 29 days. Carrying the balance to 30 Sep would assume nothing happened that day, and the data doesn't show that. `monthly_days_counted` makes this visible. If the lender's rule is "always use the full month", this is a one-line change in `balance.py` (run the loop to the end of the last month).
- Averages are rounded to paise with half-up rounding.

### 2. Bounced cheques
- Rows are linked by **cheque number**: `CHQ DEP <no>` → `CHQ RTN <no>` → `RTN CHGS <no>`.
- **One entry per cheque number** ("count instruments, not rows"). If the same cheque is returned again, it is still counted once, and a warning is added.
- A return is linked to the **most recent earlier deposit** of that cheque number.
- If a return has no deposit in the file (for example, a deposit made before the statement started), the bounce is still reported with `"deposit": null`, and a warning is added.
- A missing fee row gives `"charge": null` and a warning.
- If the returned amount differs from the deposited amount, there is a warning, but the bounce is still reported.
- A fee row with no return before it only produces a warning.

### 3. Round trips
- **Rule:** a **credit** from counterparty X, followed by a **debit** to the same X, for **exactly the same amount**, **at least ₹1,00,000** (inclusive), and **at most 2 calendar days** later.
- **48 hours = 2 calendar days.** The file has dates but no times, so "within 48 hours" can only be judged on dates. A gap of 0, 1 or 2 days is flagged. The real gap could be up to almost 72 hours, so this errs on the side of flagging. The analyst confirms.
- **Direction matters.** The money must come *in first* and then go back out. Paying a supplier and then receiving a refund is not the inflation pattern.
- **One-to-one matching.** Each debit is paired with at most one credit. Each credit takes the earliest eligible debit after it in the file. Same-day pairs need the debit to come after the credit in the file.
- **Counterparty extraction.** The name is taken from the description patterns in this bank's format:
  - `NEFT|RTGS|IMPS|UPI` + `CR|DR` + name
  - `CHQ DEP <no> - name`
  - `POS PURCHASE name`

  It is then normalised: uppercased, every character except letters, digits and `&` becomes a space, and repeated spaces are collapsed. So `"MEHTA, JOSHI & CO"` and `MEHTA JOSHI & CO` match. Rows with no recognisable counterparty (GST, salary, EMI, utility bills) are never paired.
- Both the threshold and the window can be changed from the command line.

### 4. Data integrity
- `expected = previous printed balance + credit − debit`, compared exactly with `Decimal`.
- The comparison uses the **previous printed balance**, not my own running total. This way one wrong row is reported once. With a running total, every row after line 205 would be reported, which hides where the actual problem is.
- The OPENING BALANCE row is the starting point and can't be checked itself.

## Tests

`pytest` runs 19 core tests and 2 API tests. Each test pins down a decision above:
- quoted commas
- line numbers across blank and multi-line rows
- carry-forward and last-row-of-day in the average
- half-up rounding
- a bounce with a missing fee row
- the round-trip boundaries: exactly ₹1,00,000 and exactly 2 days pass, 3 days and ₹99,999.99 don't
- direction, and one-to-one matching
- a balance break that doesn't cascade

There is also an end-to-end test on `statement_A.csv`. I checked the monthly averages separately with an integer-paise calculation.

## What I would do with more time

- **Better counterparty matching.** A per-bank set of description patterns, fuzzy matching (`PVT LTD` vs `PRIVATE LIMITED`), and matching on account number or IFSC when the bank prints them.
- **Round trips that are split or in other forms.** For example, ₹3,60,000 in and 2 × ₹1,80,000 out, near-equal amounts, or chains through a third party.
- **Duplicate-row detection**, and checking that the statement covers contiguous dates.
- **Support for other bank formats**: a single amount column with a Dr/Cr flag, separate value date and transaction date, and PDF statements.
- **A full-month option** for the average balance, and summary metrics lenders also use (credit turnover, EMI and bounce counts, cash-deposit share).
- A Dockerfile and CI.

## Use of AI tools
I used Claude (Anthropic) to help structure the solution, to draft the code, tests and this README . I reviewed every file, ran the tests and checked the outputs against the CSV by hand: the bounces, round trips and the line-205 break, plus a separate recomputation of the monthly averages. I understand and can modify the changes.

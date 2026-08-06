import os
import re

# Ensure the '../data/...' relative paths used here resolve regardless of where
# this module is imported from.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import openpyxl

import bloomberg_tickers
import entrypoint
import expiry
from bloomberg_fetch import fetch_blocks

TEMPLATE_FILE = '../data/template.txt'
EXCEL_FILE = '../data/numbers.xlsx'
BLOOMBERG_TICKERS_FILE = '../data/bloomberg_tickers.txt'
OUTPUT_FILE = '../data/final_output.txt'

# This module used to rebuild its own derived files when original_input.txt
# looked newer by mtime. That check has been removed: run_pipeline.py now
# rebuilds the whole chain from original_input.txt unconditionally, and mtime
# comparison was unreliable here anyway — the repo lives in OneDrive, whose
# sync can land a fresh input with an mtime older than the derived files, in
# which case the check silently reused stale data.


def get_ticker(line):
    match = re.match(r'^([A-Z]+)\s+', line.strip())
    return match.group(1) if match else None


def parse_excel_file(filepath):
    """
    Returns a list of blocks, one per ticker, in order.
    Each block is a list of (oi_change, volume) tuples.
    Rows where column A is '###' act as ticker separators.
    """
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.active

    blocks = []
    current = []
    for row in ws.iter_rows(min_row=1, values_only=True):
        col_a = str(row[0]).strip() if row[0] is not None else ''
        col_b = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ''

        if col_a == '###':
            if current:
                blocks.append(current)
                current = []
        elif col_a:
            current.append((col_a, col_b))

    if current:
        blocks.append(current)

    return blocks


def main(from_excel=False, as_of=None):
    with open(TEMPLATE_FILE, 'r') as f:
        template_lines = f.readlines()

    # Collect unique tickers in order of first appearance in OI Change lines
    tickers_ordered = []
    seen = set()
    for line in template_lines:
        if 'OI Change:' in line:
            ticker = get_ticker(line)
            if ticker and ticker not in seen:
                tickers_ordered.append(ticker)
                seen.add(ticker)

    # Map each ticker to the line indices of its OI Change lines
    ticker_oi_indices = {t: [] for t in tickers_ordered}
    for i, line in enumerate(template_lines):
        if 'OI Change:' in line:
            ticker = get_ticker(line)
            if ticker in ticker_oi_indices:
                ticker_oi_indices[ticker].append(i)

    if not tickers_ordered:
        print(f"No OI Change lines in {TEMPLATE_FILE} — nothing to fill.")
        with open(OUTPUT_FILE, 'w') as f:
            f.writelines(template_lines)
        print(f"Output written to {OUTPUT_FILE}")
        return

    if from_excel:
        print(f"Reading OI/volume data from Excel: {EXCEL_FILE}")
        data_blocks = parse_excel_file(EXCEL_FILE)
    else:
        entrypoint.check_alignment(
            [(t, len(ticker_oi_indices[t])) for t in tickers_ordered],
            bloomberg_tickers.ticker_order(BLOOMBERG_TICKERS_FILE),
            BLOOMBERG_TICKERS_FILE)
        print(f"Fetching OI/volume data from Bloomberg for {BLOOMBERG_TICKERS_FILE}")
        data_blocks = fetch_blocks(BLOOMBERG_TICKERS_FILE)

    # Validate ticker count
    n_tickers = len(tickers_ordered)
    n_blocks = len(data_blocks)
    if n_tickers != n_blocks:
        print(f"ERROR: Ticker count mismatch — template has {n_tickers} tickers, "
              f"data source has {n_blocks} blocks.")
        print(f"  Template tickers: {tickers_ordered}")
        print(f"  Processing first {min(n_tickers, n_blocks)} matching pairs.")
    else:
        print(f"Ticker count OK: {n_tickers} tickers.")

    # Build line_index -> (oi, volume) substitution map
    substitutions = {}
    for i in range(min(n_tickers, n_blocks)):
        ticker = tickers_ordered[i]
        oi_indices = ticker_oi_indices[ticker]
        rows = data_blocks[i]

        if len(oi_indices) != len(rows):
            print(f"WARNING: {ticker} has {len(oi_indices)} OI Change line(s) "
                  f"but {len(rows)} data row(s) — filling what matches.")

        for j, idx in enumerate(oi_indices):
            if j < len(rows):
                substitutions[idx] = rows[j]
            else:
                print(f"  Skipping {ticker} OI Change line {j + 1} (line {idx + 1}): no data provided.")

    # Expired options have no open interest — override to 0.
    zeroed = expiry.zero_expired(substitutions, template_lines, as_of)
    if zeroed:
        print(f"Overrode {zeroed} expired option(s) to OI Change: 0.")

    # Write output
    output_lines = []
    for i, line in enumerate(template_lines):
        if i in substitutions:
            oi, vol = substitutions[i]
            stripped = line.rstrip('\n').rstrip()
            output_lines.append(f"{stripped} {oi} / Volume = {vol}\n")
        else:
            output_lines.append(line)

    with open(OUTPUT_FILE, 'w') as f:
        f.writelines(output_lines)

    filled = len(substitutions)
    total_oi = sum(len(v) for v in ticker_oi_indices.values())
    print(f"\nFilled {filled}/{total_oi} OI Change lines.")
    print(f"Output written to {OUTPUT_FILE}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description="Step 3 of the OI/Volume report: fill OI change + volume "
                    "into template.txt -> final_output.txt. Reads template.txt "
                    "as-is, so edits made to it are preserved. Run "
                    "run_pipeline.py to do the whole chain instead.")
    parser.add_argument(
        '--from-excel', action='store_true',
        help="Read OI/volume from numbers.xlsx instead of querying Bloomberg.")
    args = parser.parse_args()
    main(from_excel=args.from_excel)

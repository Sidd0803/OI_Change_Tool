import argparse
import os
import re

# Ensure the '../data/...' relative paths used here and by every step we call
# into (template.py, bloomberg_tickers.py) resolve regardless of where this
# script is launched from.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import openpyxl

import bloomberg_tickers
import template as template_mod
from bloomberg_fetch import fetch_blocks

INPUT_FILE = '../data/original_input.txt'
TEMPLATE_FILE = '../data/template.txt'
FILTERED_FILE = '../data/filtered_input.txt'
EXCEL_FILE = '../data/numbers.xlsx'
BLOOMBERG_TICKERS_FILE = '../data/bloomberg_tickers.txt'
OUTPUT_FILE = '../data/final_output.txt'


def _is_stale(derived, source):
    """True if `derived` is missing or older than `source`."""
    if not os.path.exists(derived):
        return True
    return os.path.getmtime(source) > os.path.getmtime(derived)


def refresh_derived_files():
    """
    Rebuild the derived files whose ultimate source is original_input.txt:

        original_input.txt -> template.txt -> filtered_input.txt -> bloomberg_tickers.txt

    Each step runs only when its input is newer than its output, so a hand-edit
    to template.txt is preserved until original_input.txt changes again.
    """
    if not os.path.exists(INPUT_FILE):
        print(f"WARNING: {INPUT_FILE} not found — using {TEMPLATE_FILE} as-is.")
        return

    if _is_stale(TEMPLATE_FILE, INPUT_FILE):
        print(f"{TEMPLATE_FILE} is out of date — rebuilding from {INPUT_FILE}")
        template_mod.template(INPUT_FILE, TEMPLATE_FILE)
    else:
        print(f"{TEMPLATE_FILE} is up to date with {INPUT_FILE}")

    if _is_stale(FILTERED_FILE, TEMPLATE_FILE):
        bloomberg_tickers.filter_oi_change_lines(TEMPLATE_FILE, FILTERED_FILE)

    if _is_stale(BLOOMBERG_TICKERS_FILE, FILTERED_FILE):
        bloomberg_tickers.process_file_to_bloomberg(FILTERED_FILE, BLOOMBERG_TICKERS_FILE)


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


def main(from_excel=False, refresh=True):
    if refresh:
        refresh_derived_files()

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
    parser = argparse.ArgumentParser(
        description="Generate final_output.txt (OI Change report for Element "
                    "Chat) from template.txt, sourcing OI change + volume from "
                    "Bloomberg (default) or numbers.xlsx.")
    parser.add_argument(
        '--from-excel', action='store_true',
        help="Read OI/volume from numbers.xlsx instead of querying Bloomberg.")
    parser.add_argument(
        '--no-refresh', action='store_true',
        help="Use template.txt as-is instead of rebuilding it from "
             "original_input.txt when that file is newer.")
    args = parser.parse_args()
    main(from_excel=args.from_excel, refresh=not args.no_refresh)

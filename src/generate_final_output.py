import re
import openpyxl

TEMPLATE_FILE = 'template.txt'
EXCEL_FILE = 'numbers.xlsx'
OUTPUT_FILE = 'final_output.txt'


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


def main():
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

    data_blocks = parse_excel_file(EXCEL_FILE)

    # Validate ticker count
    n_tickers = len(tickers_ordered)
    n_blocks = len(data_blocks)
    if n_tickers != n_blocks:
        print(f"ERROR: Ticker count mismatch — template has {n_tickers} tickers, "
              f"Excel has {n_blocks} blocks.")
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
    main()

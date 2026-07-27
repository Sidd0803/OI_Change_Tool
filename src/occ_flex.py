"""
OCC Flex color pipeline.

Extracts flex color blocks from a day's Bloomberg chat log, downloads the
OCC equity Flex Open Interest reports for the trade date and the prior
business day, diffs them to get the OI change per series, and writes a
recap-style output: each flex trade line followed by
"OI Change: <n> / Volume = <v>".

The OCC report gives OI *levels* only, so change = OI(trade date) minus
OI(previous business day). The report for activity date T is published
early the following morning, so this runs on the same next-morning
cadence as the regular recap.

Usage:
    python occ_flex.py --input <chat.txt> [--date M/D/YYYY] [--output <path>]
"""

import argparse
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta

_ORIG_CWD = os.getcwd()
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEPARATOR = '-' * 33 + '\n'

OCC_URL = ('https://marketdata.theocc.com/flex-reports'
           '?reportType=OI&optionType=E&reportDate={yyyymmdd}')
OCC_CACHE_DIR = '../data/occ'
OUTPUT_FILE = '../data/flex_output.txt'

# `1AAL     C   09 02 2026  00021 960      0.0450     52850`
# Leading digit is the OCC flex prefix: 1 = American equity (a.m. settled for
# index), 2 = European equity, 3 = American index p.m., 4 = European index p.m.
# ETF flex (e.g. SMH) shows up under the index prefixes, so a chat line's
# exercise style maps to two possible prefixes rather than one.
PREFIXES = {'Amer': ('1', '3'), 'Euro': ('2', '4')}

REPORT_ROW_RE = re.compile(
    r'^\s+(\d[A-Z][A-Z0-9.]*)\s+([CP])\s+'
    r'(\d{2}) (\d{2}) (\d{4})\s+'
    r'(\d{5}) (\d{3})\s+\S+\s+(\d+)\s*$')

# `10:11:39 Color - SNDK Flex:`  /  `13:08:36 Color - TSM Listed vs Flex:`
FLEX_HEADER_RE = re.compile(
    r'^\d{2}:\d{2}:\d{2}\s+Color\s*-\s+(\S+)\s+(?:Listed vs )?Flex:\s*$')

TIMESTAMP_RE = re.compile(r'^\d{2}:\d{2}:\d{2}\s')

# `07/31/2026 1500.01 Amer PM Put 3,000x traded 198.59, vs 1313.40 stk 65d (OI = 3,000)`
FLEX_TRADE_RE = re.compile(
    r'^(\d{2}/\d{2}/\d{4})\s+([\d,]+(?:\.\d+)?)\s+(Amer|Euro)\s+(AM|PM)\s+'
    r'(Put|Call)\s+([\d,]+)x\s+traded\s+([\d.]+)(.*)$')

OI_ANNOTATION_RE = re.compile(r'[,\s]*\(OI\s*=\s*[^)]*\)')


def previous_business_day(ref=None):
    """Return the most recent weekday before `ref` (default: today)."""
    d = (ref or date.today()) - timedelta(days=1)
    while d.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        d -= timedelta(days=1)
    return d


def download_flex_oi(report_date):
    """Download (or reuse cached) OCC equity flex OI report; return its path."""
    os.makedirs(OCC_CACHE_DIR, exist_ok=True)
    path = os.path.join(OCC_CACHE_DIR,
                        f"flex_oi_{report_date.strftime('%Y%m%d')}.txt")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        print(f"Using cached OCC report {path}")
        return path

    url = OCC_URL.format(yyyymmdd=report_date.strftime('%Y%m%d'))
    print(f"Downloading OCC flex OI report for {report_date} ...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()

    text = data.decode('utf-8', errors='replace')
    if not text.strip() or text.lstrip().lower().startswith(('<!doctype', '<html')):
        raise RuntimeError(
            f"OCC returned no report for {report_date} (holiday or not yet "
            f"published). URL: {url}")

    with open(path, 'w') as f:
        f.write(text)
    print(f"Saved {len(data):,} bytes to {path}")
    return path


def parse_flex_oi_report(path):
    """
    Returns {(symbol, 'C'|'P', expiry_date, strike): open_interest}.
    `symbol` keeps the OCC flex prefix digit (1 = Amer equity, 2 = Euro).
    """
    oi = {}
    with open(path, 'r') as f:
        for line in f:
            m = REPORT_ROW_RE.match(line)
            if not m:
                continue
            symbol, right, mo, day, yr, dollars, frac, open_int = m.groups()
            strike = round(int(dollars) + int(frac) / 1000, 3)
            expiry = date(int(yr), int(mo), int(day))
            oi[(symbol, right, expiry, strike)] = int(open_int)
    return oi


def series_keys(trade):
    """
    Candidate OCC report keys for a parsed chat trade, in preference order.
    The exercise style narrows the flex prefix to two options (equity vs
    index/ETF numbering); which one a name uses isn't knowable from the chat.
    """
    right = 'C' if trade['right'] == 'Call' else 'P'
    return [(p + trade['ticker'], right, trade['expiry'], trade['strike'])
            for p in PREFIXES[trade['exercise']]]


def resolve_key(trade, *oi_maps):
    """First candidate key present in any report, else the primary candidate."""
    candidates = series_keys(trade)
    for key in candidates:
        if any(key in m for m in oi_maps):
            return key
    return candidates[0]


def parse_chat(path):
    """
    Extract flex color blocks from a raw Bloomberg chat log.

    Returns a list of blocks: {'ticker': str, 'trades': [trade, ...]} where
    each trade has ticker/expiry/strike/exercise/ampm/right/qty/price and
    `text` (the original line with any hand-filled "(OI = n)" stripped).
    Listed legs inside "Listed vs Flex" blocks and regular color are ignored.
    """
    with open(path, 'r') as f:
        lines = f.readlines()

    blocks = []
    current = None
    for line in lines:
        header = FLEX_HEADER_RE.match(line)
        if header:
            current = {'ticker': header.group(1), 'trades': []}
            blocks.append(current)
            continue
        if current is None:
            continue
        if TIMESTAMP_RE.match(line):  # next chat message ends the block
            current = None
            continue
        m = FLEX_TRADE_RE.match(line.strip())
        if not m:
            continue  # blank lines, listed legs, "live; stk ref ..." etc.
        expiry_s, strike_s, exercise, ampm, right, qty_s, price_s, _tail = m.groups()
        text = OI_ANNOTATION_RE.sub('', line.strip()).rstrip(' ,')
        current['trades'].append({
            'ticker': current['ticker'],
            'expiry': datetime.strptime(expiry_s, '%m/%d/%Y').date(),
            'strike': round(float(strike_s.replace(',', '')), 3),
            'exercise': exercise,
            'ampm': ampm,
            'right': right,
            'qty': int(qty_s.replace(',', '')),
            'price': price_s,
            'text': text,
        })

    return [b for b in blocks if b['trades']]


def compute_oi_changes(blocks, trade_date):
    """
    Annotate every trade with `oi_change` (OCC day-over-day diff) and
    `volume` (total chat qty traded in that series across all blocks).
    """
    today_oi = parse_flex_oi_report(download_flex_oi(trade_date))
    prev_oi = parse_flex_oi_report(
        download_flex_oi(previous_business_day(trade_date)))

    volume = {}
    for block in blocks:
        for t in block['trades']:
            t['key'] = resolve_key(t, today_oi, prev_oi)
            volume[t['key']] = volume.get(t['key'], 0) + t['qty']

    for block in blocks:
        for t in block['trades']:
            key = t['key']
            if key not in today_oi and key not in prev_oi:
                print(f"WARNING: {t['ticker']} {t['right']} {t['expiry']} "
                      f"{t['strike']} {t['exercise']} not found in either OCC "
                      f"report (tried {[k[0] for k in series_keys(t)]}).",
                      file=sys.stderr)
            t['oi_change'] = today_oi.get(key, 0) - prev_oi.get(key, 0)
            t['volume'] = volume[key]


def write_output(blocks, path=OUTPUT_FILE):
    lines = []
    for block in blocks:
        lines.append(f"Color - {block['ticker']} Flex:\n")
        for t in block['trades']:
            lines.append(f"{t['text']} OI Change: {t['oi_change']} "
                         f"/ Volume = {t['volume']}\n")
        lines.append(SEPARATOR)

    with open(path, 'w') as f:
        f.writelines(lines)
    print(f"Output written to {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract flex color from a Bloomberg chat log and fill "
                    "OI change from OCC flex open interest reports.")
    parser.add_argument('--input', required=True,
                        help="Path to the day's chat log text file.")
    parser.add_argument('--date',
                        help="Trade date M/D/YYYY (default: previous "
                             "business day).")
    parser.add_argument('--output', default=OUTPUT_FILE,
                        help=f"Output path (default: {OUTPUT_FILE}).")
    args = parser.parse_args()

    trade_date = (datetime.strptime(args.date, '%m/%d/%Y').date()
                  if args.date else previous_business_day())
    print(f"Trade date: {trade_date} (baseline: "
          f"{previous_business_day(trade_date)})")

    input_path = args.input
    if not os.path.isabs(input_path) and not os.path.exists(input_path):
        input_path = os.path.join(_ORIG_CWD, args.input)

    blocks = parse_chat(input_path)
    if not blocks:
        print("No flex color blocks found in input.")
        return
    n_trades = sum(len(b['trades']) for b in blocks)
    print(f"Found {len(blocks)} flex block(s), {n_trades} trade line(s): "
          + ', '.join(b['ticker'] for b in blocks))

    compute_oi_changes(blocks, trade_date)
    write_output(blocks, args.output)


if __name__ == '__main__':
    main()

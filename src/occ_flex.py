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

# OCC answers an unavailable date with HTTP 200 and the body "File requested
# does not exist.", so the status code proves nothing — the report header is
# what tells us we actually got a report. Without this check a bad date parses
# to zero rows and every OI change silently reads as 0.
REPORT_MARKER = 'FLEX OPEN INTEREST REPORT'

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


def _is_report(text):
    return REPORT_MARKER in text


def download_flex_oi(report_date):
    """Download (or reuse cached) OCC equity flex OI report; return its path."""
    os.makedirs(OCC_CACHE_DIR, exist_ok=True)
    path = os.path.join(OCC_CACHE_DIR,
                        f"flex_oi_{report_date.strftime('%Y%m%d')}.txt")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, 'r') as f:
            if _is_report(f.read(4096)):
                print(f"Using cached OCC report {path}")
                return path
        print(f"Cached {path} isn't a valid report — re-downloading.")

    url = OCC_URL.format(yyyymmdd=report_date.strftime('%Y%m%d'))
    print(f"Downloading OCC flex OI report for {report_date} ...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()

    text = data.decode('utf-8', errors='replace')
    if not _is_report(text):
        detail = ' '.join(text.split())[:120] or '(empty response)'
        raise RuntimeError(
            f"OCC has no flex OI report for {report_date} — it may be a "
            f"weekend/holiday, or not published yet (reports appear the "
            f"morning after the activity date). OCC said: {detail!r}")

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


def report_date_for(trade_date):
    """
    OCC publishes activity date T on the morning of T+1, so the open interest
    a trade on T moved is the difference between the T and T-1 reports.
    Returns (current, baseline).
    """
    return trade_date, previous_business_day(trade_date)


def _ordinal(day):
    if 11 <= day <= 13:
        return f"{day}th"
    return f"{day}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th') }"


def format_expiry(d):
    """
    Weeklies read as the chat writes them ('Jul27th'); standard monthly
    expiries (third Friday) collapse to just the month ('Aug').
    """
    mon = d.strftime('%b')
    is_third_friday = d.weekday() == 4 and 15 <= d.day <= 21
    return mon if is_third_friday else f"{mon}{_ordinal(d.day)}"


def format_strike(strike):
    """1395.0 -> '1395', 197.51 -> '197.51'."""
    return f"{strike:g}"


def annotate_oi(blocks, trade_date):
    """
    Annotate every trade with `oi_change`, the day-over-day move in OCC open
    interest for its series: level on the trade date minus level the previous
    business day.
    """
    current_date, baseline_date = report_date_for(trade_date)
    current = parse_flex_oi_report(download_flex_oi(current_date))
    baseline = parse_flex_oi_report(download_flex_oi(baseline_date))

    for block in blocks:
        for t in block['trades']:
            t['key'] = resolve_key(t, current, baseline)

    for block in blocks:
        for t in block['trades']:
            key = t['key']
            if key not in current and key not in baseline:
                print(f"WARNING: {t['ticker']} {t['right']} {t['expiry']} "
                      f"{t['strike']} {t['exercise']} not found in either OCC "
                      f"report (tried {[k[0] for k in series_keys(t)]}) — "
                      f"reporting OI Change: 0.", file=sys.stderr)
            t['oi_change'] = current.get(key, 0) - baseline.get(key, 0)


def summary_line(t):
    """'SNDK Jul27th 1395 Euro PM Call OI Change: 1223'"""
    return (f"{t['ticker']} {format_expiry(t['expiry'])} "
            f"{format_strike(t['strike'])} {t['exercise']} {t['ampm']} "
            f"{t['right']} OI Change: {t['oi_change']}")


def write_output(blocks, path=OUTPUT_FILE):
    lines = []
    for block in blocks:
        lines.append(f"Color - {block['ticker']} Flex:\n")
        lines.append("\n")
        for t in block['trades']:
            lines.append(f"{t['text']}\n")
        lines.append("\n")
        for t in block['trades']:
            lines.append(f"{summary_line(t)}\n")
        lines.append(SEPARATOR)

    with open(path, 'w') as f:
        f.writelines(lines)
    print(f"Output written to {path}")


def resolve_input_path(path):
    """Let a relative --input resolve against the caller's original cwd."""
    if not os.path.isabs(path) and not os.path.exists(path):
        return os.path.join(_ORIG_CWD, path)
    return path


def run(input_file, trade_date=None, output=OUTPUT_FILE):
    """
    Full flex flow: chat log -> OCC open interest -> flex_output.txt.
    Returns the parsed blocks (empty list when the log has no flex color).
    """
    trade_date = trade_date or previous_business_day()
    current_date, baseline_date = report_date_for(trade_date)
    print(f"Trades from {trade_date} — OI change = OCC report {current_date} "
          f"minus {baseline_date}.")

    blocks = parse_chat(resolve_input_path(input_file))
    if not blocks:
        print("No flex color blocks found in input — nothing to do.")
        return blocks

    n_trades = sum(len(b['trades']) for b in blocks)
    print(f"Found {len(blocks)} flex block(s), {n_trades} trade line(s): "
          + ', '.join(b['ticker'] for b in blocks))

    annotate_oi(blocks, trade_date)
    write_output(blocks, output)
    return blocks


if __name__ == '__main__':
    import entrypoint
    entrypoint.refuse('occ_flex.py')

import re

# Regex building blocks
_MONTH = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
EXPIRY_RE = rf'(?:\d{{1,2}})?{_MONTH}\w*'  # Apr, Apr24th, May1st, Dec27, 8May, 6May, 5Jun, etc.
STRIKE_RE = r'\d+(?:\.\d+)?'         # 230, 12.5, 277.50, etc.
OPT_RE    = r'(?:Ca[a-zA-Z]+|Puts?)' # Call/Calls/CAll/Cakk  or  Put/Puts
RATIO_RE  = r'(?:\d[\d.]*x\d[\d.]*\s+)?'   # optional 1x2, 1x1.5, etc.
SPREAD_KW = r'(?:(CS|PS|RR)|(Call\s+Spread|Put\s+Spread|Strangle))'


def _normalize(s):
    """'Calls' → 'Call', 'Puts' → 'Put', typos like 'Cakk' → 'Call'."""
    sl = s.lower()
    if sl.startswith('ca'):
        return 'Call'
    if sl.startswith('pu'):
        return 'Put'
    return None


def _spread_type(m, g4, g5):
    """Return canonical spread key from two alternative capture groups."""
    raw = (m.group(g4) or m.group(g5)).upper().replace(' ', '')
    # CS → CS, PS → PS, RR → RR, CALLSPREAD → CS, PUTSPREAD → PS
    if raw in ('CALLSPREAD',):
        return 'CS'
    if raw in ('PUTSPREAD',):
        return 'PS'
    return raw  # CS, PS, RR


def _parse_segment(seg, ticker):
    """
    Return list of formatted option strings for one comma-segment.

    Handles:
      A. EXPIRY STRIKE1/STRIKE2 [ratio] CS|PS|RR|Call Spread|Put Spread
      B. EXPIRY1/EXPIRY2 STRIKE CS|PS|RR|Call Spread|Put Spread
      C. EXPIRY STRIKE Call/Put (single option, including typos)
    """
    # ── Pattern A: same expiry, two strikes ──────────────────────────────────
    m = re.search(
        rf'({EXPIRY_RE})\s+({STRIKE_RE})\s*/\s*({STRIKE_RE})\s+{RATIO_RE}{SPREAD_KW}',
        seg, re.IGNORECASE
    )
    if m:
        expiry, s1_str, s2_str = m.group(1), m.group(2), m.group(3)
        kind = _spread_type(m, 4, 5)
        s1, s2 = float(s1_str), float(s2_str)
        if kind in ('RR', 'STRANGLE'):
            low, high = (s1_str, s2_str) if s1 <= s2 else (s2_str, s1_str)
            return [f"{ticker} {expiry} {low} Put",
                    f"{ticker} {expiry} {high} Call"]
        opt = 'Call' if kind == 'CS' else 'Put'
        return [f"{ticker} {expiry} {s1_str} {opt}",
                f"{ticker} {expiry} {s2_str} {opt}"]

    # ── Pattern D: two expiries, two different strikes ───────────────────────
    m = re.search(
        rf'({EXPIRY_RE})\s+({STRIKE_RE})\s*/\s*({EXPIRY_RE})\s+({STRIKE_RE})\s+{SPREAD_KW}',
        seg, re.IGNORECASE
    )
    if m:
        exp1, s1, exp2, s2 = m.group(1), m.group(2), m.group(3), m.group(4)
        kind = _spread_type(m, 5, 6)
        if kind in ('RR', 'STRANGLE'):
            return [f"{ticker} {exp1} {s1} Put",
                    f"{ticker} {exp2} {s2} Call"]
        opt = 'Call' if kind == 'CS' else 'Put'
        return [f"{ticker} {exp1} {s1} {opt}",
                f"{ticker} {exp2} {s2} {opt}"]

    # ── Pattern B: two expiries, same strike ─────────────────────────────────
    m = re.search(
        rf'({EXPIRY_RE})\s*/\s*({EXPIRY_RE})\s+({STRIKE_RE})\s+{SPREAD_KW}',
        seg, re.IGNORECASE
    )
    if m:
        exp1, exp2, strike = m.group(1), m.group(2), m.group(3)
        kind = _spread_type(m, 4, 5)
        if kind in ('RR', 'STRANGLE'):
            return [f"{ticker} {exp1} {strike} Put",
                    f"{ticker} {exp2} {strike} Call"]
        opt = 'Call' if kind == 'CS' else 'Put'
        return [f"{ticker} {exp1} {strike} {opt}",
                f"{ticker} {exp2} {strike} {opt}"]

    # ── Pattern E: straddle (same expiry, same strike → Put + Call) ─────────
    m = re.search(
        rf'({EXPIRY_RE})\s+({STRIKE_RE})\s+Straddle',
        seg, re.IGNORECASE
    )
    if m:
        return [f"{ticker} {m.group(1)} {m.group(2)} Put",
                f"{ticker} {m.group(1)} {m.group(2)} Call"]

    # ── Pattern C: single option ─────────────────────────────────────────────
    m = re.search(
        rf'({EXPIRY_RE})\s+({STRIKE_RE})\s+({OPT_RE})',
        seg, re.IGNORECASE
    )
    if m:
        opt = _normalize(m.group(3))
        if opt:
            return [f"{ticker} {m.group(1)} {m.group(2)} {opt}"]

    return []


def parse_line_options(line):
    """
    Return all option strings found on a line, preserving input order and
    de-duplicating identical entries (e.g. two identical puts on one line).
    """
    line = line.strip()
    if not line:
        return []

    # Ticker is the leading all-caps word.
    tm = re.match(r'^([A-Z]+)\s+', line)
    if not tm:
        return []
    ticker = tm.group(1)

    # Split by commas to isolate each individual option clause.
    segments = re.split(r',\s*', line)

    seen, results = set(), []
    for seg in segments:
        for opt in _parse_segment(seg, ticker):
            if opt not in seen:
                seen.add(opt)
                results.append(opt)
    return results


_COLOR_RE = re.compile(r'Color\s*-\s+', re.IGNORECASE)
_TIME_RE  = re.compile(r'^\d{2}:\d{2}:\d{2}\s+')

# Matches "Color - TICKER:" with nothing meaningful after the colon (multi-line block header).
_MULTILINE_HEADER_RE = re.compile(r'Color\s*-\s+([A-Za-z]+):\s*$', re.IGNORECASE)

# Matches a line that starts with an expiry+strike+call/put (option detail line in a block).
_OPTION_LINE_START_RE = re.compile(rf'^\s*{EXPIRY_RE}\s+{STRIKE_RE}\s+{OPT_RE}', re.IGNORECASE)


def extract_color_lines(raw_lines):
    """
    From a raw chat log, return (timestamp, cleaned_trade_line) tuples.
    Finds every line containing 'Color -', captures any leading HH:MM:SS
    timestamp, and returns the text after 'Color - '.
    Skips multi-line block headers (Color - TICKER:) — those are handled
    by extract_multiline_color_blocks.
    """
    result = []
    for line in raw_lines:
        line = line.rstrip('\n')
        m = _COLOR_RE.search(line)
        if m:
            if _MULTILINE_HEADER_RE.search(line):
                continue
            cleaned = line[m.end():]
            ts_match = _TIME_RE.match(line)
            timestamp = ts_match.group(0).strip() if ts_match else ''
            result.append((timestamp, cleaned))
    return result


def extract_multiline_color_blocks(raw_lines):
    """
    From a raw chat log, detect 'Color - TICKER:' header lines followed by
    option detail lines on subsequent lines.

    Collects lines after the header until a blank line or a new 'Color -' line.
    Lines matching EXPIRY STRIKE Call/Put are parsed as options; non-option
    lines (e.g. 'elec live; stk ref 308.15') are included in the display text
    but skipped for parsing.

    Returns (timestamp, display_text, options) tuples where display_text is
    the full block and options is the list of parsed option strings.
    """
    result = []
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i].rstrip('\n')
        m = _MULTILINE_HEADER_RE.search(line)
        if m:
            ticker = m.group(1).upper()
            ts_match = _TIME_RE.match(line)
            timestamp = ts_match.group(0).strip() if ts_match else ''

            block_lines = []
            j = i + 1
            while j < len(raw_lines):
                next_line = raw_lines[j].rstrip('\n')
                if not next_line.strip():
                    break
                if _COLOR_RE.search(next_line):
                    break
                block_lines.append(next_line)
                j += 1

            display_text = '\n'.join([f"{ticker}:"] + block_lines)

            options, seen = [], set()
            for bl in block_lines:
                if _OPTION_LINE_START_RE.match(bl):
                    for opt in parse_line_options(f"{ticker} {bl.strip()}"):
                        if opt not in seen:
                            seen.add(opt)
                            options.append(opt)

            result.append((timestamp, display_text, options))
            i = j
        else:
            i += 1
    return result


def template(input_file, output_file):
    """
    Reads a raw chat log, extracts Color trade lines, strips timestamps and
    the 'Color -' prefix, then for each cleaned line writes:
        {cleaned trade line}
        {blank line}
        {TICKER EXPIRY STRIKE Type OI Change:}   <- one per parsed option
        ---------------------------------

    Lines are sorted by ticker alphabetically, then by timestamp within each ticker.
    Returns the number of color lines processed.
    """
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            raw_lines = f.readlines()

        # Single-line entries: (timestamp, display_text, None) — options parsed at write time.
        single_entries = [
            (ts, line, None) for ts, line in extract_color_lines(raw_lines)
        ]
        # Multi-line block entries: (timestamp, display_text, options_list).
        multi_entries = extract_multiline_color_blocks(raw_lines)

        all_entries = single_entries + multi_entries

        def sort_key(item):
            timestamp, display_text, _ = item
            first_line = display_text.split('\n')[0]
            tm = re.match(r'^([A-Za-z]+)', first_line)
            ticker = tm.group(1).upper() if tm else ''
            return (ticker, timestamp)

        all_entries.sort(key=sort_key)

        with open(output_file, 'w', encoding='utf-8') as f:
            for _timestamp, display_text, options in all_entries:
                f.write(display_text + '\n\n')
                if options is None:
                    options = parse_line_options(display_text)
                for opt in options:
                    f.write(f"{opt} OI Change:\n")
                f.write("---------------------------------\n")

        print(f"Processed {len(all_entries)} color lines")
        print(f"Output written to: {output_file}")
        return len(all_entries)

    except FileNotFoundError:
        raise FileNotFoundError(f"Input file not found: {input_file}")
    except Exception as e:
        raise Exception(f"Error processing file: {e}")


if __name__ == "__main__":
    template("../data/original_input.txt", "../data/template.txt")

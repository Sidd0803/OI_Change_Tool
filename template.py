import re

# Regex building blocks
_MONTH = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
EXPIRY_RE = rf'{_MONTH}\w*'          # Apr, Apr24th, May1st, Dec27, etc.
STRIKE_RE = r'\d+(?:\.\d+)?'         # 230, 12.5, 277.50, etc.
OPT_RE    = r'(?:Ca[a-zA-Z]+|Puts?)' # Call/Calls/CAll/Cakk  or  Put/Puts
RATIO_RE  = r'(?:\d[\d.]*x\d[\d.]*\s+)?'   # optional 1x2, 1x1.5, etc.
SPREAD_KW = r'(?:(CS|PS|RR)|(Call\s+Spread|Put\s+Spread))'


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
        if kind == 'RR':
            low, high = (s1_str, s2_str) if s1 <= s2 else (s2_str, s1_str)
            return [f"{ticker} {expiry} {low} Put",
                    f"{ticker} {expiry} {high} Call"]
        opt = 'Call' if kind == 'CS' else 'Put'
        return [f"{ticker} {expiry} {s1_str} {opt}",
                f"{ticker} {expiry} {s2_str} {opt}"]

    # ── Pattern B: two expiries, same strike ─────────────────────────────────
    m = re.search(
        rf'({EXPIRY_RE})\s*/\s*({EXPIRY_RE})\s+({STRIKE_RE})\s+{SPREAD_KW}',
        seg, re.IGNORECASE
    )
    if m:
        exp1, exp2, strike = m.group(1), m.group(2), m.group(3)
        kind = _spread_type(m, 4, 5)
        if kind == 'RR':
            return [f"{ticker} {exp1} {strike} Put",
                    f"{ticker} {exp2} {strike} Call"]
        opt = 'Call' if kind == 'CS' else 'Put'
        return [f"{ticker} {exp1} {strike} {opt}",
                f"{ticker} {exp2} {strike} {opt}"]

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


def template(input_file, output_file):
    """
    For every line in input_file write:
        {original line}
        {blank line}
        {TICKER EXPIRY STRIKE Type OI Change:}   <- one per parsed option
        ---------------------------------

    Returns the number of lines processed.
    """
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        with open(output_file, 'w', encoding='utf-8') as f:
            for line in lines:
                # line already ends with \n; writing '\n' again gives the blank line
                f.write(line + '\n')
                for opt in parse_line_options(line):
                    f.write(f"{opt} OI Change:\n")
                f.write("---------------------------------\n")

        print(f"Processed {len(lines)} lines")
        print(f"Output written to: {output_file}")
        return len(lines)

    except FileNotFoundError:
        raise FileNotFoundError(f"Input file not found: {input_file}")
    except Exception as e:
        raise Exception(f"Error processing file: {e}")


if __name__ == "__main__":
    template("original_input.txt", "template.txt")

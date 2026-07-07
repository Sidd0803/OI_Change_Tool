#!/usr/bin/env python3
"""
WallachBeth Trade Recap HTML Generator
---------------------------------------
Parses a plain-text trade recap file and outputs a branded HTML table.

Usage:
    python generate_trade_recap_v2.py <input.txt> [output.html]

Arguments:
    input.txt     Path to the trade recap text file
    output.html   Optional output path (default: trade_recap.html)

Expected input format:
    Trade Recap: <date>
    ———————————
    Color - <trade description text>
    <TICKER> <leg> OI Change: <+/-value>
    <TICKER> <leg> OI Change: <+/-value>   (optional second leg)
    Volume: <value>
    ———————————
    ... repeat for each trade block

Notes:
  - Trade description is kept verbatim (minus "Color - " prefix)
  - Volume line is optional per block
  - OI change values are color coded green/red
  - Trade volume (from "Color -" line) and Volume line value are both bolded
"""

import sys, re, os

BLUE      = "#08519C"
BLUE_LITE = "#DEEBF7"
STRIPE    = "#F2F7FC"
WHITE     = "#ffffff"
DARK_GRAY = "#3D3D3D"
GRAY_MUTE = "#9B9B9B"
GREEN_FG  = "#1A7C3E"
RED_FG    = "#C0392B"


def is_separator(line):
    s = line.strip()
    s = s.replace("\u2014","-").replace("\u2013","-").replace("\u2012","-").replace("\u2015","-")
    return bool(re.match(r'^[-—\-]{3,}$', line.strip())) or bool(re.match(r'^-{3,}$', s))


def parse_date(line):
    m = re.search(r'Trade Recap[:\s]+(.+)', line, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def parse_oi_line(line):
    """'WBD Oct 20 Put OI Change: +1,309' -> ('WBD Oct 20 Put OI Change', '+1,309')"""
    m = re.match(r'^(.+?)\s+OI\s+Change\s*:\s*([+-]?\s*[\d,]+)', line.strip(), re.IGNORECASE)
    if not m:
        return None, None
    label = m.group(1).strip() + " OI Change"
    raw = m.group(2).replace(',','').replace(' ','')
    try:
        n = int(raw)
        val = f"+{n:,}" if n >= 0 else f"{n:,}"
    except ValueError:
        val = m.group(2).strip()
    return label, val


def parse_volume_line(line):
    """'Volume: 5k' or 'Volume 21k' or 'Volume = 5k' -> '5k'"""
    m = re.match(r'^volume[\s:=]+(.+)', line.strip(), re.IGNORECASE)
    return m.group(1).strip() if m else None


def bold_trade_volume(desc):
    """
    Find the trade size/volume in the description and wrap it in <strong>.
    The volume typically appears as a number (possibly with k) before 'traded' or 'bot' or 'paid'.
    Also handles patterns like '750x1.5k', '6k', '1k', '21k'.
    """
    # Pattern: size token immediately before traded/bot/paid/for
    def replacer(m):
        return f'<strong style="color:{BLUE};">{m.group(1)}</strong> {m.group(2)}'

    # Match size before action words
    result = re.sub(
        r'\b([\d]+(?:\.\d+)?[kK]?(?:x[\d]+(?:\.\d+)?[kK]?)?)\s+(traded|bot|paid)',
        replacer,
        desc,
        flags=re.IGNORECASE
    )
    return result


def oi_color(val):
    try:
        n = int(val.replace(',','').replace('+',''))
        return GREEN_FG if n > 0 else RED_FG if n < 0 else DARK_GRAY
    except ValueError:
        return DARK_GRAY


def parse_file(path):
    with open(path, encoding="utf-8") as f:
        lines = [l.rstrip('\n') for l in f]

    date_str      = ""
    trades        = []
    current_trade = None
    current_oi    = []
    current_vol   = None

    def flush():
        nonlocal current_trade, current_oi, current_vol
        if current_trade:
            current_trade["oi"]     = current_oi
            current_trade["volume"] = current_vol
            trades.append(current_trade)
        current_trade = None
        current_oi    = []
        current_vol   = None

    for line in lines:
        s = line.strip()
        if not s: continue

        if re.match(r'trade recap', s, re.IGNORECASE):
            date_str = parse_date(s)
            continue

        if is_separator(s):
            flush()
            continue

        # Volume line
        vol = parse_volume_line(s)
        if vol is not None:
            current_vol = vol
            continue

        # OI change line
        oi_label, oi_value = parse_oi_line(s)
        if oi_label:
            current_oi.append((oi_label, oi_value))
            continue

        # Trade line
        if re.match(r'color\s*-', s, re.IGNORECASE):
            flush()
            desc = re.sub(r'^color\s*-\s*', '', s, flags=re.IGNORECASE).strip()
            current_trade = {"desc": desc}
            current_oi    = []
            current_vol   = None
            continue

    flush()
    return date_str, trades


def build_html(date_str, trades):
    rows = []

    for i, t in enumerate(trades):
        desc   = t.get("desc", "")
        oi     = t.get("oi", [])
        volume = t.get("volume", None)
        bg     = STRIPE if i % 2 == 1 else WHITE

        # Bold the trade volume in the description
        desc_html = bold_trade_volume(desc)

        # Build OI + Volume line (volume first)
        vol_html = ""
        if volume:
            vol_html = f'Total Volume OTD: <strong style="color:{BLUE};">{volume}</strong>'

        oi_parts = []
        for lbl, val in oi:
            color = oi_color(val)
            oi_parts.append(f'{lbl}: <span style="color:{color};">{val}</span>')
        oi_html = " &nbsp;&middot;&nbsp; ".join(oi_parts)

        if vol_html and oi_html:
            oi_html = vol_html + f' &nbsp;&nbsp; ' + oi_html
        elif vol_html:
            oi_html = vol_html

        rows.append(
            f'  <tr><td style="background:{bg};padding:12px 16px;border-bottom:1px solid {BLUE_LITE};">\n'
            f'    <div style="font-size:12px;color:{DARK_GRAY};line-height:1.5;">{desc_html}</div>\n'
            + (f'    <div style="font-size:10px;color:{GRAY_MUTE};margin-top:5px;">{oi_html}</div>\n' if oi_html else '')
            + f'  </td></tr>'
        )

    body = "\n".join(rows)
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="font-family:Arial,sans-serif;border-collapse:collapse;border:1px solid {BLUE_LITE};">\n\n'
        f'  <tr><td style="background:{BLUE};padding:12px 16px;">\n'
        f'    <span style="font-size:15px;font-weight:bold;color:#ffffff;letter-spacing:0.3px;">'
        f'Trade Recap ({date_str})</span>\n'
        f'  </td></tr>\n\n'
        f'{body}\n\n'
        f'  <tr><td style="background:{BLUE};padding:6px 16px;text-align:center;">\n'
        f'    <span style="color:#ffffff;font-size:10px;">WallachBeth Capital'
        f' &nbsp;|&nbsp; Confidential &nbsp;|&nbsp; For Internal Use Only</span>\n'
        f'  </td></tr>\n\n</table>'
    )


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) >= 3 else "trade_recap.html"
    if not os.path.exists(inp):
        print(f"Error: file not found: {inp}"); sys.exit(1)
    print(f"Parsing {inp} ...")
    date_str, trades = parse_file(inp)
    print(f"  -> date:   {date_str}")
    print(f"  -> trades: {len(trades)}")
    for t in trades:
        print(f"     oi={len(t['oi'])}  vol={t['volume']}  {t['desc'][:60]}")
    html = build_html(date_str, trades)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML written to {out}")

if __name__ == "__main__":
    main()

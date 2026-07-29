"""Reformat Bloomberg CFLEX trade color into a clean, human-readable summary.

Usage:
    python flex_color.py                 # paste lines, then Ctrl-Z Enter (Windows) / Ctrl-D
    python flex_color.py input.txt       # read from a file
    echo "*CFLEX ..." | python flex_color.py

Sample input:
    *CFLEX BE LST 197.51P PM AMR 07/17/2026 9500 @ 8.67 1BE
    *CFLEX BE LST 250.01P PM AMR 07/10/2026 9500 @ 13.42 1BE

Sample output:
    Color - BE Flex:

    7/10/26 250.01 Amer PM Put 9500 traded 13.42
    7/17/26 197.51 Amer PM Put 9500 traded 8.67
"""

import re
import sys
from datetime import datetime

# Bloomberg abbreviation -> display text
EXERCISE = {"AMR": "Amer", "EUR": "Euro", "EUE": "Euro"}
RIGHT = {"P": "Put", "C": "Call"}


def parse_line(line):
    """Parse one *CFLEX line into a dict, or return None if it doesn't match."""
    # *CFLEX <ticker> LST <strike><P/C> <AM/PM> <exercise> <MM/DD/YYYY> <qty> @ <price> ...
    m = re.match(
        r"\*CFLEX\s+(?P<ticker>\S+)\s+\S+\s+"
        r"(?P<strike>[\d.]+)(?P<right>[PC])\s+"
        r"(?P<ampm>AM|PM)\s+"
        r"(?P<exercise>\S+)\s+"
        r"(?P<date>\d{2}/\d{2}/\d{4})\s+"
        r"(?P<qty>\d+)\s+@\s+(?P<price>[\d.]+)",
        line.strip(),
    )
    if not m:
        return None
    d = m.groupdict()
    d["dt"] = datetime.strptime(d["date"], "%m/%d/%Y")
    return d


def format_trade(d):
    date = "{}/{}/{}".format(d["dt"].month, d["dt"].day, d["dt"].strftime("%y"))
    exercise = EXERCISE.get(d["exercise"], d["exercise"])
    right = RIGHT.get(d["right"], d["right"])
    return "{} {} {} {} {} {} traded {}".format(
        date, d["strike"], exercise, d["ampm"], right, d["qty"], d["price"]
    )


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            text = f.read()
    elif sys.stdin.isatty():
        # Interactive: show instructions before reading pasted input.
        eof = "Ctrl-Z then Enter" if sys.platform == "win32" else "Ctrl-D"
        print("Paste the Bloomberg CFLEX trade color lines below.")
        print("Each line looks like:")
        print("    *CFLEX BE LST 197.51P PM AMR 07/17/2026 9500 @ 8.67 1BE")
        print("When you're done, press {} on a new line.".format(eof))
        print("-" * 60)
        text = sys.stdin.read()
        print("-" * 60)
    else:
        text = sys.stdin.read()

    trades = [t for t in (parse_line(ln) for ln in text.splitlines()) if t]
    if not trades:
        print("No CFLEX lines found.")
        return

    trades.sort(key=lambda t: t["dt"])
    ticker = trades[0]["ticker"]

    print("Color - {} Flex:".format(ticker))
    print()
    for t in trades:
        print(format_trade(t))


if __name__ == "__main__":
    main()

"""
Group template.txt blocks that describe the same structure.

The chat log often carries the same option traded several times in a day —
two or three separate prints of MU Oct 1050 Put. template.py emits one block
per print, so the same series gets its own OI Change line in each, and the
fill steps then stamp the identical Bloomberg figure onto every copy. Merging
those was being done by hand before the recap went out.

This step does the merge: blocks whose OI Change lines are identical become a
single block, keeping every trade description in the order it appeared, under
one set of OI Change lines.

It also drops the OI Change lines of contracts that were already expired on
the trading day being reported. Their OI change reads 0, and a 0 there tells
the reader nothing, so the line is cut instead of printed. A multi-leg trade
keeps its live legs; a trade with no live legs left drops out entirely.

Reads and rewrites ../data/template.txt, so it belongs between template.py
and bloomberg_tickers.py. Running it twice changes nothing.
"""
import argparse
import os
from datetime import datetime

import expiry
from expiry import previous_business_day

SEPARATOR = '-' * 33
TEMPLATE_FILE = '../data/template.txt'


def _is_separator(line):
    stripped = line.strip()
    return bool(stripped) and set(stripped) == {'-'}


def parse_blocks(lines):
    """
    Split template.txt at the dashed separators into (descriptions, oi_lines)
    pairs. Blank lines are structural and get rebuilt on write.
    """
    blocks = []
    descriptions, oi_lines = [], []

    def flush():
        if descriptions or oi_lines:
            blocks.append((descriptions[:], oi_lines[:]))
        descriptions.clear()
        oi_lines.clear()

    for raw in lines:
        line = raw.rstrip('\n').rstrip()
        if _is_separator(line):
            flush()
        elif 'OI Change:' in line:
            oi_lines.append(line)
        elif line.strip():
            descriptions.append(line)
    flush()
    return blocks


def structure_key(oi_lines):
    """What makes two blocks the same trade structure."""
    return tuple(line.strip() for line in oi_lines)


def consolidate(blocks):
    """
    Merge blocks sharing an identical set of OI Change lines, at the position
    where that structure first appeared.

    Returns (merged_blocks, groups) where groups maps a structure key to how
    many source blocks fed it.

    A block with no OI Change lines is left alone: template.py could not parse
    that trade, and folding it into a neighbour would hide it. Duplicate
    description lines are kept rather than de-duplicated — two prints of the
    same size at the same price are two trades, and dropping one would lose a
    fill from the recap.
    """
    merged = []
    position = {}
    groups = {}

    for descriptions, oi_lines in blocks:
        if not oi_lines:
            merged.append((descriptions, oi_lines))
            continue

        key = structure_key(oi_lines)
        groups[key] = groups.get(key, 0) + 1
        if key in position:
            merged[position[key]][0].extend(descriptions)
        else:
            position[key] = len(merged)
            merged.append((descriptions, oi_lines))

    return merged, groups


def drop_expired(blocks, trade_date):
    """
    Remove OI Change lines for contracts already dead by `trade_date`, and
    drop any block left with none.

    Runs before grouping. Two trades can differ only in a leg that is now
    dead — an Oct5th/Oct2nd spread against an Oct5th/Oct2nd spread at another
    Oct2nd strike — and once those legs are cut both present as the same
    surviving structure with the same OI figure. Grouping first would leave
    them side by side as visibly identical blocks, which is the duplication
    this step exists to remove. Each trade's own description is kept, so what
    it actually was stays on the page.

    A block that never had an OI Change line is untouched — template.py could
    not parse that trade, and it needs to stay visible to be fixed by hand.
    An expiry that cannot be resolved is treated as live, so nothing is cut
    on a guess.
    """
    kept, cut_lines, cut_blocks = [], [], []

    for descriptions, oi_lines in blocks:
        if not oi_lines:
            kept.append((descriptions, oi_lines))
            continue

        live, dead = [], []
        for line in oi_lines:
            if expiry.expired_for_recap(expiry.expiry_of_oi_line(line), trade_date):
                dead.append(line)
            else:
                live.append(line)

        cut_lines.extend(dead)
        if live:
            kept.append((descriptions, live))
        elif dead:
            cut_blocks.append((descriptions, dead))

    return kept, cut_lines, cut_blocks


def render(blocks):
    """Back to template.txt's layout: descriptions, blank line, OI, separator."""
    out = []
    for descriptions, oi_lines in blocks:
        out.extend(f"{d}\n" for d in descriptions)
        out.append('\n')
        out.extend(f"{o}\n" for o in oi_lines)
        out.append(SEPARATOR + '\n')
    return out


def main(path=TEMPLATE_FILE, output=None, trade_date=None):
    trade_date = trade_date or previous_business_day()

    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    blocks = parse_blocks(lines)
    live, cut_lines, cut_blocks = drop_expired(blocks, trade_date)
    merged, groups = consolidate(live)
    destination = output or path

    with open(destination, 'w', encoding='utf-8') as f:
        f.writelines(render(merged))

    print(f"Read {len(blocks)} block(s) from {path}.")

    print(f"Expired on or before {trade_date} (OI change would read 0):")
    if cut_lines:
        for line in cut_lines:
            print(f"  cut leg     {line.replace(' OI Change:', '')}")
        for descriptions, _ in cut_blocks:
            print(f"  cut trade   {descriptions[0]}")
        print(f"  {len(cut_lines)} OI line(s) cut, "
              f"{len(cut_blocks)} trade(s) dropped entirely.")
    else:
        print("  nothing expired.")

    repeated = {k: n for k, n in groups.items() if n > 1}
    if repeated:
        print(f"Grouped {len(live) - len(merged)} repeat print(s) into "
              f"{len(repeated)} structure(s):")
        for key, count in repeated.items():
            label = ' + '.join(k.replace(' OI Change:', '') for k in key)
            print(f"  {label}  <- {count} trades")
    else:
        print("No repeated structures — nothing to merge.")

    print(f"Output written to {destination}")
    return merged


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    parser = argparse.ArgumentParser(
        description="Group template.txt blocks that trade the same structure, "
                    "so a series repeated through the day carries one OI "
                    "Change line instead of an identical copy per print. Run "
                    "after template.py and before bloomberg_tickers.py.")
    parser.add_argument('--input', default=TEMPLATE_FILE,
                        help=f"Template to consolidate (default: {TEMPLATE_FILE}).")
    parser.add_argument('--output',
                        help="Where to write (default: rewrite the input).")
    parser.add_argument('--date',
                        help="Trading day being reported, M/D/YYYY (default: "
                             "previous business day). Contracts expiring on or "
                             "before it are cut.")
    args = parser.parse_args()
    trade_date = (datetime.strptime(args.date, '%m/%d/%Y').date()
                  if args.date else None)
    main(args.input, args.output, trade_date)

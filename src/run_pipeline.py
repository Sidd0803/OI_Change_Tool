"""
Run any combination of the three reports from a single chat log.

All three read the same original_input.txt:

    Shared prep (needed by the recap and OI/volume reports)
        original_input.txt
            --(template.py)-->          template.txt
            --(bloomberg_tickers.py)--> bloomberg_tickers.txt

    recap  Trade recap HTML
            --(generate_recap_input_txt.py + Bloomberg)--> recap_input.txt
            --(generate_trade_recap.py)-->                 trade_recap.html

    oi     OI change / Volume report (Element Chat)
            --(generate_final_output.py + Bloomberg)-->    final_output.txt

    flex   Flex color (no Bloomberg, no shared prep)
            --(occ_flex.py + OCC flex reports)-->          flex_output.txt

Each step is still runnable on its own (each script keeps its own __main__);
this just chains them.

Usage:
    python run_pipeline.py                    # menu
    python run_pipeline.py --reports all
    python run_pipeline.py --reports recap,flex
    python run_pipeline.py --reports oi
    python run_pipeline.py --reports flex --date 7/24/2026
    python run_pipeline.py --from-excel       # numbers.xlsx instead of Bloomberg
    python run_pipeline.py --input ../data/other_input.txt
"""
import argparse
import os
import sys
from datetime import datetime

# Ensure the '../data/...' relative paths used by every step resolve regardless
# of where this script is launched from.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import entrypoint
import template
import bloomberg_tickers
import generate_recap_input_txt
import generate_final_output
import generate_trade_recap
import occ_flex

INPUT_FILE = '../data/original_input.txt'
TEMPLATE_FILE = '../data/template.txt'
FILTERED_FILE = '../data/filtered_input.txt'
TICKERS_FILE = '../data/bloomberg_tickers.txt'
RECAP_INPUT_FILE = '../data/recap_input.txt'
RECAP_HTML_FILE = '../data/trade_recap.html'
FINAL_OUTPUT_FILE = '../data/final_output.txt'
FLEX_OUTPUT_FILE = '../data/flex_output.txt'

# Menu order; also the order reports run in.
REPORTS = ('recap', 'flex', 'oi')

MENU = """
============================================================
 Which report(s) do you want?
============================================================
  1) Trade recap    - branded HTML recap  (trade_recap.html)
  2) Flex color     - OI change from OCC  (flex_output.txt)
  3) OI / Volume    - for Element Chat    (final_output.txt)
  4) All three
"""


def _banner(step, title):
    print(f"\n{'=' * 60}\n[Step {step}] {title}\n{'=' * 60}")


def parse_reports(value):
    """'all' / 'recap,flex' / '1,3' -> ordered list of report names."""
    if value.strip().lower() in ('all', '4'):
        return list(REPORTS)

    chosen = []
    for token in value.replace(' ', '').split(','):
        if not token:
            continue
        if token.isdigit():
            idx = int(token) - 1
            if not 0 <= idx < len(REPORTS):
                raise ValueError(f"'{token}' is not one of 1-4")
            name = REPORTS[idx]
        elif token.lower() in REPORTS:
            name = token.lower()
        else:
            raise ValueError(f"'{token}' is not a known report")
        if name not in chosen:
            chosen.append(name)

    if not chosen:
        raise ValueError("no reports selected")
    return [r for r in REPORTS if r in chosen]


def prompt_for_reports():
    """Ask which reports to run. Falls back to all when not interactive."""
    if not sys.stdin.isatty():
        print("Non-interactive shell — defaulting to all reports.")
        return list(REPORTS)

    print(MENU)
    while True:
        raw = input("Enter numbers (e.g. 1,3) or 4 for all [4]: ").strip() or '4'
        try:
            return parse_reports(raw)
        except ValueError as exc:
            print(f"  {exc} — try again.")


def run_prep(input_file, step):
    """template.txt + bloomberg_tickers.txt — shared by the recap and OI reports."""
    _banner(step, "Parse chat log -> template.txt")
    template.template(input_file, TEMPLATE_FILE)

    _banner(step + 1, "Build Bloomberg tickers -> bloomberg_tickers.txt")
    bloomberg_tickers.filter_oi_change_lines(TEMPLATE_FILE, FILTERED_FILE)
    bloomberg_tickers.process_file_to_bloomberg(FILTERED_FILE, TICKERS_FILE)
    return step + 2


def run_recap(from_excel, step):
    source = "numbers.xlsx" if from_excel else "Bloomberg"
    _banner(step, f"Fill OI change + volume ({source}) -> recap_input.txt")
    generate_recap_input_txt.main(from_excel=from_excel)

    _banner(step + 1, "Render recap -> trade_recap.html")
    date_str, trades = generate_trade_recap.parse_file(RECAP_INPUT_FILE)
    html = generate_trade_recap.build_html(date_str, trades)
    with open(RECAP_HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  -> date: {date_str}, {len(trades)} trades")
    print(f"Output written to {RECAP_HTML_FILE}")
    return step + 2


def run_oi(from_excel, step):
    source = "numbers.xlsx" if from_excel else "Bloomberg"
    _banner(step, f"OI change / Volume ({source}) -> final_output.txt")
    generate_final_output.main(from_excel=from_excel)
    return step + 1


def run_flex(input_file, trade_date, step):
    _banner(step, "Flex color: OCC open interest -> flex_output.txt")
    occ_flex.run(input_file, trade_date=trade_date, output=FLEX_OUTPUT_FILE)
    return step + 1


def run(input_file=INPUT_FILE, from_excel=False, reports=None, trade_date=None):
    reports = reports or list(REPORTS)
    outputs = []
    failures = []
    step = 1

    # Every report starts here — no report may be built from anything else.
    entrypoint.require_input(input_file)
    print(f"Source: {input_file}")

    # Only the Bloomberg-backed reports need the template/ticker chain; the
    # flex report reads the chat log directly. Either way the chain is rebuilt
    # from the input on every run, so a report can never reuse stale
    # intermediates.
    if {'recap', 'oi'} & set(reports):
        step = run_prep(input_file, step)

    # A report that blows up shouldn't discard the ones that already succeeded,
    # so each is isolated when more than one was requested.
    def _attempt(name, fn, produced):
        nonlocal step
        try:
            step = fn(step)
            outputs.extend(produced)
        except Exception as exc:
            if len(reports) == 1:
                raise
            failures.append((name, exc))
            print(f"\nWARNING: {name} report failed: {exc}", file=sys.stderr)

    if 'recap' in reports:
        _attempt('trade recap', lambda s: run_recap(from_excel, s),
                 [RECAP_INPUT_FILE, RECAP_HTML_FILE])

    if 'flex' in reports:
        _attempt('flex color', lambda s: run_flex(input_file, trade_date, s),
                 [FLEX_OUTPUT_FILE])

    if 'oi' in reports:
        _attempt('OI / volume', lambda s: run_oi(from_excel, s),
                 [FINAL_OUTPUT_FILE])

    print(f"\n{'=' * 60}")
    if outputs:
        print("Done. Ready: "
              + ', '.join(os.path.basename(o) for o in outputs))
    if failures:
        print("Failed: " + ', '.join(name for name, _ in failures))
    print('=' * 60)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Run the trade recap, flex color and/or OI-volume reports "
                    "from original_input.txt.")
    parser.add_argument(
        '--input', default=INPUT_FILE,
        help=f"Raw chat log to start from (default: {INPUT_FILE}).")
    parser.add_argument(
        '--reports',
        help="Comma-separated: recap, flex, oi — or 'all'. Omit to be asked.")
    parser.add_argument(
        '--from-excel', action='store_true',
        help="Read OI/volume from numbers.xlsx instead of querying Bloomberg "
             "(does not affect the flex report).")
    parser.add_argument(
        '--date',
        help="Trade date M/D/YYYY for the flex report (default: previous "
             "business day).")
    args = parser.parse_args()

    try:
        reports = parse_reports(args.reports) if args.reports else prompt_for_reports()
    except ValueError as exc:
        parser.error(f"--reports: {exc}")

    trade_date = (datetime.strptime(args.date, '%m/%d/%Y').date()
                  if args.date else None)
    run(input_file=args.input,
        from_excel=args.from_excel,
        reports=reports,
        trade_date=trade_date)

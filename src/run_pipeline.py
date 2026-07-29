"""
Run the reports end-to-end from a single chat log.

Both reports read the same original_input.txt:

    Trade recap (Bloomberg OI change)
        original_input.txt
            --(template.py)-->          template.txt
            --(bloomberg_tickers.py)--> bloomberg_tickers.txt
            --(generate_recap_input_txt.py + Bloomberg)--> recap_input.txt
            --(generate_trade_recap.py)--> trade_recap.html

    Flex color (OCC OI change)
        original_input.txt
            --(occ_flex.py + OCC flex reports)--> flex_output.txt

Each step is still runnable on its own (each script keeps its own __main__);
this just chains them.

Usage:
    python run_pipeline.py                  # menu: recap, flex, or both
    python run_pipeline.py --reports both   # skip the menu
    python run_pipeline.py --reports flex --date 7/24/2026
    python run_pipeline.py --from-excel     # use numbers.xlsx instead of Bloomberg
    python run_pipeline.py --input ../data/other_input.txt
"""
import argparse
import os
import sys
from datetime import datetime

# Ensure the '../data/...' relative paths used by every step resolve regardless
# of where this script is launched from.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import template
import bloomberg_tickers
import generate_recap_input_txt
import generate_trade_recap
import occ_flex

INPUT_FILE = '../data/original_input.txt'
TEMPLATE_FILE = '../data/template.txt'
FILTERED_FILE = '../data/filtered_input.txt'
TICKERS_FILE = '../data/bloomberg_tickers.txt'
RECAP_INPUT_FILE = '../data/recap_input.txt'
RECAP_HTML_FILE = '../data/trade_recap.html'
FLEX_OUTPUT_FILE = '../data/flex_output.txt'

REPORT_CHOICES = ('recap', 'flex', 'both')

MENU = """
============================================================
 Which report(s) do you want?
============================================================
  1) Trade recap  - listed color, OI change from Bloomberg
  2) Flex color   - flex trades, OI change from OCC reports
  3) Both
"""


def _banner(step, title):
    print(f"\n{'=' * 60}\n[Step {step}] {title}\n{'=' * 60}")


def prompt_for_reports():
    """Ask which reports to run. Falls back to 'both' when not interactive."""
    if not sys.stdin.isatty():
        print("Non-interactive shell — defaulting to both reports.")
        return 'both'

    print(MENU)
    while True:
        choice = input("Enter 1, 2 or 3 [3]: ").strip() or '3'
        if choice in ('1', '2', '3'):
            return REPORT_CHOICES[int(choice) - 1]
        print("  Please enter 1, 2 or 3.")


def run_recap(input_file, from_excel=False, step=1):
    _banner(step, "Parse chat log -> template.txt")
    template.template(input_file, TEMPLATE_FILE)

    _banner(step + 1, "Build Bloomberg tickers -> bloomberg_tickers.txt")
    bloomberg_tickers.filter_oi_change_lines(TEMPLATE_FILE, FILTERED_FILE)
    bloomberg_tickers.process_file_to_bloomberg(FILTERED_FILE, TICKERS_FILE)

    source = "numbers.xlsx" if from_excel else "Bloomberg"
    _banner(step + 2, f"Fill OI change + volume ({source}) -> recap_input.txt")
    generate_recap_input_txt.main(from_excel=from_excel)

    _banner(step + 3, "Render recap -> trade_recap.html")
    date_str, trades = generate_trade_recap.parse_file(RECAP_INPUT_FILE)
    html = generate_trade_recap.build_html(date_str, trades)
    with open(RECAP_HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  -> date: {date_str}, {len(trades)} trades")
    print(f"Output written to {RECAP_HTML_FILE}")
    return step + 4


def run_flex(input_file, trade_date=None, step=1):
    _banner(step, "Flex color: OCC open interest -> flex_output.txt")
    occ_flex.run(input_file, trade_date=trade_date, output=FLEX_OUTPUT_FILE)
    return step + 1


def run(input_file=INPUT_FILE, from_excel=False, reports='both', trade_date=None):
    outputs = []
    step = 1

    if reports in ('recap', 'both'):
        step = run_recap(input_file, from_excel=from_excel, step=step)
        outputs += [RECAP_INPUT_FILE, RECAP_HTML_FILE]

    if reports in ('flex', 'both'):
        if reports == 'both':
            # A flex failure (no OCC report yet, network down) shouldn't throw
            # away the recap that already succeeded.
            try:
                step = run_flex(input_file, trade_date=trade_date, step=step)
                outputs.append(FLEX_OUTPUT_FILE)
            except Exception as exc:
                print(f"\nWARNING: flex report failed: {exc}", file=sys.stderr)
                print("The trade recap above is still valid.", file=sys.stderr)
        else:
            step = run_flex(input_file, trade_date=trade_date, step=step)
            outputs.append(FLEX_OUTPUT_FILE)

    print(f"\n{'=' * 60}\nDone. Ready: {', '.join(os.path.basename(o) for o in outputs)}"
          f"\n{'=' * 60}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Run the trade recap and/or flex color reports from "
                    "original_input.txt.")
    parser.add_argument(
        '--input', default=INPUT_FILE,
        help=f"Raw chat log to start from (default: {INPUT_FILE}).")
    parser.add_argument(
        '--reports', choices=REPORT_CHOICES,
        help="Which report(s) to run. Omit to be asked.")
    parser.add_argument(
        '--from-excel', action='store_true',
        help="Read OI/volume from numbers.xlsx instead of querying Bloomberg "
             "(trade recap only).")
    parser.add_argument(
        '--date',
        help="Trade date M/D/YYYY for the flex report (default: previous "
             "business day).")
    args = parser.parse_args()

    trade_date = (datetime.strptime(args.date, '%m/%d/%Y').date()
                  if args.date else None)
    run(input_file=args.input,
        from_excel=args.from_excel,
        reports=args.reports or prompt_for_reports(),
        trade_date=trade_date)

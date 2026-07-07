"""
Run the recap pipeline end-to-end:

    original_input.txt
        --(template.py)-->        template.txt
        --(bloomberg_tickers.py)--> bloomberg_tickers.txt
        --(generate_recap_input_txt.py + Bloomberg)--> recap_input.txt

Each step is still runnable on its own (each script keeps its own __main__);
this just chains them so you can produce recap_input.txt in one command.

Usage:
    python run_pipeline.py                # full chain, OI/volume from Bloomberg
    python run_pipeline.py --from-excel   # use numbers.xlsx instead of Bloomberg
    python run_pipeline.py --input ../data/other_input.txt
"""
import argparse
import os

# Ensure the '../data/...' relative paths used by every step resolve regardless
# of where this script is launched from.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import template
import bloomberg_tickers
import generate_recap_input_txt
import generate_trade_recap

INPUT_FILE = '../data/original_input.txt'
TEMPLATE_FILE = '../data/template.txt'
FILTERED_FILE = '../data/filtered_input.txt'
TICKERS_FILE = '../data/bloomberg_tickers.txt'
RECAP_INPUT_FILE = '../data/recap_input.txt'
RECAP_HTML_FILE = '../data/trade_recap.html'


def _banner(step, title):
    print(f"\n{'=' * 60}\n[Step {step}] {title}\n{'=' * 60}")


def run(input_file=INPUT_FILE, from_excel=False):
    _banner(1, "Parse chat log -> template.txt")
    template.template(input_file, TEMPLATE_FILE)

    _banner(2, "Build Bloomberg tickers -> bloomberg_tickers.txt")
    bloomberg_tickers.filter_oi_change_lines(TEMPLATE_FILE, FILTERED_FILE)
    bloomberg_tickers.process_file_to_bloomberg(FILTERED_FILE, TICKERS_FILE)

    source = "numbers.xlsx" if from_excel else "Bloomberg"
    _banner(3, f"Fill OI change + volume ({source}) -> recap_input.txt")
    generate_recap_input_txt.main(from_excel=from_excel)

    _banner(4, "Render recap -> trade_recap.html")
    date_str, trades = generate_trade_recap.parse_file(RECAP_INPUT_FILE)
    html = generate_trade_recap.build_html(date_str, trades)
    with open(RECAP_HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  -> date: {date_str}, {len(trades)} trades")
    print(f"Output written to {RECAP_HTML_FILE}")

    print(f"\n{'=' * 60}\nDone. recap_input.txt and trade_recap.html are ready.\n{'=' * 60}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Run the recap pipeline end-to-end "
                    "(original_input.txt -> recap_input.txt).")
    parser.add_argument(
        '--input', default=INPUT_FILE,
        help=f"Raw chat log to start from (default: {INPUT_FILE}).")
    parser.add_argument(
        '--from-excel', action='store_true',
        help="Read OI/volume from numbers.xlsx instead of querying Bloomberg.")
    args = parser.parse_args()
    run(input_file=args.input, from_excel=args.from_excel)

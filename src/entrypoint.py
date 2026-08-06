"""
Shared guards for the pipeline.

data/original_input.txt is the starting point for all three reports.
run_pipeline.py rebuilds the whole chain from it; the step modules can also be
run one at a time, in which case each does only its own step so that edits
made to template.txt in between are preserved.

Because a standalone step trusts the files it is given, the ordering guard in
`check_alignment` matters: OI values are matched to trades by position, so a
reordered template.txt with a stale ticker list would put values on the wrong
trades.
"""
import os
import sys


def require_input(path):
    """
    Fail loudly if the one true starting point is missing or empty, rather
    than letting a report be built from nothing.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Paste the day's Bloomberg chat log into it "
            f"before running the pipeline.")
    if os.path.getsize(path) == 0:
        raise ValueError(
            f"{path} is empty. Paste the day's Bloomberg chat log into it "
            f"before running the pipeline.")


def check_alignment(expected, actual, tickers_file):
    """
    Verify the ticker sequence derived from template.txt matches the one
    recorded in bloomberg_tickers.txt. Both are [(ticker, count), ...].

    Raises SystemExit on a mismatch rather than filling values that would be
    attributed to the wrong trades.
    """
    if expected == actual:
        return

    print("\nERROR: template.txt and the Bloomberg ticker list disagree.",
          file=sys.stderr)
    print(f"  template.txt expects: {expected}", file=sys.stderr)
    print(f"  {tickers_file} has:   {actual}", file=sys.stderr)
    print("\nOI values are matched to trades by position, so filling them now "
          "would attribute them to the wrong trades.", file=sys.stderr)
    print("Rebuild the ticker list from the current template:\n", file=sys.stderr)
    print("    python bloomberg_tickers.py\n", file=sys.stderr)
    print("Note that tickers must be grouped together — if the same ticker "
          "appears in two separate places in template.txt, move those lines "
          "next to each other.", file=sys.stderr)
    raise SystemExit(3)

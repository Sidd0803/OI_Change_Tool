"""
Guard for the pipeline step modules.

data/original_input.txt is the single starting point for all three reports,
and every derived file (template.txt, filtered_input.txt,
bloomberg_tickers.txt, ...) is rebuilt from it on every run.

Running a step module directly would start mid-chain on whatever intermediate
files happen to be sitting on disk. That doesn't error — it produces a
complete, correct-looking report built on stale data, which is worse. So the
step modules refuse to run on their own; run_pipeline.py is the only entry
point.
"""
import os
import sys

MESSAGE = """\
{script} is a pipeline step and cannot be run on its own.

Running it directly starts partway down the chain, using intermediate files
that may be left over from an earlier run. That produces a report which looks
correct but is built on stale data. Every report is rebuilt from
data/original_input.txt on each run, so start there instead:

    python run_pipeline.py                      # menu
    python run_pipeline.py --reports recap      # or skip the menu
    python run_pipeline.py --reports all
"""


def refuse(script):
    """Print how to run the pipeline properly and exit non-zero."""
    print(MESSAGE.format(script=script), file=sys.stderr)
    sys.exit(2)


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

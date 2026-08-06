"""
Open-interest convention, applied uniformly by all three reports.

An option whose expiry has passed has no open interest, so its OI value is
reported as 0 regardless of what Bloomberg or the OCC report returns. This
overrides the fetched value rather than adjusting it.

The rule matters because an expired contract stops reporting open interest,
but OPEN_INT_CHANGE keeps serving the delta from its last live session
indefinitely — a real number from days ago, printed as if it were the trade
date's. Subtracting open interest by hand across the trade date gives 0, so
0 is what gets reported.

"Passed" is measured against today's date, so re-running an older recap will
zero out anything that has since expired. An option expiring today is still
live and keeps its real value.

This module is the single home for the rule. Everything that needs it —
generate_recap_input_txt, generate_final_output, occ_flex — goes through here
so there is one expiry parser rather than several drifting apart.
"""
import re
from datetime import date, datetime

from bloomberg_tickers import convert_to_bloomberg_format

# The expiry inside a security string: 'MU US 8/3/26 P825 Equity'. Anchored on
# digit runs so a ticker with a slash (BRK/B) and a decimal strike (C347.50)
# don't get mistaken for a date.
_EXPIRY_RE = re.compile(r'\b(\d{1,2})/(\d{1,2})/(\d{2}(?:\d{2})?)\b')

ZERO = '0'


def parse_expiry(security):
    """
    Pull the expiry out of a Bloomberg option security string.
    'MU US 8/3/26 P825 Equity' -> date(2026, 8, 3).

    Returns None when the string carries no parseable date — the right answer
    for a non-option security, which has no expiry to be past.
    """
    match = _EXPIRY_RE.search(security)
    if not match:
        return None
    month, day, year = (int(g) for g in match.groups())
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def expiry_of_oi_line(line):
    """
    Expiry date for a template OI Change line such as
    'AAPL Jul31st 287.5 Put OI Change:', or None if it can't be resolved.

    Goes through convert_to_bloomberg_format so the chat's expiry shorthand
    ('Jul31st', 'Aug', 'Dec26') resolves via dates.txt exactly as it does when
    building the ticker list — no second date parser to keep in step.
    """
    try:
        security = convert_to_bloomberg_format(line)
    except (ValueError, AttributeError, IndexError):
        return None
    return parse_expiry(security)


def has_expired(expiry, as_of=None):
    """True if `expiry` (a date) is strictly before `as_of` (default: today)."""
    if expiry is None:
        return False
    return expiry < (as_of or date.today())


def is_expired(security, today=None):
    """True if the Bloomberg security string names a contract already expired."""
    return has_expired(parse_expiry(security), today)


def zero_expired(substitutions, template_lines, as_of=None):
    """
    Force OI to 0 for every substitution whose option has already expired.
    `substitutions` maps line index -> (oi, volume). Volume is left alone.
    Returns the number of lines overridden.
    """
    overridden = 0
    for idx, (oi, volume) in list(substitutions.items()):
        if has_expired(expiry_of_oi_line(template_lines[idx]), as_of):
            if str(oi).strip() != ZERO:
                overridden += 1
            substitutions[idx] = (ZERO, volume)
    return overridden

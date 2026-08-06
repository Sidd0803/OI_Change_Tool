"""
Open-interest convention, applied uniformly by all three reports.

An option whose expiry has passed has no open interest, so its OI value is
reported as 0 regardless of what Bloomberg or the OCC report returns. This
overrides the fetched value rather than adjusting it.

"Passed" is measured against today's date, so re-running an older recap will
zero out anything that has since expired.
"""
import re
from datetime import date, datetime

from bloomberg_tickers import convert_to_bloomberg_format

# 'AAPL US 7/31/26 P287.5 Equity' -> 7/31/26
_BBG_DATE_RE = re.compile(r'\b(\d{1,2}/\d{1,2}/\d{2})\b')

ZERO = '0'


def expiry_of_oi_line(line):
    """
    Expiry date for a template OI Change line such as
    'AAPL Jul31st 287.5 Put OI Change:', or None if it can't be resolved.

    Reuses convert_to_bloomberg_format so the chat's expiry shorthand
    ('Jul31st', 'Aug', 'Dec26') resolves through dates.txt exactly as it does
    when building the ticker list — no second parser to keep in step.
    """
    try:
        security = convert_to_bloomberg_format(line)
    except (ValueError, AttributeError):
        return None
    m = _BBG_DATE_RE.search(security)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), '%m/%d/%y').date()
    except ValueError:
        return None


def has_expired(expiry, as_of=None):
    """True if `expiry` is strictly before `as_of` (default: today)."""
    if expiry is None:
        return False
    return expiry < (as_of or date.today())


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

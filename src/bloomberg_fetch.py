"""
Fetch OI change + volume for the option securities in bloomberg_tickers.txt
directly from Bloomberg via the Desktop API (blpapi), replacing the manual
Excel/BDP copy-paste step.

Requires a logged-in Bloomberg Terminal on the machine running this script.
Replicates the two BDP fields the Excel used: OPEN_INT_CHANGE and VOLUME.
"""
import re

import blpapi

TICKERS_FILE = '../data/bloomberg_tickers.txt'

OI_FIELD = 'OPEN_INT_CHANGE'
VOL_FIELD = 'VOLUME'

_OCCURRENCES_RE = re.compile(r'^\d+\s+occurrences\s+of\b', re.IGNORECASE)


def parse_ticker_blocks(filepath):
    """
    Parse bloomberg_tickers.txt into blocks of security strings.

    Each 'N occurrences of X' line closes the current block, reproducing the
    same block boundaries the '###' separator rows mark in numbers.xlsx.
    Returns a list of blocks, each a list of Bloomberg security strings in order.
    """
    blocks = []
    current = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if _OCCURRENCES_RE.match(line):
                if current:
                    blocks.append(current)
                    current = []
            else:
                current.append(line)

    if current:
        blocks.append(current)

    return blocks


def _normalize_value(value):
    """
    Return a string matching the old Excel contract (parse_excel_file stringified
    every cell). Integral floats become plain integers ('418', not '418.0');
    missing values become an empty string.
    """
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def fetch_fields(securities):
    """
    Query OPEN_INT_CHANGE and VOLUME for the given securities via blpapi.

    Returns {security: (oi_change, volume)}. A missing field or a security
    error yields None for that value and prints a warning.
    """
    if not securities:
        return {}

    # De-duplicate while preserving order.
    unique = list(dict.fromkeys(securities))
    results = {}

    session = blpapi.Session()
    try:
        if not session.start():
            raise RuntimeError(
                "Failed to start blpapi session — is the Bloomberg Terminal "
                "running and logged in on this machine?")
        if not session.openService('//blp/refdata'):
            raise RuntimeError("Failed to open //blp/refdata service.")

        service = session.getService('//blp/refdata')
        request = service.createRequest('ReferenceDataRequest')
        for sec in unique:
            request.getElement('securities').appendValue(sec)
        request.getElement('fields').appendValue(OI_FIELD)
        request.getElement('fields').appendValue(VOL_FIELD)

        session.sendRequest(request)

        done = False
        while not done:
            event = session.nextEvent()
            for msg in event:
                if not msg.hasElement('securityData'):
                    continue
                sec_data_array = msg.getElement('securityData')
                for i in range(sec_data_array.numValues()):
                    sec_data = sec_data_array.getValueAsElement(i)
                    sec_name = sec_data.getElementAsString('security')

                    if sec_data.hasElement('securityError'):
                        err = sec_data.getElement('securityError')
                        print(f"WARNING: security error for {sec_name}: "
                              f"{err.getElementAsString('message')}")
                        results[sec_name] = ('', '')
                        continue

                    field_data = sec_data.getElement('fieldData')
                    oi = (field_data.getElementAsFloat(OI_FIELD)
                          if field_data.hasElement(OI_FIELD) else None)
                    vol = (field_data.getElementAsFloat(VOL_FIELD)
                           if field_data.hasElement(VOL_FIELD) else None)

                    if sec_data.hasElement('fieldExceptions'):
                        fx = sec_data.getElement('fieldExceptions')
                        for k in range(fx.numValues()):
                            fld = fx.getValueAsElement(k).getElementAsString('fieldId')
                            print(f"WARNING: field '{fld}' unavailable for {sec_name}.")

                    if oi is None or vol is None:
                        print(f"WARNING: missing data for {sec_name} "
                              f"(OI={oi}, VOL={vol}).")

                    results[sec_name] = (_normalize_value(oi), _normalize_value(vol))

            if event.eventType() == blpapi.Event.RESPONSE:
                done = True

        return results
    finally:
        session.stop()


def fetch_blocks(filepath=TICKERS_FILE):
    """
    Return OI/volume data grouped into blocks matching parse_excel_file's output:
    a list of blocks, each a list of (oi_change, volume) tuples, in file order.
    """
    blocks = parse_ticker_blocks(filepath)
    flat = [sec for block in blocks for sec in block]
    data = fetch_fields(flat)

    result = []
    for block in blocks:
        result.append([data.get(sec, ('', '')) for sec in block])
    return result


if __name__ == '__main__':
    for idx, block in enumerate(fetch_blocks(), 1):
        print(f"Block {idx}:")
        for oi, vol in block:
            print(f"  OI Change = {oi}, Volume = {vol}")

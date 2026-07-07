"""
Generate a daily list of the largest option block trades for a set of tracked
underlyings, using BLPAPI (Bloomberg Desktop API) — a code replica of manually
reading the Block Trade Monitor and jotting down the top-size prints.

Approach (kept light to stay under Desktop-API limits):
  1. For each underlying, get spot (PX_LAST) to center a strike window.
  2. Enumerate its option chain (OPT_CHAIN) and filter to the nearest few
     expiries and a band of strikes around spot.
  3. Volume-gate: pull each candidate's day VOLUME; drop anything below the
     size floor (a contract can't hold a single print bigger than its volume).
  4. Tick only the survivors (IntradayTickRequest, TRADE events, today) and keep
     the largest print per contract at/above the floor.
  5. Rank all prints across names by size, keep the top N, enrich the winners
     (bought/sold via a bid/ask snapshot; stock ref via last price) and write
     recap-style lines.

Usage:
    python generate_block_trades.py --tickers WBD
    python generate_block_trades.py --excel ../data/watchlist.xlsx --sheet Sheet1 --column A
    python generate_block_trades.py --tickers WBD --top 10 --min-size 250
"""
import argparse
import datetime
import re

import blpapi
import openpyxl

# ── Defaults (all overridable via CLI) ───────────────────────────────────────
DEFAULT_TOP = 10
DEFAULT_MIN_SIZE = 250
N_EXPIRIES = 2            # nearest expiries to scan
STRIKES_EACH_SIDE = 10   # strikes kept on each side of spot
MIN_PRICE = 0.03         # skip near-worthless prints (administrative/closing)
OUTPUT_FILE = '../data/block_trades.txt'

_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# "WBD US 07/17/26 C29.5 Equity"
CHAIN_RE = re.compile(
    r'^(?P<root>.+?) US (?P<exp>\d{2}/\d{2}/\d{2}) (?P<cp>[CP])(?P<strike>\d+(?:\.\d+)?) Equity$')


# ── blpapi session plumbing ──────────────────────────────────────────────────
def open_session():
    session = blpapi.Session()
    if not session.start():
        raise RuntimeError("Failed to start blpapi session — is the Bloomberg "
                           "Terminal running and logged in?")
    if not session.openService("//blp/refdata"):
        raise RuntimeError("Failed to open //blp/refdata service.")
    return session


def _drain(session):
    """Collect messages from data events only (skip admin/status events)."""
    out = []
    while True:
        ev = session.nextEvent()
        et = ev.eventType()
        if et in (blpapi.Event.PARTIAL_RESPONSE, blpapi.Event.RESPONSE):
            out.extend(list(ev))
        if et == blpapi.Event.RESPONSE:
            break
    return out


def bdp(session, securities, fields, overrides=None):
    """Reference data for many securities -> {security: {field: value}}."""
    svc = session.getService("//blp/refdata")
    req = svc.createRequest("ReferenceDataRequest")
    for s in securities:
        req.getElement("securities").appendValue(s)
    for f in fields:
        req.getElement("fields").appendValue(f)
    if overrides:
        ov = req.getElement("overrides")
        for k, v in overrides.items():
            e = ov.appendElement()
            e.setElement("fieldId", k)
            e.setElement("value", str(v))
    session.sendRequest(req)
    result = {}
    for msg in _drain(session):
        if not msg.hasElement("securityData"):
            continue
        arr = msg.getElement("securityData")
        for i in range(arr.numValues()):
            sd = arr.getValueAsElement(i)
            name = sd.getElementAsString("security")
            fd = sd.getElement("fieldData")
            result[name] = {f: (fd.getElementValue(f) if fd.hasElement(f) else None)
                            for f in fields}
    return result


def get_option_chain(session, underlying):
    """Return every option ticker in OPT_CHAIN for an underlying."""
    svc = session.getService("//blp/refdata")
    req = svc.createRequest("ReferenceDataRequest")
    req.getElement("securities").appendValue(underlying)
    req.getElement("fields").appendValue("OPT_CHAIN")
    session.sendRequest(req)
    tickers = []
    for msg in _drain(session):
        if not msg.hasElement("securityData"):
            continue
        sd = msg.getElement("securityData").getValueAsElement(0)
        fd = sd.getElement("fieldData")
        if fd.hasElement("OPT_CHAIN"):
            ch = fd.getElement("OPT_CHAIN")
            for i in range(ch.numValues()):
                tickers.append(ch.getValueAsElement(i).getElement(0).getValueAsString())
    return tickers


def intraday_trades(session, security, start_dt, end_dt):
    """TRADE ticks for a security between start/end (UTC naive datetimes)."""
    svc = session.getService("//blp/refdata")
    req = svc.createRequest("IntradayTickRequest")
    req.set("security", security)
    req.getElement("eventTypes").appendValue("TRADE")
    req.set("startDateTime", start_dt)
    req.set("endDateTime", end_dt)
    req.set("includeConditionCodes", True)
    session.sendRequest(req)
    trades = []
    for msg in _drain(session):
        if not msg.hasElement("tickData"):
            continue
        td = msg.getElement("tickData").getElement("tickData")
        for i in range(td.numValues()):
            e = td.getValueAsElement(i)
            trades.append({
                "time": e.getElementAsDatetime("time"),
                "price": e.getElementAsFloat("value"),
                "size": e.getElementAsInteger("size"),
            })
    return trades


# ── chain filtering + parsing ────────────────────────────────────────────────
def parse_contract(ticker):
    """'WBD US 07/17/26 C29.5 Equity' -> (root, date, strike, 'C'|'P') or None."""
    m = CHAIN_RE.match(ticker)
    if not m:
        return None
    exp = datetime.datetime.strptime(m.group("exp"), "%m/%d/%y").date()
    return m.group("root"), exp, float(m.group("strike")), m.group("cp")


def filter_chain(tickers, spot, n_expiries=N_EXPIRIES, strikes_each_side=STRIKES_EACH_SIDE):
    """
    Keep the nearest `n_expiries` expiries and `strikes_each_side` strikes on
    each side of spot. A value of 0 for either means "no limit" (full scan on
    that axis) — use 0/0 to scan the entire chain and select purely by size.
    """
    # (ticker, expiry, strike, call/put) for every parseable contract.
    parsed = []
    for t in tickers:
        pc = parse_contract(t)
        if pc:
            _, exp, strike, cp = pc
            parsed.append((t, exp, strike, cp))
    today = datetime.date.today()
    exps = sorted({e for _, e, _, _ in parsed if e >= today})
    if n_expiries:
        exps = exps[:n_expiries]
    exps = set(exps)
    keep = []
    for t, e, s, cp in parsed:
        if e not in exps:
            continue
        if strikes_each_side:
            strikes = sorted({ss for _, ee, ss, _ in parsed if ee == e})
            below = [ss for ss in strikes if ss <= spot][-strikes_each_side:]
            above = [ss for ss in strikes if ss > spot][:strikes_each_side]
            if s not in set(below + above):
                continue
        keep.append(t)
    return keep


# ── formatting ───────────────────────────────────────────────────────────────
def _is_third_friday(d):
    return d.weekday() == 4 and 15 <= d.day <= 21


def format_expiry(d, today=None):
    """
    Monthly expiries -> 'Aug'; weeklies -> '11Jul'. Out-year expiries get a
    2-digit year suffix ('Mar27', '11Jan27') to disambiguate LEAPs.
    """
    today = today or datetime.date.today()
    mon = _MONTHS[d.month - 1]
    base = mon if _is_third_friday(d) else f"{d.day}{mon}"
    return base if d.year == today.year else f"{base}{d.year % 100:02d}"


def format_strike(strike):
    return str(int(strike)) if float(strike).is_integer() else str(strike)


def format_price(px):
    return f"{px:.2f}".rstrip('0').rstrip('.') if px == round(px, 2) else str(px)


def classify_side(price, bid, ask):
    """Approximate bought/sold from a bid/ask snapshot (v1 — not trade-time)."""
    if ask is not None and price >= ask:
        return "bot"
    if bid is not None and price <= bid:
        return "sold"
    return "mid"


def format_line(trade):
    root, exp, strike, cp = trade["contract"]
    opt = "Call" if cp == "C" else "Put"
    return (f"{root} {format_expiry(exp)} {format_strike(strike)} {opt} "
            f"{trade['size']:,}x @ {format_price(trade['price'])} "
            f"({trade['side']}); stk ref {trade['spot']:.2f}")


# ── ticker source ────────────────────────────────────────────────────────────
def read_underlyings(excel_path, sheet, column):
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb[sheet] if sheet else wb.active
    col_idx = openpyxl.utils.column_index_from_string(column)
    out = []
    for row in ws.iter_rows(min_col=col_idx, max_col=col_idx, values_only=True):
        v = row[0]
        if v is None:
            continue
        t = str(v).strip().upper()
        if t and t not in out:
            out.append(t)
    return out


# ── main ─────────────────────────────────────────────────────────────────────
def collect_block_trades(session, roots, min_size, n_expiries=N_EXPIRIES,
                         strikes_each_side=STRIKES_EACH_SIDE):
    """Return the largest print per contract (>= min_size) across all roots."""
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    start = datetime.datetime(now.year, now.month, now.day, 0, 0)

    candidates = []
    for root in roots:
        underlying = f"{root} US Equity"
        spot = bdp(session, [underlying], ["PX_LAST"]).get(underlying, {}).get("PX_LAST")
        if spot is None:
            print(f"  {root}: no spot price, skipping.")
            continue

        chain = get_option_chain(session, underlying)
        kept = filter_chain(chain, spot, n_expiries, strikes_each_side)
        vol = bdp(session, kept, ["PX_VOLUME"])
        gated = [t for t in kept if (vol.get(t, {}).get("PX_VOLUME") or 0) >= min_size]
        print(f"  {root}: spot {spot:.2f}, chain {len(chain)} -> {len(kept)} near "
              f"-> {len(gated)} over volume floor")

        for contract in gated:
            trades = intraday_trades(session, contract, start, now)
            big = [t for t in trades if t["size"] >= min_size and t["price"] >= MIN_PRICE]
            if not big:
                continue
            top = max(big, key=lambda t: t["size"])
            candidates.append({
                "contract": parse_contract(contract),
                "ticker": contract,
                "size": top["size"],
                "price": top["price"],
                "time": top["time"],
                "spot": spot,
            })
    return candidates


def enrich_sides(session, winners):
    """Fill 'side' for the final winners using a bid/ask snapshot."""
    quotes = bdp(session, [w["ticker"] for w in winners], ["BID", "ASK"])
    for w in winners:
        q = quotes.get(w["ticker"], {})
        w["side"] = classify_side(w["price"], q.get("BID"), q.get("ASK"))


def main():
    parser = argparse.ArgumentParser(
        description="List the largest option block trades today for tracked underlyings.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument('--tickers', nargs='+', help="Underlying roots, e.g. --tickers WBD AAPL")
    src.add_argument('--excel', help="Path to an .xlsx worksheet of tickers")
    parser.add_argument('--sheet', help="Worksheet name (default: active sheet)")
    parser.add_argument('--column', default='A', help="Column letter holding tickers (default: A)")
    parser.add_argument('--top', type=int, default=DEFAULT_TOP)
    parser.add_argument('--min-size', type=int, default=DEFAULT_MIN_SIZE)
    parser.add_argument('--expiries', type=int, default=N_EXPIRIES,
                        help="Nearest expiries to scan (0 = all expiries).")
    parser.add_argument('--strikes', type=int, default=STRIKES_EACH_SIDE,
                        help="Strikes each side of spot (0 = all strikes).")
    parser.add_argument('--full-chain', action='store_true',
                        help="Scan the entire chain (all expiries/strikes); "
                             "select purely by size. Shortcut for --expiries 0 --strikes 0.")
    parser.add_argument('--output', default=OUTPUT_FILE)
    args = parser.parse_args()

    n_expiries = 0 if args.full_chain else args.expiries
    strikes = 0 if args.full_chain else args.strikes

    if args.excel:
        roots = read_underlyings(args.excel, args.sheet, args.column)
    else:
        roots = [t.strip().upper() for t in args.tickers]
    print(f"Scanning {len(roots)} underlying(s) for blocks >= {args.min_size}...")

    session = open_session()
    try:
        candidates = collect_block_trades(session, roots, args.min_size,
                                          n_expiries, strikes)
        candidates.sort(key=lambda c: -c["size"])
        winners = candidates[:args.top]
        enrich_sides(session, winners)
    finally:
        session.stop()

    lines = [format_line(w) for w in winners]
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + ('\n' if lines else ''))

    print(f"\nTop {len(winners)} block trade(s):")
    for ln in lines:
        print("  " + ln)
    print(f"\nOutput written to {args.output}")


if __name__ == '__main__':
    main()

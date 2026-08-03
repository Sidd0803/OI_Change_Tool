import os
import sys
import tempfile
import unittest
from datetime import date

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, 'src')
from occ_flex import (parse_chat, parse_flex_oi_report, series_keys,
                      resolve_key, previous_business_day, _is_report,
                      report_date_for, annotate_oi, write_output)

REPORT_SNIPPET = """\
 THE OPTIONS CLEARING CORPORATION - CHICAGO, ILLINOIS                             SYSTEM DATE 07/25/26    TIME 01:51:39    PAGE     1
 EQUITY FLEX OPEN INTEREST REPORT                                               ACTIVITY DATE 07/24/26    PROGRAM ID BV2C0210   V005

                   EXPIRATION  STRIKE        MARK     OPEN
      SYMBOL  P/C  MO DAY  YR  PRICE         PRICE    INTEREST

 American Airlines Group, Inc.
      1AAL     C   09 02 2026  00021 960      0.0450     52850
      1AAL     C   11 06 2026  00016 250      0.9939     10680

                          ***  CLASS TOTALS  ***        101233

 Accenture PLC (AMER/FLEX)
      1ACN     P   01 15 2027  00125 010     10.5772      5273
      4SMH     C   08 21 2026  00635 000      6.0000      6164
"""

CHAT_SAMPLE = """\
RAFAEL FERNANDES
08:02:22 Hey good morning everyone!
09:59:59 Color - SPCX Jul31st 330 Call bot 11k up to 0.10 live
KAEGEN MORRIS
10:11:39 Color - SNDK Flex:

07/31/2026 1500.01 Amer PM Put 3,000x traded 198.59, vs 1313.40 stk 65d (OI = 3,000)
10:36:57 Color - NBIS Flex:

07/31/2026 180.01 Amer PM Put 285x traded 9.25 (OI = 11,489)
07/31/2026 180.01 Amer PM Put 3,700x traded 9.26 (OI = 11,489)
11:10:49 Color - SNDK Jul31st 1500 Call 1.5k traded 22.50 vs 1,285.00 stk 14d - looks sold
13:08:36 Color - TSM Listed vs Flex:

Jul31st 350 Call 143x traded 43.95 - looks sold
Jul31st 355 Put 1,080x traded 1.02 - looks sold
live; stk ref 392.89

07/31/2026 280.01 Amer PM Call 378x traded 117.99 (OI = 1,260)
08/21/2026 635.00 Euro PM Call 3,126x traded 6.00 - looks sold
13:33:36 Color - NVDA:
Sep 225 Call 15.5k traded 4.21 - looks bot
elec live; stk ref 197.82
"""


def _write_temp(content):
    f = tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False)
    f.write(content)
    f.close()
    return f.name


class TestParseFlexOiReport(unittest.TestCase):

    def setUp(self):
        self.path = _write_temp(REPORT_SNIPPET)

    def tearDown(self):
        os.unlink(self.path)

    def test_rows_parsed_with_strike_and_expiry(self):
        oi = parse_flex_oi_report(self.path)
        self.assertEqual(oi[('1AAL', 'C', date(2026, 9, 2), 21.96)], 52850)
        self.assertEqual(oi[('1ACN', 'P', date(2027, 1, 15), 125.01)], 5273)
        self.assertEqual(oi[('4SMH', 'C', date(2026, 8, 21), 635.0)], 6164)

    def test_headers_and_totals_skipped(self):
        oi = parse_flex_oi_report(self.path)
        self.assertEqual(len(oi), 4)


class TestParseChat(unittest.TestCase):

    def setUp(self):
        self.path = _write_temp(CHAT_SAMPLE)
        self.blocks = parse_chat(self.path)

    def tearDown(self):
        os.unlink(self.path)

    def test_flex_blocks_extracted(self):
        self.assertEqual([b['ticker'] for b in self.blocks],
                         ['SNDK', 'NBIS', 'TSM'])

    def test_regular_color_ignored(self):
        tickers = {t['ticker'] for b in self.blocks for t in b['trades']}
        self.assertNotIn('SPCX', tickers)
        self.assertNotIn('NVDA', tickers)

    def test_listed_legs_in_mixed_block_ignored(self):
        tsm = self.blocks[2]
        self.assertEqual(len(tsm['trades']), 2)
        self.assertEqual(tsm['trades'][0]['strike'], 280.01)

    def test_trade_fields(self):
        t = self.blocks[0]['trades'][0]
        self.assertEqual(t['expiry'], date(2026, 7, 31))
        self.assertEqual(t['strike'], 1500.01)
        self.assertEqual(t['exercise'], 'Amer')
        self.assertEqual(t['right'], 'Put')
        self.assertEqual(t['qty'], 3000)

    def test_oi_annotation_stripped_but_tail_kept(self):
        t = self.blocks[0]['trades'][0]
        self.assertNotIn('(OI', t['text'])
        self.assertIn('vs 1313.40 stk 65d', t['text'])
        t2 = self.blocks[2]['trades'][1]
        self.assertTrue(t2['text'].endswith('- looks sold'))

    def test_series_keys_offer_both_prefixes_for_exercise(self):
        amer = self.blocks[0]['trades'][0]
        euro = self.blocks[2]['trades'][1]
        self.assertEqual([k[0] for k in series_keys(amer)], ['1SNDK', '3SNDK'])
        self.assertEqual([k[0] for k in series_keys(euro)], ['2TSM', '4TSM'])
        self.assertEqual(series_keys(amer)[0],
                         ('1SNDK', 'P', date(2026, 7, 31), 1500.01))


class TestResolveKey(unittest.TestCase):
    """ETF/index flex uses prefixes 3/4, so the primary guess can be wrong."""

    def setUp(self):
        self.path = _write_temp(REPORT_SNIPPET)
        self.oi = parse_flex_oi_report(self.path)

    def tearDown(self):
        os.unlink(self.path)

    def test_falls_through_to_index_prefix(self):
        trade = {'ticker': 'SMH', 'right': 'Call', 'exercise': 'Euro',
                 'expiry': date(2026, 8, 21), 'strike': 635.0}
        key = resolve_key(trade, self.oi, {})
        self.assertEqual(key[0], '4SMH')
        self.assertEqual(self.oi[key], 6164)

    def test_prefers_equity_prefix_when_present(self):
        trade = {'ticker': 'AAL', 'right': 'Call', 'exercise': 'Amer',
                 'expiry': date(2026, 9, 2), 'strike': 21.96}
        self.assertEqual(resolve_key(trade, self.oi, {})[0], '1AAL')

    def test_unmatched_falls_back_to_primary_candidate(self):
        trade = {'ticker': 'ZZZZ', 'right': 'Put', 'exercise': 'Amer',
                 'expiry': date(2026, 9, 2), 'strike': 10.0}
        self.assertEqual(resolve_key(trade, self.oi, {})[0], '1ZZZZ')


class TestReportValidation(unittest.TestCase):
    """OCC answers an unavailable date with HTTP 200 and a plain-text excuse."""

    def test_real_report_accepted(self):
        self.assertTrue(_is_report(REPORT_SNIPPET))

    def test_missing_file_message_rejected(self):
        self.assertFalse(_is_report('File requested does not exist.'))

    def test_empty_and_html_rejected(self):
        self.assertFalse(_is_report(''))
        self.assertFalse(_is_report('<!doctype html><html><body>x</body></html>'))


class TestOpenInterestIsALevel(unittest.TestCase):
    """
    Pinned to a real cross-check: on 7/31/2026 the desk hand-wrote
    "(OI = 18,717)" for BE 197.51 Put and "(OI = 2,100)" for MU 850.01 Put.
    Both equal the level in the 7/30 report — the latest one published when
    the color was written. Reporting a day-over-day change instead gave 0 and
    -2,100, the second being the expiry zeroing rather than the trade.
    """

    CHAT = (
        "12:38:28 Color - BE Listed vs Flex:\n"
        "\n"
        "BE Jul31st 197.5 Put 14k traded 1.90 elec live; stk ref 212.31 (OI = 14,426) - looks bot\n"
        "07/31/2026 197.51 Amer PM Put 14,000x traded 1.91 (OI = 18,717) - looks bot\n"
        "14:31:32 Color - MU Listed vs Flex:\n"
        "\n"
        "07/31/2026 850.01 Amer PM Put 1,050x traded 14.77 (OI = 2,100) - looks sold\n"
    )

    # The 7/30 report rows the desk's numbers came from.
    REPORT = (
        " EQUITY FLEX OPEN INTEREST REPORT   ACTIVITY DATE 07/30/26\n"
        "      1BE      P   07 31 2026  00197 510      4.1847     18717\n"
        "      1MU      P   07 31 2026  00850 010     13.6535      2100\n"
    )

    def setUp(self):
        self.chat_path = _write_temp(self.CHAT)
        self.report_path = _write_temp(self.REPORT)
        self.blocks = parse_chat(self.chat_path)

    def tearDown(self):
        os.unlink(self.chat_path)
        os.unlink(self.report_path)

    def test_reads_the_prior_business_day_report(self):
        # Friday 7/31 trades read against Thursday 7/30.
        self.assertEqual(report_date_for(date(2026, 7, 31)), date(2026, 7, 30))
        # Monday reads against Friday, not Sunday.
        self.assertEqual(report_date_for(date(2026, 8, 3)), date(2026, 7, 31))

    def test_levels_match_the_desk(self):
        oi = parse_flex_oi_report(self.report_path)
        be = self.blocks[0]['trades'][0]
        mu = self.blocks[1]['trades'][0]
        self.assertEqual(oi[resolve_key(be, oi)], 18717)
        self.assertEqual(oi[resolve_key(mu, oi)], 2100)

    def test_output_line_format(self):
        oi = parse_flex_oi_report(self.report_path)
        for block in self.blocks:
            for t in block['trades']:
                t['key'] = resolve_key(t, oi)
                t['oi'] = oi[t['key']]
                t['volume'] = t['qty']

        out = _write_temp('')
        try:
            write_output(self.blocks, out)
            with open(out) as f:
                text = f.read()
        finally:
            os.unlink(out)

        self.assertIn('OI = 18,717 / Volume = 14,000', text)
        self.assertIn('OI = 2,100 / Volume = 1,050', text)
        self.assertNotIn('OI Change', text)


class TestPreviousBusinessDay(unittest.TestCase):

    def test_monday_backs_up_to_friday(self):
        self.assertEqual(previous_business_day(date(2026, 7, 27)),
                         date(2026, 7, 24))

    def test_midweek(self):
        self.assertEqual(previous_business_day(date(2026, 7, 24)),
                         date(2026, 7, 23))


if __name__ == '__main__':
    unittest.main()

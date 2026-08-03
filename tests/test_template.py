import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from template import parse_line_options, extract_color_lines


class TestPatternA(unittest.TestCase):
    """Same expiry, two strikes + spread keyword."""

    def test_cs_same_expiry(self):
        result = parse_line_options("AAPL Jun 150/160 CS 1k traded live")
        self.assertEqual(result, ["AAPL Jun 150 Call", "AAPL Jun 160 Call"])

    def test_ps_same_expiry(self):
        result = parse_line_options("AAPL Jun 150/140 PS 1k traded live")
        self.assertEqual(result, ["AAPL Jun 150 Put", "AAPL Jun 140 Put"])

    def test_rr_same_expiry(self):
        result = parse_line_options("AAPL Jun 140/160 RR 1k traded live")
        self.assertEqual(result, ["AAPL Jun 140 Put", "AAPL Jun 160 Call"])

    def test_call_spread_keyword(self):
        result = parse_line_options("AAPL Jun 150/160 Call Spread 1k traded live")
        self.assertEqual(result, ["AAPL Jun 150 Call", "AAPL Jun 160 Call"])


class TestPatternB(unittest.TestCase):
    """Two expiries, same strike + spread keyword."""

    def test_rr_two_expiries_same_strike(self):
        result = parse_line_options("WBD Nov 20/Aug 20 RR 5k traded live")
        self.assertEqual(result, ["WBD Nov 20 Put", "WBD Aug 20 Call"])

    def test_cs_two_expiries_same_strike(self):
        result = parse_line_options("AAPL Jun/Sep 150 CS 2k traded live")
        self.assertEqual(result, ["AAPL Jun 150 Call", "AAPL Sep 150 Call"])

    def test_ps_two_expiries_same_strike(self):
        result = parse_line_options("AAPL Jun/Sep 150 PS 2k traded live")
        self.assertEqual(result, ["AAPL Jun 150 Put", "AAPL Sep 150 Put"])


class TestPatternC(unittest.TestCase):
    """Single option — expiry, strike, call/put."""

    def test_single_call(self):
        result = parse_line_options("AMZN Jun 415 Call 1k traded live; stk ref 400")
        self.assertEqual(result, ["AMZN Jun 415 Call"])

    def test_single_put(self):
        result = parse_line_options("AMZN Jun 415 Put 1k traded live; stk ref 400")
        self.assertEqual(result, ["AMZN Jun 415 Put"])

    def test_call_typo(self):
        result = parse_line_options("AAPL Jun 150 Cakk 1k traded live")
        self.assertEqual(result, ["AAPL Jun 150 Call"])

    def test_puts_plural(self):
        result = parse_line_options("AAPL Jun 150 Puts 1k traded live")
        self.assertEqual(result, ["AAPL Jun 150 Put"])

    def test_weekly_expiry(self):
        result = parse_line_options("AAPL 15Jun 150 Call 1k traded live")
        self.assertEqual(result, ["AAPL 15Jun 150 Call"])

    def test_ordinal_expiry(self):
        result = parse_line_options("AAPL Jun20th 150 Call 1k traded live")
        self.assertEqual(result, ["AAPL Jun20th 150 Call"])

    def test_year_qualified_expiry(self):
        result = parse_line_options("AAPL Jun27 150 Call 1k traded live")
        self.assertEqual(result, ["AAPL Jun27 150 Call"])


class TestPatternD(unittest.TestCase):
    """Two expiries, two different strikes + spread keyword."""

    def test_rr_different_expiries_different_strikes(self):
        # exp1 = Put, exp2 = Call
        result = parse_line_options(
            "WBD Nov 20 / Aug 30 RR paid 0.53 to buy nov put 5k live; stk ref 27.09"
        )
        self.assertEqual(result, ["WBD Nov 20 Put", "WBD Aug 30 Call"])

    def test_rr_no_spaces_around_slash(self):
        result = parse_line_options("WBD Nov 20/Aug 30 RR 5k live")
        self.assertEqual(result, ["WBD Nov 20 Put", "WBD Aug 30 Call"])

    def test_cs_different_expiries_different_strikes(self):
        result = parse_line_options("AAPL Jun 150/Sep 160 CS 2k live")
        self.assertEqual(result, ["AAPL Jun 150 Call", "AAPL Sep 160 Call"])

    def test_ps_different_expiries_different_strikes(self):
        result = parse_line_options("AAPL Jun 150/Sep 140 PS 2k live")
        self.assertEqual(result, ["AAPL Jun 150 Put", "AAPL Sep 140 Put"])

    def test_call_spread_keyword(self):
        result = parse_line_options("AAPL Jun 150/Sep 160 Call Spread 2k live")
        self.assertEqual(result, ["AAPL Jun 150 Call", "AAPL Sep 160 Call"])

    def test_decimal_strikes(self):
        result = parse_line_options("AAPL Jun 150.5/Sep 160.5 RR 2k live")
        self.assertEqual(result, ["AAPL Jun 150.5 Put", "AAPL Sep 160.5 Call"])

    def test_weekly_expiry_leg(self):
        result = parse_line_options("AAPL 15Jun 150/Sep 160 RR 2k live")
        self.assertEqual(result, ["AAPL 15Jun 150 Put", "AAPL Sep 160 Call"])

    def test_year_qualified_expiry_leg(self):
        result = parse_line_options("AAPL Jun27 150/Sep28 160 RR 2k live")
        self.assertEqual(result, ["AAPL Jun27 150 Put", "AAPL Sep28 160 Call"])


class TestEdgeCases(unittest.TestCase):

    def test_empty_line(self):
        self.assertEqual(parse_line_options(""), [])

    def test_no_ticker(self):
        self.assertEqual(parse_line_options("Jun 150 Call 1k live"), [])

    def test_no_match(self):
        self.assertEqual(parse_line_options("AAPL some random text"), [])

    def test_dedup_identical_legs(self):
        # If a line somehow produces the same option twice, it should only appear once
        result = parse_line_options("AAPL Jun 150 Call 1k and Jun 150 Call 2k live")
        self.assertEqual(result, ["AAPL Jun 150 Call"])


class TestFlexHeadersExcluded(unittest.TestCase):
    """
    Flex belongs to the flex report. Its block headers used to slip through
    as color lines and land in template.txt as a description with no legs,
    which then showed up as an empty stub in the OI/volume report.
    """

    def test_flex_header_dropped(self):
        lines = ["15:45:43 Color - MU Flex:\n"]
        self.assertEqual(extract_color_lines(lines), [])

    def test_listed_vs_flex_header_dropped(self):
        lines = ["14:26:53 Color - BE Listed vs Flex:\n"]
        self.assertEqual(extract_color_lines(lines), [])

    def test_ordinary_color_still_kept(self):
        lines = ["09:31:30 Color - AAPL Jul31st 287.5 Put 4,695x traded 0.03 live\n"]
        result = extract_color_lines(lines)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], '09:31:30')
        self.assertTrue(result[0][1].startswith('AAPL Jul31st'))

    def test_ticker_containing_flex_not_dropped(self):
        # Only a trailing "Flex:" header is a flex block — a normal trade line
        # that happens to mention flex must survive.
        lines = ["10:00:00 Color - FLEX Aug 20 Call 1k traded 1.00 live\n"]
        self.assertEqual(len(extract_color_lines(lines)), 1)

    def test_multiline_block_header_still_dropped(self):
        lines = ["09:40:41 Color - AMZN:\n"]
        self.assertEqual(extract_color_lines(lines), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)

import unittest
from template import parse_line_options


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


if __name__ == '__main__':
    unittest.main(verbosity=2)

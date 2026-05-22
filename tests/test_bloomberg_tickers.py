import os
import unittest

os.chdir(os.path.dirname(os.path.abspath(__file__)))
from bloomberg_tickers import convert_to_bloomberg_format


class TestRegularMonthlyExpiry(unittest.TestCase):
    """Plain month name — resolves to first (earliest) matching entry in dates.txt."""

    def test_jun_resolves_to_2026(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL Jun 150 Call OI Change:"),
                         "AAPL US 6/18/26 C150 Equity")

    def test_jun_lowercase(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL jun 150 Call OI Change:"),
                         "AAPL US 6/18/26 C150 Equity")

    def test_jun_uppercase(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL JUN 150 Call OI Change:"),
                         "AAPL US 6/18/26 C150 Equity")

    def test_dec_resolves_to_2026(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL Dec 150 Call OI Change:"),
                         "AAPL US 12/18/26 C150 Equity")

    def test_may_resolves_to_2027_no_may_2026_in_file(self):
        # dates.txt starts at Jun 2026 — first May is 5/21/27
        self.assertEqual(convert_to_bloomberg_format("AAPL May 150 Call OI Change:"),
                         "AAPL US 5/21/27 C150 Equity")

    def test_jan_resolves_to_2027_no_jan_2026_in_file(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL Jan 150 Call OI Change:"),
                         "AAPL US 1/15/27 C150 Equity")

    def test_put_option(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL Jun 150 Put OI Change:"),
                         "AAPL US 6/18/26 P150 Equity")


class TestYearQualifiedMonthlyExpiry(unittest.TestCase):
    """Month + 2-digit year — looks up exact expiry from dates.txt."""

    def test_jun26(self):
        self.assertEqual(convert_to_bloomberg_format("AMZN Jun26 415 Call OI Change:"),
                         "AMZN US 6/18/26 C415 Equity")

    def test_jun27(self):
        self.assertEqual(convert_to_bloomberg_format("AMZN Jun27 415 Call OI Change:"),
                         "AMZN US 6/17/27 C415 Equity")

    def test_jun28(self):
        self.assertEqual(convert_to_bloomberg_format("AMZN Jun28 415 Call OI Change:"),
                         "AMZN US 6/15/28 C415 Equity")

    def test_dec26(self):
        self.assertEqual(convert_to_bloomberg_format("MSFT Dec26 400 Put OI Change:"),
                         "MSFT US 12/18/26 P400 Equity")

    def test_dec27(self):
        self.assertEqual(convert_to_bloomberg_format("MSFT Dec27 400 Put OI Change:"),
                         "MSFT US 12/17/27 P400 Equity")

    def test_dec28(self):
        self.assertEqual(convert_to_bloomberg_format("MSFT Dec28 400 Put OI Change:"),
                         "MSFT US 12/15/28 P400 Equity")

    def test_jan27(self):
        self.assertEqual(convert_to_bloomberg_format("PEN Jan27 300 Put OI Change:"),
                         "PEN US 1/15/27 P300 Equity")

    def test_jan28(self):
        self.assertEqual(convert_to_bloomberg_format("PEN Jan28 300 Put OI Change:"),
                         "PEN US 1/21/28 P300 Equity")

    def test_sep27(self):
        self.assertEqual(convert_to_bloomberg_format("TECK Sep27 80 Call OI Change:"),
                         "TECK US 9/17/27 C80 Equity")

    def test_year_qualified_lowercase_month(self):
        self.assertEqual(convert_to_bloomberg_format("AMZN jun26 415 Call OI Change:"),
                         "AMZN US 6/18/26 C415 Equity")

    def test_year_qualified_uppercase_month(self):
        self.assertEqual(convert_to_bloomberg_format("AMZN JUN26 415 Call OI Change:"),
                         "AMZN US 6/18/26 C415 Equity")


class TestWeeklyExpiryDayMonth(unittest.TestCase):
    """Day + month format (e.g. 15Jun) — uses the year from the first matching month entry."""

    def test_15jun(self):
        # First Jun is 6/18/26, so year = 26
        self.assertEqual(convert_to_bloomberg_format("AAPL 15Jun 150 Call OI Change:"),
                         "AAPL US 6/15/26 C150 Equity")

    def test_15jun_lowercase(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL 15jun 150 Call OI Change:"),
                         "AAPL US 6/15/26 C150 Equity")

    def test_5dec(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL 5Dec 150 Call OI Change:"),
                         "AAPL US 12/5/26 C150 Equity")

    def test_10jan_resolves_to_2027(self):
        # First Jan is 1/15/27
        self.assertEqual(convert_to_bloomberg_format("AAPL 10Jan 150 Call OI Change:"),
                         "AAPL US 1/10/27 C150 Equity")

    def test_20aug(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL 20Aug 150 Put OI Change:"),
                         "AAPL US 8/20/26 P150 Equity")


class TestWeeklyExpiryOrdinal(unittest.TestCase):
    """Month + day + ordinal suffix (e.g. Jun20th) — uses year from first matching month entry."""

    def test_jun20th(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL Jun20th 150 Call OI Change:"),
                         "AAPL US 6/20/26 C150 Equity")

    def test_jun20th_lowercase(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL jun20th 150 Call OI Change:"),
                         "AAPL US 6/20/26 C150 Equity")

    def test_jul31st(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL Jul31st 150 Call OI Change:"),
                         "AAPL US 7/31/26 C150 Equity")

    def test_aug2nd(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL Aug2nd 150 Call OI Change:"),
                         "AAPL US 8/2/26 C150 Equity")

    def test_sep3rd(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL Sep3rd 150 Call OI Change:"),
                         "AAPL US 9/3/26 C150 Equity")

    def test_jan10th_resolves_to_2027(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL Jan10th 150 Call OI Change:"),
                         "AAPL US 1/10/27 C150 Equity")


class TestOptionTypeCaseInsensitivity(unittest.TestCase):

    def test_call_lowercase(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL Jun 150 call OI Change:"),
                         "AAPL US 6/18/26 C150 Equity")

    def test_call_uppercase(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL Jun 150 CALL OI Change:"),
                         "AAPL US 6/18/26 C150 Equity")

    def test_put_lowercase(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL Jun 150 put OI Change:"),
                         "AAPL US 6/18/26 P150 Equity")

    def test_put_uppercase(self):
        self.assertEqual(convert_to_bloomberg_format("AAPL Jun 150 PUT OI Change:"),
                         "AAPL US 6/18/26 P150 Equity")


class TestErrorCases(unittest.TestCase):

    def test_year_not_in_file(self):
        # May 2026 not in dates.txt
        with self.assertRaises(ValueError):
            convert_to_bloomberg_format("AAPL May26 150 Call OI Change:")

    def test_year_beyond_file(self):
        with self.assertRaises(ValueError):
            convert_to_bloomberg_format("AAPL Jun29 150 Call OI Change:")

    def test_invalid_month_name(self):
        with self.assertRaises(ValueError):
            convert_to_bloomberg_format("AAPL Xyz 150 Call OI Change:")

    def test_too_few_parts(self):
        with self.assertRaises(ValueError):
            convert_to_bloomberg_format("AAPL Jun 150")

    def test_invalid_month_format(self):
        with self.assertRaises(ValueError):
            convert_to_bloomberg_format("AAPL 2026/06/18 150 Call OI Change:")


if __name__ == '__main__':
    unittest.main(verbosity=2)

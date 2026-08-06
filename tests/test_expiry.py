"""
Convention: an expired option has no open interest, so its OI value is
overridden to 0 whatever the data source returned. Measured against today.
"""
import os
import sys
import unittest
from datetime import date, timedelta

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, 'src')
from expiry import expiry_of_oi_line, has_expired, zero_expired


class TestExpiryOfOiLine(unittest.TestCase):
    """Expiry comes via convert_to_bloomberg_format, so dates.txt drives it."""

    def test_weekly_ordinal(self):
        self.assertEqual(
            expiry_of_oi_line("AAPL Jul31st 287.5 Put OI Change:"),
            date(2026, 7, 31))

    def test_monthly(self):
        self.assertEqual(
            expiry_of_oi_line("AAPL Dec 150 Call OI Change:"),
            date(2026, 12, 18))

    def test_year_qualified(self):
        self.assertEqual(
            expiry_of_oi_line("PEN Jan28 300 Put OI Change:"),
            date(2028, 1, 21))

    def test_unparseable_returns_none(self):
        self.assertIsNone(expiry_of_oi_line("not a real line"))
        self.assertIsNone(expiry_of_oi_line("AAPL Xyz 150 Call OI Change:"))


class TestHasExpired(unittest.TestCase):

    def test_past_expiry(self):
        self.assertTrue(has_expired(date(2020, 1, 17)))

    def test_future_expiry(self):
        self.assertFalse(has_expired(date.today() + timedelta(days=30)))

    def test_expiring_today_is_not_yet_expired(self):
        # Still live on its expiry date.
        self.assertFalse(has_expired(date.today()))

    def test_none_is_never_expired(self):
        # An unresolvable expiry must not be silently zeroed.
        self.assertFalse(has_expired(None))

    def test_explicit_as_of(self):
        self.assertTrue(has_expired(date(2026, 7, 31), as_of=date(2026, 8, 3)))
        self.assertFalse(has_expired(date(2026, 7, 31), as_of=date(2026, 7, 31)))
        self.assertFalse(has_expired(date(2026, 7, 31), as_of=date(2026, 7, 30)))


class TestZeroExpired(unittest.TestCase):

    LINES = [
        "AAPL Jul31st 287.5 Put OI Change:\n",   # expired as of 8/3/2026
        "PEN Jan28 300 Put OI Change:\n",        # still live
    ]

    def test_only_expired_lines_are_zeroed(self):
        subs = {0: ('4695', '12000'), 1: ('-250', '900')}
        n = zero_expired(subs, self.LINES, as_of=date(2026, 8, 3))
        self.assertEqual(n, 1)
        self.assertEqual(subs[0], ('0', '12000'))   # overridden
        self.assertEqual(subs[1], ('-250', '900'))  # untouched

    def test_volume_is_preserved(self):
        subs = {0: ('4695', '12000')}
        zero_expired(subs, self.LINES, as_of=date(2026, 8, 3))
        self.assertEqual(subs[0][1], '12000')

    def test_negative_values_are_overridden_too(self):
        subs = {0: ('-4695', '12000')}
        zero_expired(subs, self.LINES, as_of=date(2026, 8, 3))
        self.assertEqual(subs[0], ('0', '12000'))

    def test_nothing_zeroed_before_expiry(self):
        subs = {0: ('4695', '12000'), 1: ('-250', '900')}
        n = zero_expired(subs, self.LINES, as_of=date(2026, 7, 30))
        self.assertEqual(n, 0)
        self.assertEqual(subs[0], ('4695', '12000'))

    def test_already_zero_is_not_counted_as_an_override(self):
        subs = {0: ('0', '12000')}
        self.assertEqual(zero_expired(subs, self.LINES, as_of=date(2026, 8, 3)), 0)


if __name__ == '__main__':
    unittest.main()
